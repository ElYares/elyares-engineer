"""Lo que el editor muestra de un repositorio: la rama y qué archivos cambiaron.

Solo lee: nunca escribe en el repositorio. Abrir y editar el archivo es cosa de nvim.
"""

import os
import subprocess
import threading
import time
from collections import namedtuple

EVERY = 2.0               # cada cuánto se mira `git status` mientras el editor está a la vista
MAX_FILES = 200
State = namedtuple('State', 'branch files root chosen', defaults=('', None, '', ''))
LABELS = {'M': 'modificado', 'A': 'nuevo', 'D': 'borrado', 'R': 'renombrado', '?': 'sin seguir', 'U': 'en conflicto'}


def _git(root, *args):
    """La salida de `git -C root …`, o None si falla o no hay git."""
    try:
        out = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def branch(root):
    """La rama (o el hash corto si está suelta); '' si la carpeta no es un repositorio."""
    name = _git(root, 'rev-parse', '--abbrev-ref', 'HEAD')
    return (name or '').strip()


def parse_status(text):
    """`git status --porcelain -z` -> [(código, ruta)], con un código de una letra de LABELS."""
    items, parts = [], text.split('\0')
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        xy, path = entry[:2], entry[3:]
        if 'R' in xy or 'C' in xy:
            i += 1                      # el original de un renombrado viene aparte
        code = '?' if xy == '??' else 'U' if 'U' in xy or xy in ('AA', 'DD') else \
            next((c for c in 'RDAM' if c in xy), 'M')
        items.append((code, path))
    return items[:MAX_FILES]


def changed(root):
    """Los archivos con cambios, o None si `root` no es un repositorio."""
    out = _git(root, 'status', '--porcelain', '-z', '--untracked-files=all')
    return None if out is None else parse_status(out)


class Watcher:
    """Mira `git status` en un hilo: el dibujo nunca espera a un subproceso.
    `read()` devuelve un `State`; `files` es None si la carpeta no es un repositorio.
    `chosen` es el último archivo en el que se hizo clic (la lista lo marca)."""

    def __init__(self):
        self.root = ''
        self.state = State()
        self.at = 0.0
        self.busy = False

    def watch(self, root):
        if root != self.root:
            self.root, self.state, self.at = root, State(root=root), 0.0

    def choose(self, path):
        self.state = self.state._replace(chosen=path)

    def read(self):
        now = time.monotonic()
        if self.root and not self.busy and now - self.at >= EVERY:
            self.busy, self.at = True, now
            threading.Thread(target=self._fetch, args=(self.root,), daemon=True).start()
        return self.state

    def refresh(self):
        self.at = 0.0

    def _fetch(self, root):
        try:
            files, name = changed(root), branch(root)
            if root == self.root:
                self.state = State(name, files, root, self.state.chosen)
        finally:
            self.busy = False
