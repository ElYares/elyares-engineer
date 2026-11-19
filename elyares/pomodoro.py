"""La vista Pomodoro: lo que dice `coffe` y las órdenes que se le dan.

El reloj lo manda el daemon de `coffe`; aquí solo se le pregunta
(`coffe status --json`, `coffe task list`) y se le piden cosas (`coffe start`,
`pause`, `void`, `done`). Nunca se escribe su estado.
"""

import json
import re
import shutil
import subprocess
import threading
import time

EVERY = 1.0               # cada cuánto se le pregunta al reloj mientras la vista está a la vista
TASKS_EVERY = 10.0        # la lista de tareas cambia menos
MAX_TASKS = 12
FOCUS_PHASES = ('focus', 'overlearning')
PHASES = {'idle': 'Parado', 'focus': 'En foco', 'overlearning': 'En foco',
          'short_break': 'Descanso', 'long_break': 'Descanso largo'}
BREAKS = ('short_break', 'long_break')
# `coffe task list`: id, estado, tiempo, prioridad, título (con «…») y [pomodoros] y proyecto.
TASK_LINE = re.compile(r'^\s*(\d+)\s+(\S+)\s+\S+\s+(\S+)\s+(.*?)\s+(\[[^\]]*\])\s+(.*\S)\s*$')


def clock(secs):
    secs = max(0, int(secs or 0))
    return f'{secs // 60:02d}:{secs % 60:02d}'


def parse_tasks(text):
    """La salida de `coffe task list` -> [dict(id, title, project)] de las pendientes."""
    tasks = []
    for line in text.splitlines():
        m = TASK_LINE.match(line)
        if m and m.group(2) == 'pendiente':
            tasks.append(dict(id=m.group(1), title=m.group(4), project=m.group(6)))
    return tasks


# Con todos los estados: «en curso» lleva un espacio. [pomodoros] es «[hechos/estimados]» o «[hechos]».
ALL_LINE = re.compile(r'^\s*(\d+)\s+(en curso|\S+)\s+\S+\s+(\S+)\s+(.*?)\s+\[(\d+)(?:/(\d+))?\]\s+(.*\S)\s*$')
# Los estados de una tarea en `coffe`, en un solo sitio: las dos vistas Tareas los leen de aquí.
LIVE, PARKED, PENDING, DONE = 'en curso', 'refri', 'pendiente', 'hecha'
OPEN_STATES = (LIVE, PARKED, PENDING)
ALL_STATES = OPEN_STATES + (DONE,)
STATE_ORDER = {LIVE: 0, PARKED: 1, PENDING: 2, DONE: 3}
PRIORITY_ORDER = {'alta': 0, 'media': 1, 'baja': 2}
MARKS = {'alta': '▲', 'media': '◆', 'baja': '▽'}         # la prioridad, en las dos vistas Tareas
EMPTY_ALL = 'Sin tareas en coffe. Crea una con: coffe task add "título"'


def parse_all(text):
    """`coffe task list` -> todas, con su estado: [dict(id, state, priority, title, done, estimate, project)].
    Las apartadas («descartada»…) vienen tal cual: la vista decide si las enseña."""
    tasks = []
    for line in text.splitlines():
        m = ALL_LINE.match(line)
        if m:
            tasks.append(dict(id=m.group(1), state=m.group(2), priority=m.group(3), title=m.group(4),
                              done=int(m.group(5)), estimate=int(m.group(6) or 0), project=m.group(7)))
    return tasks


def by_project(tasks, states=OPEN_STATES, query=''):
    """Agrupa por proyecto -> [(proyecto, [tareas])]. Dentro, en curso primero y luego por prioridad;
    los proyectos con algo en curso van arriba y el resto por nombre. `query` filtra por título o proyecto."""
    query = query.strip().lower()
    groups = {}
    for t in tasks:
        if t['state'] in states and (not query or query in t['title'].lower() or query in t['project'].lower()):
            groups.setdefault(t['project'], []).append(t)
    for items in groups.values():
        items.sort(key=lambda t: (STATE_ORDER.get(t['state'], 9), PRIORITY_ORDER.get(t['priority'], 9), int(t['id'])))
    return sorted(groups.items(), key=lambda g: (min(STATE_ORDER.get(t['state'], 9) for t in g[1]) > 1, g[0].lower()))


def parse_projects(text):
    """La salida de `coffe project list` -> {'personal / apunte': '/ruta/del/repo'}.
    El árbol viene sangrado de dos en dos; la ruta de un nodo es la de sus
    padres, igual que la columna de proyecto de `coffe task list`."""
    found, names = {}, []
    for line in text.splitlines():
        m = re.match(r'^(\s*)\[\d+\]\s+(.+?)(?:\s+←\s+(\S.*))?\s*$', line)
        if not m:
            continue
        depth = len(m.group(1)) // 2
        names[depth:] = [m.group(2)]
        if m.group(3):
            found[' / '.join(names)] = m.group(3)
    return found


