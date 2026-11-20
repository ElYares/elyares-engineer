"""Tus servidores: los `Host` de `~/.ssh/config` y cómo abrir uno en Ghostty.

Solo lee los alias. No guarda ni muestra direcciones, usuarios ni llaves, y no escribe
`~/.ssh/config` nunca. Abrir un servidor lanza `ghostty -e ssh <alias>`: la terminal es la de
siempre y quien teclea eres tú; la app no escribe nada dentro de ella.

Se descartan los `Host` que no son servidores: comodines, y los de git (`github.com`,
`gitlab.com`, `bitbucket.org` o `User git`, como `github-work`).
"""

import os
import re
import subprocess

CONFIG = os.path.expanduser('~/.ssh/config')
GIT_HOSTS = ('github.com', 'gitlab.com', 'bitbucket.org', 'ssh.github.com')
ALIAS = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')       # sin «-» al inicio: nunca una opción de ssh
LINE = re.compile(r'^(\S+?)(?:\s*=\s*|\s+)(.*)$')          # «Clave valor» o «Clave=valor»; un «=» del valor no cuenta
MAX = 8                                                     # lo que cabe en el panel; el resto no sale


def parse(text):
    """Los alias de servidores de un `ssh_config`, en el orden del archivo y sin repetir."""
    blocks, current = [], None
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        split = LINE.match(line)
        if split is None:
            continue
        key, value = split.group(1).lower(), split.group(2).strip()
        if key == 'host':
            current = dict(aliases=value.split(), hostname='', user='')
            blocks.append(current)
        elif current is not None and key == 'hostname':
            current['hostname'] = value.lower()
        elif current is not None and key == 'user':
            current['user'] = value.lower()
        elif key == 'match':
            current = None                                  # un `Match` no es un alias: lo que siga no es de ningún Host
    found = []
    for block in blocks:
        if block['hostname'] in GIT_HOSTS or block['user'] == 'git':
            continue
        for alias in block['aliases']:
            if ALIAS.match(alias) and alias not in found:
                found.append(alias)
    return found


def hosts(path=None):
    """Los servidores de tu `~/.ssh/config`; vacío si no hay archivo o no se puede leer."""
    try:
        with open(path or CONFIG, encoding='utf-8', errors='replace') as fh:
            return parse(fh.read())
    except OSError:
        return []


def command(alias):
    """La orden que abre `alias` en Ghostty, en su propio scope de systemd para que un `reload` de la isla
    no cierre la terminal; None si el alias no es un servidor de la lista."""
    if alias not in hosts():
        return None
    return ['systemd-run', '--user', '--scope', '--quiet', 'ghostty', '-e', 'ssh', alias]


def connect(alias):
    """Abre `alias` en una terminal nueva. Devuelve si pudo lanzarla (no si la conexión sale bien)."""
    argv = command(alias)
    if argv is None:
        return False
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        return False
    return True
