"""Los contenedores de los proyectos de DevHerd: cuáles están arriba, cuáles no y qué consumen.

Todo sale de `docker` (contenedores, recursos y logs) y de `devherd list --json`
(los proyectos registrados, aunque no tengan ningún contenedor). Un contenedor
se asigna a su proyecto por la carpeta de compose (`working_dir`).

`Watcher` pregunta en un hilo, para que el dibujo nunca espere a un subproceso;
`LogTail` sigue el log de un contenedor en otro. Las acciones (levantar, parar)
corren en un hilo y devuelven (ok, texto).
"""

import collections
import json
import os
import re
import subprocess
import threading
import time

EVERY = 3.0                       # segundos entre consultas
LOG_LINES = 300                   # líneas de log que se guardan por contenedor
WORKDIR = 'com.docker.compose.project.working_dir'
SERVICE = 'com.docker.compose.service'
UNITS = {'B': 1, 'KB': 1e3, 'MB': 1e6, 'GB': 1e9, 'TB': 1e12,
         'KIB': 1024, 'MIB': 1024 ** 2, 'GIB': 1024 ** 3, 'TIB': 1024 ** 4}


def _run(cmd, timeout=10):
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=timeout)
    except (OSError, subprocess.SubprocessError) as err:
        return False, str(err)
    return done.returncode == 0, (done.stdout if done.returncode == 0 else done.stderr or done.stdout).strip()


def _jsonl(text):
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _labels(text):
    """`k=v,k=v` de docker. Un valor puede traer comas (los archivos de compose): se corta solo
    donde lo que sigue a la coma parece otra clave."""
    out = {}
    key = None
    for part in (text or '').split(','):
        head, eq, tail = part.partition('=')
        if eq and re.fullmatch(r'[\w.\-/]+', head):
            key = head
            out[key] = tail
        elif key:
            out[key] += ',' + part
    return out


def parse_ps(text):
    """`docker ps -a --format json` → [{id, name, service, state, status, health, path}]."""
    rows = []
    for row in _jsonl(text):
        labels = _labels(row.get('Labels'))
        rows.append(dict(id=row.get('ID', ''), name=row.get('Names', ''), service=labels.get(SERVICE, ''),
                         state=row.get('State', ''), status=row.get('Status', ''),
                         health=row.get('HealthStatus', ''), path=labels.get(WORKDIR, '')))
    return rows


def to_bytes(text):
    """«11.2MiB» → 11744051.2; 0 si no se entiende."""
    m = re.fullmatch(r'\s*([\d.]+)\s*([A-Za-z]+)\s*', text or '')
    if not m or m.group(2).upper() not in UNITS:
        return 0.0
    return float(m.group(1)) * UNITS[m.group(2).upper()]


def parse_stats(text):
    """`docker stats --no-stream --format json` → {nombre: {cpu (%), mem, mem_limit (bytes), mem_pct, net_rx, net_tx}}."""
    out = {}
    for row in _jsonl(text):
        used, _, limit = (row.get('MemUsage') or '').partition('/')
        rx, _, tx = (row.get('NetIO') or '').partition('/')
        out[row.get('Name', '')] = dict(
            cpu=_pct(row.get('CPUPerc')), mem=to_bytes(used), mem_limit=to_bytes(limit),
            mem_pct=_pct(row.get('MemPerc')), net_rx=to_bytes(rx), net_tx=to_bytes(tx))
    return out


def _pct(text):
    try:
        return float((text or '').strip().rstrip('%'))
    except ValueError:
        return 0.0


def group(projects, containers, stats):
    """Une los proyectos de DevHerd (`[{name, path}]`) con sus contenedores.

    Devuelve [{name, path, containers, running, total, cpu, mem}], los que tienen algo arriba primero y
    luego por nombre. Un contenedor cuya carpeta no está registrada forma su propio proyecto."""
    by_path = {os.path.normpath(p['path']): dict(name=p['name'], path=p['path'], containers=[]) for p in projects}
    for c in containers:
        key = os.path.normpath(c['path']) if c['path'] else ''
        slot = by_path.setdefault(key, dict(name=os.path.basename(key) or '(sin proyecto)', path=c['path'],
                                            containers=[]))
        slot['containers'].append(dict(c, **stats.get(c['name'], {})))
    result = []
    for slot in by_path.values():
        slot['containers'].sort(key=lambda c: (c['state'] != 'running', c['service'] or c['name']))
        up = [c for c in slot['containers'] if c['state'] == 'running']
        slot.update(running=len(up), total=len(slot['containers']),
                    cpu=sum(c.get('cpu', 0.0) for c in up), mem=sum(c.get('mem', 0.0) for c in up))
        result.append(slot)
    return sorted(result, key=lambda p: (p['running'] == 0, p['name'].lower()))


