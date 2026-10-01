"""Las sesiones conocidas, para que sobrevivan al reinicio del daemon.

Viven en `$XDG_RUNTIME_DIR/elyares-sessions.json`, junto al socket, y no en
`~/.config`: ese directorio se borra al apagar la máquina, igual que los panes
de tmux a los que apuntan las sesiones. Por lo mismo los tiempos se guardan en
el reloj monotónico tal cual: cuenta desde el arranque de la máquina, no del
daemon.
"""

import json
import os


def path():
    base = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    return os.path.join(base, 'elyares-sessions.json')


def load():
    try:
        with open(path()) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def save(sessions):
    p = path()
    try:
        with open(p + '.tmp', 'w') as f:
            json.dump(sessions, f)
        os.replace(p + '.tmp', p)
    except OSError:
        pass
