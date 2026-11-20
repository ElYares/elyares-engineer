"""La vista Pomodoro: lo que dice `coffe` y las órdenes que se le dan.

El reloj lo manda el daemon de `coffe`; aquí solo se le pregunta
(`coffe status --json`, `coffe task list`) y se le piden cosas (`coffe start`,
`pause`, `void`, `done`). Nunca se escribe su estado.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time

EVERY = 1.0               # cada cuánto se le pregunta al reloj mientras la vista está a la vista
TASKS_EVERY = 10.0        # la lista de tareas cambia menos
MAX_TASKS = 12
DB = os.path.expanduser('~/.local/share/coffe/coffe.db')          # la base de coffe: aquí solo se LEE
VAULT = os.path.expanduser('~/develop/docs/obsidean-vault-personal')   # de donde cuelgan los `vault_note` de las tareas
DESC_MAX = 2000                   # lo que se guarda de una descripción
FOCUS_PHASES = ('focus', 'overlearning')
PHASES = {'idle': 'Parado', 'focus': 'En foco', 'overlearning': 'En foco',
          'break': 'Descanso', 'break-long': 'Descanso largo'}
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
    task_id = task.get('id') if isinstance(task, dict) else None
    parked = status.get('parked')
    return dict(phase=phase, text=PHASES.get(phase, phase), clock=clock(status.get('remaining_secs')),
                progress=float(status.get('progress') or 0.0),
                task=str(title) if title else '', task_id=str(task_id) if task_id is not None else '',
                parked=bool(parked), today=int(status.get('pomodoros_hoy') or 0),
                cycle=int(status.get('completed_since_long_break') or 0),
                cycle_of=int(status.get('long_break_every') or 4),
                running=phase != 'idle')


def _db_rows(sql, args=()):
    """Lee la base de coffe en solo lectura. Sin base o con un error, no hay filas."""
    try:
        con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=1)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []


def read_titles():
    """{id: título completo} de las tareas: `coffe task list` los corta a ~28 letras."""
    return {str(i): t for i, t in _db_rows('SELECT id, title FROM tasks WHERE state != ?', ('archived',))}


def vault_story(rel):
    """La «Historia» de una nota del vault (lo que sigue a `## Historia`, en una línea), o ''."""
    try:
        with open(os.path.join(VAULT, rel), encoding='utf-8') as f:
            text = f.read()
    except (OSError, ValueError):
        return ''
    body, found = [], False
    for line in text.splitlines():
        if line.startswith('## '):
            if found:
                break
            found = line.strip().lower() == '## historia'
        elif found and line.strip():
            body.append(line.strip().replace('**', ''))
    return ' '.join(body)[:DESC_MAX]


def format_description(text):
    """Una descripción con cada paso en su línea: lo que ya viene en líneas se queda, y un «1) … 2) …» corrido
    se parte en renglones. Sin pasos numerados, el texto no cambia."""
    text = re.sub(r'[ \t]+(?=\d+[).]\s)', '\n', text.strip()) if '\n' not in text.strip() else text.strip()
    return '\n'.join(line.strip() for line in text.splitlines() if line.strip())


def task_info(task_id):
    """Lo que dice la burbuja de una tarea: título completo, proyecto, estimación y descripción (sus
    notas en coffe; sin ellas, la «Historia» de su nota del vault). None si la tarea no existe."""
    rows = _db_rows('SELECT t.title, t.notes, t.estimate_pomodoros, t.vault_note, p.name FROM tasks t '
                    'JOIN projects p ON p.id = t.project_id WHERE t.id = ?', (task_id,))
    if not rows:
        return None
    title, notes, estimate, vault_note, project = rows[0]
    text = format_description((notes or '').strip()[:DESC_MAX] or (vault_story(vault_note) if vault_note else ''))
    return dict(id=str(task_id), title=title, project=project or '', estimate=estimate or 0, text=text)


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
    `read()` devuelve (estado, tareas) con lo último que se supo (`limit` corta la lista: la ventana
    muestra las primeras 12; la isla pide todas y filtra por proyecto, o las del suyo no saldrían); el estado es
    None si el reloj no responde."""

    def __init__(self):
        self.status, self.tasks = None, []
        self.titles = {}
        self.repos = {}
        self.at = self.tasks_at = 0.0
        self.busy = False

    def read(self, limit=MAX_TASKS):
        now = time.monotonic()
        if not self.busy and now - self.at >= EVERY:
            self.busy, self.at = True, now
            threading.Thread(target=self._fetch, args=(now - self.tasks_at >= TASKS_EVERY,),
                             daemon=True).start()
        return describe(self.status), [dict(t, title=self.titles.get(t['id'], t['title']), repo=self.repos.get(t['project'], ''))
                                       for t in self.tasks[:limit]]

    def refresh(self):
        self.at = self.tasks_at = 0.0

    def _fetch(self, with_tasks):
        try:
            self.status = snapshot()
            if with_tasks:
                ok, text = run('task', 'list')
                if ok:
                    self.tasks, self.tasks_at = parse_tasks(text), time.monotonic()
                    self.titles = read_titles()
                ok, text = run('project', 'list')
                if ok:
                    self.repos = parse_projects(text)
        finally:
            self.busy = False
