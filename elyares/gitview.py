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
MAX_TREE = 4000           # archivos que entran al árbol; un repositorio más grande se corta aquí
# `paths`: todos los archivos del proyecto (los que git conoce, sin lo ignorado); `stats`: {ruta: (líneas
# agregadas, quitadas)} de lo que cambió contra HEAD.
State = namedtuple('State', 'branch files root chosen paths stats', defaults=('', None, '', '', (), None))
LABELS = {'M': 'modificado', 'A': 'nuevo', 'D': 'borrado', 'R': 'renombrado', '?': 'sin seguir', 'U': 'en conflicto'}


def _git(root, *args):
    """La salida de `git -C root …`, o None si falla o no hay git. Un repositorio que llega de fuera
    puede traer `core.fsmonitor` en su config, que ejecuta un comando en cada `status`: se apaga.
    Y sin bloqueos opcionales: este `status` cada 2 s no le quita el índice a un commit del agente."""
    try:
        out = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', root, *args], capture_output=True,
                             text=True, timeout=10, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def inside(root, paths):
    """De unas rutas absolutas, las que están dentro de `root`, como rutas relativas y en el mismo orden."""
    base = os.path.realpath(root)
    found = []
    for path in paths:
        rel = os.path.relpath(os.path.realpath(path), base)
        if rel != '.' and not rel.startswith(os.pardir + os.sep) and rel != os.pardir and rel not in found:
            found.append(rel)
    return found


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


def tracked(root):
    """Todos los archivos del proyecto: los que git sigue y los nuevos, menos lo ignorado."""
    out = _git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    return sorted(set(p for p in (out or '').split('\0') if p))[:MAX_TREE]


def parse_numstat(text):
    """`git diff --numstat` -> {ruta: (agregadas, quitadas)}; los binarios cuentan 0 y 0."""
    stats = {}
    for line in text.splitlines():
        parts = line.split('\t', 2)
        if len(parts) == 3:
            stats[parts[2]] = tuple(int(n) if n.isdigit() else 0 for n in parts[:2])
    return stats


def numstat(root):
    """Las líneas agregadas y quitadas por archivo contra HEAD; {} si no hay HEAD todavía."""
    return parse_numstat(_git(root, 'diff', '--numstat', '--no-renames', 'HEAD') or '')


def tree_rows(paths, changes, expanded):
    """El árbol del proyecto como filas visibles: [dict(depth, name, path, dir, open, code, count)].

    `changes`: {ruta: código} de lo que cambió; una carpeta cuenta (`count`) los archivos cambiados que
    tiene debajo, para marcarla aunque esté cerrada. `expanded`: las carpetas abiertas. Primero las
    carpetas y luego los archivos, cada grupo por nombre."""
    root = {}
    for path in sorted(set(paths) | set(changes)):
        node = root
        *dirs, name = path.split('/')
        for d in dirs:
            node = node.setdefault(d, {})
        node[name] = None
    rows = []

    def count(node, prefix):
        return sum(count(sub, f'{prefix}{k}/') if sub is not None else (f'{prefix}{k}' in changes)
                   for k, sub in node.items())

    def walk(node, prefix, depth):
        for name in sorted(node, key=lambda k: (node[k] is None, k.lower())):
            path = prefix + name
            if node[name] is None:
                rows.append(dict(depth=depth, name=name, path=path, dir=False, open=False,
                                 code=changes.get(path, ''), count=0))
                continue
            is_open = path in expanded
            rows.append(dict(depth=depth, name=name, path=path, dir=True, open=is_open, code='',
                             count=count(node[name], path + '/')))
            if is_open:
                walk(node[name], path + '/', depth + 1)

    walk(root, '', 0)
    return rows


def parents(paths):
    """Las carpetas que contienen a esos archivos (todas las de la cadena): {'a', 'a/b'}."""
    found = set()
    for path in paths:
        parts = path.split('/')[:-1]
        for i in range(1, len(parts) + 1):
            found.add('/'.join(parts[:i]))
    return found


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
            paths, stats = (tracked(root), numstat(root)) if files is not None else ((), {})
            if root == self.root:
                self.state = State(name, files, root, self.state.chosen, paths, stats)
        finally:
            self.busy = False