def totals(projects, host_mem=0.0):
    """La suma de todo lo que está arriba: (contenedores arriba, de un total, % de CPU, bytes de memoria)."""
    boxes = [c for p in projects for c in p['containers']]
    up = [c for c in boxes if c['state'] == 'running']
    return dict(up=len(up), total=len(boxes), cpu=sum(c.get('cpu', 0.0) for c in up),
                mem=sum(c.get('mem', 0.0) for c in up), host_mem=host_mem)


def host_memory():
    """La memoria total de la máquina en bytes (0 si no se sabe)."""
    try:
        with open('/proc/meminfo') as f:
            return float(f.readline().split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return 0.0


def fmt_bytes(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return ''


def snapshot():
    """Todo de una vez: {projects, totals} o None si docker no contesta."""
    ok, ps = _run(['docker', 'ps', '-a', '--format', '{{json .}}'], timeout=8)
    if not ok:
        return None
    ok, stats = _run(['docker', 'stats', '--no-stream', '--format', '{{json .}}'], timeout=15)
    ok_list, listed = _run(['devherd', 'list', '--json'], timeout=8)
    try:
        registered = [dict(name=p['Name'], path=p['Path']) for p in json.loads(listed)] if ok_list else []
    except (ValueError, KeyError, TypeError):
        registered = []
    projects = group(registered, parse_ps(ps), parse_stats(stats) if ok else {})
    return dict(projects=projects, totals=totals(projects, host_memory()))


class Watcher:
    """`read()` devuelve lo último que se supo (None hasta la primera respuesta, o si docker no contesta)."""

    def __init__(self):
        self.data = None
        self.loaded = False             # ya contestó docker una vez (bien o mal): antes de eso, la vista muestra un esqueleto
        self.at = 0.0
        self.busy = False

    def read(self):
        now = time.monotonic()
        if not self.busy and now - self.at >= EVERY:
            self.busy, self.at = True, now
            threading.Thread(target=self._fetch, daemon=True).start()
        return self.data

    def refresh(self):
        self.at = 0.0

    def _fetch(self):
        try:
            self.data = snapshot()
        finally:
            self.loaded = True
            self.busy = False


class LogTail:
    """El log de un contenedor, en vivo: `docker logs -f` en un hilo y las últimas LOG_LINES en memoria."""

    def __init__(self, name):
        self.name = name
        self.lines = collections.deque(maxlen=LOG_LINES)
        self.stamp = 0                  # sube con cada línea nueva: quien dibuja sabe si cambió algo
        self.proc = None
        self.closed = False
        threading.Thread(target=self._follow, daemon=True).start()

    def _follow(self):
        try:
            self.proc = subprocess.Popen(['docker', 'logs', '-f', '--tail', str(LOG_LINES), self.name],
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, errors='replace')
        except OSError as err:
            self.lines.append(f'No se pudo leer el log: {err}')
            self.stamp += 1
            return
        for line in self.proc.stdout:
            self.lines.append(line.rstrip('\n'))
            self.stamp += 1
        self.proc.wait()

    def close(self):
        self.closed = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def _stream(cmd, on_line, timeout=300):
    """Corre `cmd` y le va dando a `on_line` cada línea que escribe. → (ok, últimas líneas)."""
    tail = collections.deque(maxlen=6)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    except OSError as err:
        return False, str(err)
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        for line in proc.stdout:
            line = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', line).strip()       # sin colores de la terminal
            if line:
                tail.append(line)
                if on_line:
                    on_line(line)
        proc.wait()
    finally:
        timer.cancel()
    return proc.returncode == 0, '\n'.join(tail)


def act(order, target, on_line=None):
    """`up`/`stop-project` de un proyecto (carpeta) o `stop`/`start` de un contenedor (nombre).
    → (ok, texto). `on_line` recibe lo que va escribiendo `devherd`, para mostrar el avance."""
    if order in ('up', 'stop-project'):
        return _stream(['devherd', 'up' if order == 'up' else 'stop', target], on_line)
    if order in ('stop', 'start'):
        return _run(['docker', order, target], timeout=60)
    return False, f'orden desconocida: {order}'
