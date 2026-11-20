"""El consumo de tu plan de Claude para la isla: la sesión de 5 h, la semana y cuándo se reinician.

Los números salen de `claudebar --json` (el mismo que pinta el módulo de Waybar; lee la sesión del
CLI de claude y guarda una caché de 60 s, así que preguntar seguido no pega a la API). Ni aquí ni en
la isla se tocan tokens ni credenciales.

`claudebar` solo dice cuánto llevas, no cuánto gastaste cada día. Para la gráfica por día se guarda
una muestra de la semana en `HISTORY` cada `SAMPLE_EVERY` segundos (`record`) y el gasto de un día es
cuánto subió el porcentaje semanal entre sus muestras (`daily`). Antes de la primera muestra no hay
historia que dibujar: se llena sola con los días.
"""

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta

HISTORY = os.path.expanduser('~/.local/share/elyares-engineer/usage.jsonl')
EVERY = 60.0                      # segundos entre preguntas con el panel abierto (igual que la caché de claudebar)
SAMPLE_EVERY = 600.0              # segundos entre muestras que se guardan
KEEP_DAYS = 21                    # lo que se conserva en disco
TIMEOUT = 15
DAYS = 7                          # barras de la gráfica


def parse(text):
    """La salida de `claudebar --json` a un dict, o None si no trae la sesión ni la semana.

    Sale `{'session': (pct, reset_unix), 'weekly': (pct, reset_unix), 'plan': str, 'models': [(grupo, pct)]}`."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get('error'):
        return None
    out = {'plan': str(data.get('plan') or ''), 'models': []}
    for win in data.get('windows') or ():
        if not isinstance(win, dict):
            continue
        try:
            pct = float(win.get('used_pct'))
            reset = float(win.get('reset_at_unix') or 0)
        except (TypeError, ValueError):
            continue
        if win.get('id') in ('session', 'weekly') and win['id'] not in out:
            out[win['id']] = (pct, reset)
        elif win.get('group'):
            out['models'].append((str(win['group']), pct))
    if 'session' not in out and 'weekly' not in out:
        return None
    return out


def snapshot():
    """Lo que dice `claudebar` ahora, o None si no está instalado, falla o no se entiende."""
    try:
        done = subprocess.run(['claudebar', '--json'], capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse(done.stdout) if done.returncode == 0 else None


def load(path=None):
    """Las muestras guardadas, de la más vieja a la más nueva: `[(unix, pct_sesion, pct_semana)]`."""
    samples = []
    try:
        with open(path or HISTORY, encoding='utf-8') as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    samples.append((float(row['t']), float(row['s']), float(row['w'])))
                except (ValueError, KeyError, TypeError):
                    continue                    # una línea rota no tumba la historia
    except OSError:
        pass
    return sorted(samples)


def record(data, now=None, path=None):
    """Guarda una muestra de `data` si pasaron `SAMPLE_EVERY` desde la última; recorta lo muy viejo. ¿Guardó?"""
    if not data or 'weekly' not in data:
        return False
    path = path or HISTORY
    now = time.time() if now is None else now
    samples = load(path)
    if samples and now - samples[-1][0] < SAMPLE_EVERY:
        return False
    samples.append((now, data.get('session', (0.0, 0))[0], data['weekly'][0]))
    cut = now - KEEP_DAYS * 86400
    samples = [s for s in samples if s[0] >= cut]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f'{path}.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            for t, s, w in samples:
                fh.write(json.dumps({'t': round(t), 's': s, 'w': w}) + '\n')
        os.replace(tmp, path)
    except OSError:
        return False
    return True


def midnight(day):
    """Unix de la medianoche (hora local) de la fecha `day`."""
    return datetime(day.year, day.month, day.day).timestamp()


def daily(samples, now=None, days=DAYS):
    """El gasto de cada uno de los últimos `days` días, del más viejo a hoy: `[(fecha, puntos)]`.

    Un punto es 1 % de la semana. El gasto de un día es lo que subió el porcentaje semanal entre dos
    muestras seguidas que cayeron ese día; cuando baja es que la semana se reinició y no resta nada.
    Un día sin muestras vale 0."""
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now).date()
    spent = {today - timedelta(days=i): 0.0 for i in range(days)}
    for (_, _, before), (t, _, after) in zip(samples, samples[1:]):
        day = datetime.fromtimestamp(t).date()
        if day in spent and after > before:
            spent[day] += after - before
    return sorted(spent.items())


def left(reset, now=None):
    """Cuánto falta para `reset` (unix): «2 h 12 min», «1 d 10 h», «45 min» o «ya»."""
    now = time.time() if now is None else now
    secs = int(reset - now)
    if reset <= 0:
        return '—'
    if secs <= 0:
        return 'ya'
    days, rest = divmod(secs, 86400)
    hours, rest = divmod(rest, 3600)
    mins = rest // 60
    if days:
        return f'{days} d {hours} h'
    if hours:
        return f'{hours} h {mins:02d} min'
    return f'{max(1, mins)} min'


class Watcher:
    """`read()` devuelve lo último que se supo (None si `claudebar` no contesta) y pregunta cada EVERY s en un hilo."""

    def __init__(self):
        self.data = None
        self.loaded = False
        self.at = 0.0
        self.busy = False
        self.samples = []

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
            got = snapshot()
            if got:
                self.data = got
                record(got)
            self.samples = load()
        finally:
            self.loaded = True
            self.busy = False


def sample_in_background():
    """Una muestra para la historia, aunque el panel esté cerrado. Va en un hilo: `claudebar` puede tardar."""
    def work():
        record(snapshot())
    threading.Thread(target=work, daemon=True).start()
    return True