def describe(status):
    """El `status --json` de `coffe` -> lo que pinta la vista, o None sin datos."""
    if not isinstance(status, dict):
        return None
    phase = status.get('phase') or 'idle'
    task = status.get('task')
    title = task.get('title') if isinstance(task, dict) else task
    parked = status.get('parked')
    return dict(phase=phase, text=PHASES.get(phase, phase), clock=clock(status.get('remaining_secs')),
                progress=float(status.get('progress') or 0.0),
                task=str(title) if title else '',
                parked=bool(parked), today=int(status.get('pomodoros_hoy') or 0),
                cycle=int(status.get('completed_since_long_break') or 0),
                cycle_of=int(status.get('long_break_every') or 4),
                running=phase != 'idle')


def cup(status):
    """La taza de `coffe` para este estado: (cómo está, cuánto café queda de 0 a 1).
    En foco se vacía, en el descanso se llena y en el refri se queda a medias."""
    if status is None:
        return 'fria', .3
    phase, progress = status['phase'], min(1.0, max(0.0, status['progress']))
    if phase in FOCUS_PHASES:
        return ('vaciando' if phase == 'focus' else 'repaso'), 1 - progress
    if phase in BREAKS:
        return 'llenando', progress
    return ('refri', .55) if status['parked'] else ('vacia', 0.0)


def of_project(tasks, root):
    """Las tareas del proyecto de la carpeta `root`: las de su repo o de un repo que la contiene."""
    root = root.rstrip('/')
    return [t for t in tasks if t.get('repo') and (root == t['repo'].rstrip('/') or root.startswith(t['repo'].rstrip('/') + '/'))]


def run(*args):
    """Una orden a `coffe`. Devuelve (ok, lo que dijo)."""
    if not shutil.which('coffe'):
        return False, 'No está instalado coffe'
    try:
        out = subprocess.run(['coffe', *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as err:
        return False, str(err)
    return out.returncode == 0, (out.stdout + out.stderr).strip()


def snapshot():
    ok, text = run('status', '--json')
    try:
        status = json.loads(text) if ok else None
    except ValueError:
        status = None
    return status


class Watcher:
    """Pregunta a `coffe` en un hilo: el dibujo nunca espera a un subproceso.
    `read()` devuelve (estado, tareas) con lo último que se supo; el estado es
    None si el reloj no responde."""

    def __init__(self):
        self.status, self.tasks = None, []
        self.all_tasks = []             # con todos los estados: la vista Tareas
        self.repos = {}
        self.tasks_loaded = False       # ya contestó `coffe task list` alguna vez (bien o mal)
        self.tasks_why = ''             # por qué falló la última vez, o ''
        self.at = self.tasks_at = 0.0
        self.busy = False

    def read(self):
        now = time.monotonic()
        if not self.busy and now - self.at >= EVERY:
            self.busy, self.at = True, now
            threading.Thread(target=self._fetch, args=(now - self.tasks_at >= TASKS_EVERY,),
                             daemon=True).start()
        return describe(self.status), [dict(t, repo=self.repos.get(t['project'], '')) for t in self.tasks]

    def read_all(self):
        """Todas las tareas de `coffe` (cualquier estado), con el repo de su proyecto si lo tiene."""
        self.read()
        return [dict(t, repo=self.repos.get(t['project'], '')) for t in self.all_tasks]

    def refresh(self):
        self.at = self.tasks_at = 0.0

    def tasks_state(self):
        """('loading', '') hasta que `coffe` contesta, ('error', por qué) si falló y ('ok', '') si no."""
        if self.tasks_why:
            return 'error', self.tasks_why
        return ('ok', '') if self.tasks_loaded else ('loading', '')

    def project_of(self, root):
        """El proyecto de `coffe` de la carpeta `root` (el de repo más hondo que la contiene), o ''."""
        found = [(len(repo), name) for name, repo in self.repos.items() if of_project([dict(repo=repo)], root)]
        return max(found)[1] if found else ''

    def _fetch(self, with_tasks):
        try:
            self.status = snapshot()
            if with_tasks:
                # Los repos antes que las tareas: una vista que lea entre medias ya ve cada tarea con su repo.
                ok_repos, repos = run('project', 'list')
                ok, text = run('task', 'list')
                if ok_repos:
                    self.repos = parse_projects(repos)
                if ok:
                    self.tasks, self.tasks_at = parse_tasks(text), time.monotonic()     # todas: cada vista filtra y recorta
                    self.all_tasks = parse_all(text)
                self.tasks_why = '' if ok else (text or 'coffe no contesta')
                self.tasks_loaded = True
        finally:
            self.busy = False
