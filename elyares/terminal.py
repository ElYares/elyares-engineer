"""La terminal de la ventana: una sesión de tmux por proyecto, en su propio servidor.

El widget de terminal (`terminalpanel.py`) solo se engancha a una sesión; las
sesiones viven en un servidor de tmux aparte (`-L elyares`) lanzado con su propio
scope de systemd. Así `ssh`, un servidor de desarrollo o lo que se haya
levantado sobrevive a `elyares-ctl reload`: sin el scope, el servicio mata todo
su grupo al reiniciarse. El servidor es otro que el de tmux de Yared, así que no
aparece en «Sesiones» ni tropieza con su configuración de sesión.

Nada aquí escribe en la terminal: lo que se teclea ahí lo teclea Yared.
"""

import hashlib
import os
import re
import shutil
import subprocess

SOCKET = 'elyares'
SIZE = ('-x', '200', '-y', '50')      # tamaño con el que nace la sesión; el cliente la ajusta al engancharse


def session_name(root):
    """Un nombre de sesión por carpeta: el de la carpeta y un trozo de su ruta, para que dos
    proyectos que se llamen igual no compartan sesión. tmux no admite «:» ni «.»."""
    root = os.path.realpath(root)
    base = re.sub(r'[^A-Za-z0-9_-]+', '-', os.path.basename(root.rstrip('/')) or 'raiz').strip('-') or 'raiz'
    return f'{base}-{hashlib.sha1(root.encode()).hexdigest()[:6]}'


def _tmux(*args, **kw):
    return subprocess.run(['tmux', '-L', SOCKET, *args], capture_output=True, text=True, timeout=10, **kw)


def has(name):
    try:
        return _tmux('has-session', '-t', f'={name}').returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure(root):
    """Deja viva la sesión de esa carpeta. Devuelve (nombre, '') o (nombre, por qué no se pudo)."""
    name = session_name(root)
    if not shutil.which('tmux'):
        return name, 'No está instalado tmux'
    if not os.path.isdir(root):
        return name, 'La carpeta del proyecto ya no existe'
    if has(name):
        return name, ''
    cmd = ['tmux', '-L', SOCKET, 'new-session', '-d', '-s', name, '-c', root, *SIZE]
    if shutil.which('systemd-run'):
        # Con scope propio: el servidor no cuelga del servicio y sobrevive al reload.
        cmd = ['systemd-run', '--user', '--scope', '--quiet', f'--unit=elyares-tmux-{os.getpid()}-{name}', *cmd]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as err:
        return name, str(err)
    if out.returncode != 0:
        return name, (out.stderr or out.stdout).strip() or 'tmux no pudo crear la sesión'
    return name, ''


def attach_argv(name):
    """El comando que engancha un cliente a la sesión (lo corre el widget de terminal)."""
    return ['tmux', '-L', SOCKET, 'attach-session', '-t', f'={name}']
