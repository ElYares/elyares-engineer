"""Lo que el editor muestra de un repositorio: qué cambió, su diff y el archivo.

Solo lee. Nunca escribe en el repositorio ni en los archivos: el editor es un
visor de lo que está haciendo el agente (o tú desde otro sitio).
"""

import os
import subprocess
import threading
import time
from collections import namedtuple

EVERY = 2.0               # cada cuánto se mira `git status` mientras el editor está a la vista
MAX_BYTES = 1_000_000     # un archivo más grande se avisa, no se carga
MAX_FILES = 200
State = namedtuple('State', 'branch files root chosen text note diff', defaults=('', None, '', '', '', '', ''))
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


def diff(root, path, code='M'):
    """El diff de un archivo contra HEAD. Un archivo sin seguir se muestra entero como añadido."""
    if code == '?':
        try:
            out = subprocess.run(['git', '-C', root, 'diff', '--no-index', '--', '/dev/null', path],
                                 capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return ''
        return out.stdout           # `--no-index` sale con 1 cuando hay diferencias
    return _git(root, 'diff', 'HEAD', '--', path) or ''


def read(root, path):
    """(texto, nota): el contenido del archivo, o '' y por qué no se muestra."""
    full = os.path.realpath(os.path.join(root, path))
    if not full.startswith(os.path.realpath(root) + os.sep):
        return '', 'Fuera del proyecto'
    try:
        if os.path.getsize(full) > MAX_BYTES:
            return '', 'Archivo muy grande para mostrarlo'
        with open(full, 'rb') as fh:
            data = fh.read()
    except OSError:
        return '', 'El archivo ya no existe'
    if b'\0' in data:
        return '', 'Archivo binario'
    return data.decode('utf-8', 'replace'), ''


class Watcher:
    """Mira `git status` y el archivo elegido en un hilo: el dibujo nunca espera
    a un subproceso. `read()` devuelve un `State`; `files` es None si la carpeta
    no es un repositorio. Si el archivo elegido ya no está entre los cambios, se
    elige el primero."""

    def __init__(self):
        self.root = self.chosen = ''
        self.state = State()
        self.at = 0.0
        self.busy = False

    def watch(self, root):
        if root != self.root:
            self.root, self.chosen, self.state, self.at = root, '', State(root=root), 0.0

    def choose(self, path):
        if path != self.chosen:
            self.chosen, self.at = path, 0.0

    def read(self):
        now = time.monotonic()
        if self.root and not self.busy and now - self.at >= EVERY:
            self.busy, self.at = True, now
            threading.Thread(target=self._fetch, args=(self.root, self.chosen), daemon=True).start()
        return self.state

    def refresh(self):
        self.at = 0.0

    def _fetch(self, root, chosen):
        try:
            files, name = changed(root), branch(root)
            paths = [path for _code, path in files or []]
            chosen = chosen if chosen in paths else (paths[0] if paths else '')
            code = next((c for c, path in files or [] if path == chosen), 'M')
            text, note = read(root, chosen) if chosen else ('', '')
            if root == self.root:
                self.chosen = chosen
                self.state = State(name, files, root, chosen, text, note, diff(root, chosen, code) if chosen else '')
        finally:
            self.busy = False
