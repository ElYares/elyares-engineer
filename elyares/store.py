"""Las sesiones conocidas y las conversaciones del chat, para que sobrevivan
al reinicio del daemon.

Viven en `$XDG_RUNTIME_DIR/elyares-sessions.json`, junto al socket, y no en
`~/.config`: ese directorio se borra al apagar la máquina, igual que los panes
de tmux a los que apuntan las sesiones. Por lo mismo los tiempos se guardan en
el reloj monotónico tal cual: cuenta desde el arranque de la máquina, no del
daemon.

Las conversaciones del chat van al lado, en `elyares-chats.json`: con eso la
isla se puede volver a arrancar (`elyares-ctl reload`) sin perderlas. Solo las
lee quien las escribió: traen lo que se habló.
"""

import glob
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


def chats_path():
    return os.path.join(os.path.dirname(path()), 'elyares-chats.json')


def load_chats():
    try:
        with open(chats_path(), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_chats(data):
    p = chats_path()
    try:
        fd = os.open(p + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(p + '.tmp', p)
    except OSError:
        pass


def forget_usage():
    """Borra lo que `elyares-statusline` recuerda haber mandado ya.

    La barra de estado solo avisa cuando un porcentaje cambia, y lo apunta en
    `elyares-status-<sesión>`. Si el daemon no estaba cuando avisó, ese dato se
    perdió: sin esto no volvería a llegar hasta el siguiente cambio.
    """
    for f in glob.glob(os.path.join(os.path.dirname(path()), 'elyares-status-*')):
        try:
            os.unlink(f)
        except OSError:
            pass
