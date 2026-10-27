"""Las sesiones de tmux como proyectos: qué hay abierto y a qué ventana saltar.

Cada sesión de tmux es un proyecto y cada una de sus ventanas, un lugar donde
puede vivir un `claude`. La isla ya sabe en qué pane corre cada sesión de
Claude (`Session.pane`): aquí solo se lista lo que tmux tiene y se cruza con
eso para decir en qué ventana hay un Claude y qué hace.

`snapshot()` pregunta a tmux (sin servidor devuelve []) y `jump()` lleva la
terminal a una ventana. Las sesiones ocultas (`_ssh-…`, de los popups) no
cuentan.
"""

import subprocess
import threading
import time

from . import actions

FIELDS = '#{session_name}\t#{window_index}\t#{window_name}\t#{pane_id}\t#{pane_current_command}\t#{pane_current_path}'
EVERY = 3.0                       # segundos entre consultas a tmux
# De más a menos urgente: lo que se muestra de una ventana con varios Claude.
URGENCY = ('permission', 'waiting', 'working', 'done', 'idle')


def snapshot():
    """Las sesiones de tmux: [{name, windows: [{index, name, panes: [(pane, comando, carpeta)]}]}]."""
    out = actions._run('tmux', 'list-panes', '-a', '-F', FIELDS)
    sessions = {}
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) != 6 or parts[0].startswith('_'):
            continue
        name, index, wname, pane, cmd, path = parts
        windows = sessions.setdefault(name, {})
        win = windows.setdefault(index, dict(index=index, name=wname, panes=[]))
        win['panes'].append((pane, cmd, path))
    return [dict(name=name, windows=sorted(windows.values(), key=lambda w: int(w['index']) if w['index'].isdigit() else 0))
            for name, windows in sorted(sessions.items())]


def _rank(state):
    return URGENCY.index(state) if state in URGENCY else len(URGENCY)


def merge(sessions, claude):
    """Cruza las sesiones de tmux con las de Claude. `claude`: [(pane, estado, [roles])].
    A cada ventana le pone `state` (el más urgente de sus Claude, o ''),
    `agents` (los subagentes trabajando, sin repetir) y a cada sesión `state`
    y `claudes` (cuántos Claude tiene)."""
    by_pane = {pane: (state, roles) for pane, state, roles in claude}
    for sess in sessions:
        total = 0
        for win in sess['windows']:
            mine = [by_pane[p] for p, _cmd, _path in win['panes'] if p in by_pane]
            win['state'] = min((state for state, _ in mine), key=_rank, default='')
            win['agents'] = list(dict.fromkeys(role for _, roles in mine for role in roles))
            total += len(mine)
        sess['claudes'] = total
        sess['state'] = min((w['state'] for w in sess['windows'] if w['state']), key=_rank, default='')
    return sessions


def jump(session, window):
    """Enfoca la terminal y lleva tmux a esa ventana (el cliente más reciente
    cambia de sesión si ninguno la tiene a la vista)."""
    target = f'={session}:{window}'
    actions._run('hyprctl', 'dispatch', 'focuswindow', f'class:{actions.TERM_CLASS}')
    clients = actions._real_clients(['tmux'])
    if clients and not any(s == session for _, _, s in clients):
        actions._run('tmux', 'switch-client', '-c', max(clients)[1], '-t', f'={session}')
    actions._run('tmux', 'select-window', '-t', target)


class Watcher:
    """Consulta a tmux en un hilo cada EVERY segundos: el dibujo nunca espera
    a un subproceso. `read()` devuelve lo último que se supo, o None si
    todavía no hubo consulta."""

    def __init__(self):
        self.data = None
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
        except (OSError, subprocess.SubprocessError):
            self.data = []
        finally:
            self.busy = False
