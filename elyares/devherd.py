"""Vigila DevHerd Observe y convierte lo que encuentra en alertas para la isla.

Observe no avisa hacia afuera ni tiene transmisión en vivo: hay que preguntarle.
Cada POLL_SECS se piden los problemas y los contenedores a su API local y se
comparan con la vez anterior. De ahí salen tres avisos:

    error      un problema de nivel error recibió eventos nuevos
    contenedor uno vigilado se reinició solo, o se cayó con un código de error
    colector   Observe dejó de responder

La primera consulta solo toma la foto: lo que ya estaba roto no se anuncia.
Los avisos salen como mensajes `alert` / `alert-clear`, con la misma forma que
los eventos de `elyares-hook`, para que el modelo los trate igual.

Cada aviso lleva su ficha: de un error, el archivo y la línea donde revienta
y la petición que lo causó; de un contenedor, sus últimas líneas de log. Y
sus botones: Timeline (`devherd observe timeline`) y Abrir para un error,
Logs y Levantar (`devherd up`) para un contenedor, Iniciar para el colector.
"""

import json
import subprocess
import threading
import time
import urllib.parse
import urllib.request

BASE = 'http://127.0.0.1:9777'
UNIT = 'devherd-observe.service'
POLL_SECS = 10
DOWN_POLLS = 3            # consultas fallidas seguidas antes de dar al colector por caído
LOOP_RESTARTS = 3         # reinicios en LOOP_SECS para llamarlo bucle
LOOP_SECS = 300
ERROR_LEVELS = ('error', 'fatal')
# Con estos códigos el contenedor no se cayó: lo pararon (docker stop manda
# SIGTERM = 143 y, si no hace caso, SIGKILL = 137).
STOP_CODES = (0, 137, 143)
TAIL_LINES = 8            # líneas de log que van en la ficha de un contenedor
WORKDIR_LABEL = 'com.docker.compose.project.working_dir'


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=2) as r:
        data = json.load(r)
    return data if isinstance(data, list) else []


def snapshot():
    """Problemas y contenedores de Observe, o None si no responde."""
    try:
        return {'issues': _get('/api/observe/issues?limit=100'),
                'containers': _get('/api/observe/containers?limit=500')}
    except (OSError, ValueError):
        return None


def exit_info(container_id):
    """(código de salida, murió sin memoria) o None si el contenedor ya no existe."""
    try:
        out = subprocess.run(
            ['docker', 'inspect', '-f', '{{.State.ExitCode}} {{.State.OOMKilled}}', container_id],
            capture_output=True, text=True, timeout=2).stdout.split()
        return int(out[0]), out[1] == 'true'
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def tail(container_id, n=TAIL_LINES):
    """Las últimas líneas de log de un contenedor, o [] si ya no existe."""
    try:
        out = subprocess.run(['docker', 'logs', '--tail', str(n), container_id],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors='replace', timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in out.splitlines() if line.strip()][-n:]


def last_event(project, issue_id):
    """El evento más reciente de un problema, o None. La API no filtra por
    problema: se piden los últimos del proyecto y se busca entre ellos."""
    try:
        events = _get(f'/api/observe/events?project={urllib.parse.quote(project)}&limit=50')
    except (OSError, ValueError):
        return None
    return next((e for e in events if str(e.get('issue_id')) == str(issue_id)), None)


