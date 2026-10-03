"""Tus proyectos, como los ve el sidebar de tmux (`tmux-workspace`).

Un workspace es una carpeta de primer nivel de `~/develop` (work, personal,
clients, labs…) y un proyecto, una carpeta dentro de él. Un proyecto está
abierto si tiene sesión de tmux: la que se abrió en su carpeta (o más adentro),
se llame como se llame. Las sesiones de fuera de `~/develop` van al final,
sueltas, como «otras» en el sidebar.

Se siguen sus mismas reglas para que la isla y tmux enseñen lo mismo: no salen
los workspaces que empiezan por `_` o `.`, ni los de
`~/.config/tmux/workspaces.ignore`, ni las sesiones ocultas (`_*`); el orden es
fijo, alfabético, y el estado lo dice la marca y no la posición.
"""

import os
from dataclasses import dataclass

from . import chat

ROOT = '~/develop'
IGNORE = '~/.config/tmux/workspaces.ignore'
LOOSE = 'otras'           # el grupo de las sesiones de fuera de ~/develop


@dataclass
class Project:
    name: str             # el de su carpeta (o el de su sesión, si es de las sueltas)
    path: str
    ws: str = ''          # su workspace; '' si está fuera de ~/develop
    session: str = ''     # su sesión de tmux, si está abierto
    activity: int = 0     # cuándo se usó esa sesión por última vez
    here: bool = False    # es la sesión de tmux en la que estás
    key: str = ''         # cómo se le nombra sin confundirlo con otro: su nombre o «workspace/nombre»

    @property
    def open(self):
        return bool(self.session)

    def holds(self, cwd):
        """¿Es de este proyecto esa carpeta?"""
        return bool(cwd) and (cwd == self.path or cwd.startswith(self.path.rstrip('/') + '/'))


def _ignored(path):
    try:
        with open(os.path.expanduser(path), encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    except OSError:
        return set()


def _dirs(path):
    """Las carpetas de una carpeta, sin las ocultas y por orden alfabético."""
    try:
        with os.scandir(path) as entries:
            names = [e.name for e in entries if e.is_dir() and not e.name.startswith('.')]
    except OSError:
        return []
    return sorted(names, key=str.lower)


def scan(root=ROOT, ignore=IGNORE):
    """Los proyectos de `root`: [(workspace, carpeta)]."""
    root, skip = os.path.expanduser(root), _ignored(ignore)
    return [(ws, os.path.join(root, ws, name))
            for ws in _dirs(root) if not ws.startswith('_') and ws not in skip
            for name in _dirs(os.path.join(root, ws))]


def listing(root=ROOT, ignore=IGNORE, tmux=None):
    """Todos tus proyectos, con cuáles están abiertos en tmux y en cuál estás:
    los de `root` por workspace y, al final, las sesiones sueltas."""
    tmux = tmux or chat._tmux
    current = (-1, '')
    for line in tmux('list-clients', '-F', '#{client_activity}\t#{client_session}'):
        when, _, name = line.partition('\t')
        if when.isdigit() and name and not name.startswith('_') and int(when) > current[0]:
            current = (int(when), name)
    found = scan(root, ignore)
    by_path = {path: ws for ws, path in found}
    sessions, loose = {}, []
    for line in tmux('list-sessions', '-F', '#{session_activity}\t#{session_name}\t#{session_path}'):
        when, _, rest = line.partition('\t')
        name, _, path = rest.partition('\t')
        if not name or name.startswith('_'):
            continue
        entry = (name == current[1], int(when) if when.isdigit() else 0, name)
        home = next((p for p in by_path if path == p or path.startswith(p + '/')), None)
        if home is None:
            loose.append((entry, path))
        elif home not in sessions or entry > sessions[home]:
            sessions[home] = entry      # dos sesiones en la misma carpeta: gana en la que estás
    out = []
    for ws, path in found:
        here, when, name = sessions.get(path, (False, 0, ''))
        out.append(Project(os.path.basename(path), path, ws, name, when, here))
    for (here, when, name), path in sorted(loose, key=lambda it: it[0][2].lower()):
        out.append(Project(name, path.rstrip('/') or '/', '', name, when, here))
    names = [p.name for p in out]
    for p in out:
        p.key = p.name if names.count(p.name) == 1 else f'{p.ws or LOOSE}/{p.name}'
    return out