def unit_enabled():
    """¿El colector debería estar corriendo? Sin esto, si ya estaba caído al
    arrancar la mascota no habría forma de saber que falta."""
    try:
        out = subprocess.run(['systemctl', '--user', 'is-enabled', UNIT],
                             capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return out == 'enabled'


def _alert(sid, name, message, **card):
    """card: la ficha de la alerta (where, note, lines, actions)."""
    return {'event': 'alert', 'session_id': f'devherd:{sid}', 'name': name,
            'message': message, 'url': BASE + '/', **card}


def _logs(container):
    return {'label': 'Logs', 'cmd': ['docker', 'logs', '-f', '--tail', '200', container],
            'term': True, 'hold': True}


def _clear(sid):
    return {'event': 'alert-clear', 'session_id': f'devherd:{sid}'}


class Watcher:
    def __init__(self, expected_up=False, exit_info=exit_info, tail=tail, last_event=last_event):
        self.exit_info, self.tail, self.last_event = exit_info, tail, last_event
        self.issues = None        # id -> event_count, de la consulta anterior
        self.containers = None    # container_id -> (estado, reinicios)
        self.restarts = {}        # proyecto/servicio -> momentos de sus reinicios
        self.down = set()         # proyecto/servicio con aviso de caído
        self.fails = 0
        self.seen_up = expected_up
        self.collector_down = False

    def step(self, snap, now):
        """Compara una foto con la anterior y devuelve los mensajes que tocan."""
        if snap is None:
            self.fails += 1
            if self.fails == DOWN_POLLS and self.seen_up:
                self.collector_down = True
                start = {'label': 'Iniciar', 'cmd': ['systemctl', '--user', 'start', UNIT],
                         'after': 'clear'}
                return [_alert('collector', 'devherd', 'Observe no responde', actions=[start])]
            return []
        msgs = []
        if self.collector_down:
            msgs.append(_clear('collector'))
        self.fails, self.seen_up, self.collector_down = 0, True, False
        msgs += self._issues(snap.get('issues') or [])
        msgs += self._containers(snap.get('containers') or [], now)
        return msgs

    def _issues(self, issues):
        counts = {i.get('id'): i.get('event_count') or 0 for i in issues}
        before, self.issues = self.issues, {**(self.issues or {}), **counts}
        if before is None:
            return []
        msgs = []
        for i in issues:
            iid, count = i.get('id'), i.get('event_count') or 0
            if i.get('level') not in ERROR_LEVELS or count <= before.get(iid, 0):
                continue
            # Sin límite de memoria no hay "ya lo había visto": un problema
            # viejo que cae fuera de la consulta volvería como desconocido.
            new = iid not in before and i.get('first_seen') == i.get('last_seen')
            title = i.get('title') or 'error'
            text = f'Error nuevo: {title}' if new else f'Error otra vez ({count}): {title}'
            project = i.get('project') or 'devherd'
            event = self.last_event(project, iid) or {}
            actions = [{'label': 'Abrir', 'url': BASE + '/', 'after': 'dismiss'}]
            if event.get('event_id'):
                actions.insert(0, {'label': 'Timeline', 'term': True, 'hold': True,
                                   'cmd': ['devherd', 'observe', 'timeline', event['event_id']]})
            events = '1 evento' if count == 1 else f'{count} eventos'
            msgs.append(_alert(
                f'issue:{iid}', project, text, where=i.get('culprit') or '',
                note=' · '.join(filter(None, [i.get('service'), events])),
                lines=[event.get('transaction') or ''], actions=actions))
        return msgs

    def _containers(self, containers, now):
        current = {c.get('container_id'): c for c in containers if c.get('container_id')}
        before = self.containers
        self.containers = {cid: (c.get('status'), c.get('restart_count') or 0)
                           for cid, c in current.items()}
        if before is None:
            return []
        msgs = []
        for cid, c in current.items():
            project = c.get('project') or 'devherd'
            service = c.get('service') or c.get('name') or 'contenedor'
            key = f'{project}/{service}'
            name = c.get('name') or cid[:12]
            status, count = self.containers[cid]
            if cid not in before:
                # Recreado: si era el que estaba caído, ya volvió.
                if status == 'running' and key in self.down:
                    self.down.discard(key)
                    msgs.append(_clear(f'ct:{key}'))
                continue
            was, had = before[cid]
            if count > had:
                # Docker solo cuenta los reinicios de la política de reinicio:
                # los que siguen a una caída, no un `docker restart` a mano.
                times = ([t for t in self.restarts.get(key, []) if now - t < LOOP_SECS]
                         + [now] * (count - had))
                self.restarts[key] = times
                text = (f'{service} reinicia en bucle ({len(times)} veces en 5 min)'
                        if len(times) >= LOOP_RESTARTS else f'{service} se reinició')
                msgs.append(_alert(
                    f'ct:{key}', project, text, where=name,
                    note='1 reinicio' if count == 1 else f'{count} reinicios',
                    lines=self.tail(cid), actions=[_logs(name)]))
            elif was == 'running' and status in ('exited', 'dead'):
                info = self.exit_info(cid)
                if info is None:
                    continue
                code, oom = info
                if oom or code not in STOP_CODES:
                    self.down.add(key)
                    why = 'sin memoria' if oom else f'código {code}'
                    actions = [_logs(name)]
                    path = (c.get('labels') or {}).get(WORKDIR_LABEL)
                    if path:
                        actions.append({'label': 'Levantar', 'cmd': ['devherd', 'up', path],
                                        'term': True, 'hold': True, 'after': 'clear'})
                    msgs.append(_alert(
                        f'ct:{key}', project, f'{service} se cayó ({why})', where=name,
                        note=why, lines=self.tail(cid), actions=actions))
            elif status == 'running' and was != 'running' and key in self.down:
                self.down.discard(key)
                msgs.append(_clear(f'ct:{key}'))
        return msgs


def watch(emit, enabled=lambda: True):
    """Consulta Observe en un hilo y llama a emit(mensaje) por cada aviso.

    Mientras enabled() sea falso no pregunta, y al volver empieza de cero: lo
    que cambió con la fuente apagada no se anuncia.
    """
    def loop():
        watcher, up = None, None
        while True:
            if not enabled():
                watcher, up = None, None
                time.sleep(POLL_SECS)
                continue
            if watcher is None:
                watcher = Watcher(expected_up=unit_enabled())
            try:
                snap = snapshot()
                if (snap is not None) != up:
                    up = snap is not None
                    source = {'event': 'source', 'name': 'devherd', 'ok': up}
                    if not up:
                        source.update(why=f'Observe no responde en {BASE.split("//")[1]}',
                                      fix='Arráncalo con: devherd observe start')
                    emit(source)
                for msg in watcher.step(snap, time.monotonic()):
                    emit(msg)
            except Exception:
                # Una respuesta con otra forma no debe matar al vigilante.
                pass
            time.sleep(POLL_SECS)

    threading.Thread(target=loop, daemon=True, name='devherd').start()
