"""El fragmento de código que Claude está editando, para verlo en la isla.

`build()` toma lo que traen las herramientas de edición (Edit, MultiEdit,
Write, NotebookEdit) y arma una vista previa: el nombre del archivo, la línea
donde cae el cambio si se puede saber, y unas pocas líneas de diff. Es solo
para mirar: nada de aquí vuelve a Claude ni toca el archivo.
"""

import difflib
import os
from dataclasses import dataclass, field

MAX_LINES = 12            # líneas de diff que caben en la isla
CONTEXT = 1               # líneas iguales que se dejan alrededor de un cambio
MAX_FILE = 2 << 20        # no se busca la línea en archivos más grandes que esto


@dataclass
class Preview:
    file: str = ''
    line: int = 0                                 # línea del archivo donde empieza; 0 = no se sabe
    lines: list = field(default_factory=list)     # [(marca, texto)]: '+', '-' o ' '
    added: int = 0
    removed: int = 0
    more: int = 0                                 # líneas de diff que no cupieron
    edits: int = 1                                # cuántos cambios trae la herramienta

    @property
    def name(self):
        return os.path.basename(self.file) or self.file


def _split(text):
    return (text or '').expandtabs(4).splitlines()


def _diff(old, new):
    """Diff de dos fragmentos: ([(marca, texto)], línea del fragmento viejo
    donde empieza lo que se muestra). Deja poco contexto."""
    out, first = [], 0
    groups = list(difflib.SequenceMatcher(None, old, new, autojunk=False)
                  .get_grouped_opcodes(CONTEXT))
    if groups:
        first = groups[0][0][1]
    for group in groups:
        if out:
            out.append((' ', '⋯'))
        for tag, i1, i2, j1, j2 in group:
            if tag == 'equal':
                out += [(' ', line) for line in old[i1:i2]]
                continue
            out += [('-', line) for line in old[i1:i2]]
            out += [('+', line) for line in new[j1:j2]]
    return out, first


def _locate(path, fragment):
    """Línea (desde 1) donde empieza `fragment` en el archivo, o 0."""
    if not path or not fragment:
        return 0
    try:
        if os.path.getsize(path) > MAX_FILE:
            return 0
        with open(path, errors='replace') as f:
            text = f.read()
    except OSError:
        return 0
    at = text.find(fragment)
    return text.count('\n', 0, at) + 1 if at >= 0 else 0


def build(tool, tool_input):
    """La vista previa de una herramienta de edición, o None si no edita nada."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    path = ti.get('file_path') or ti.get('notebook_path') or ''
    edits = 1
    if tool == 'Edit':
        old, new = ti.get('old_string'), ti.get('new_string')
    elif tool == 'MultiEdit':
        changes = [e for e in ti.get('edits') or [] if isinstance(e, dict)]
        if not changes:
            return None
        # Solo el primero: es una vista previa, no el diff completo.
        old, new, edits = changes[0].get('old_string'), changes[0].get('new_string'), len(changes)
    elif tool == 'Write':
        old, new = '', ti.get('content')
    elif tool == 'NotebookEdit':
        old, new = '', ti.get('new_source')
    else:
        return None
    if not isinstance(new, str) or (not new and not old):
        return None
    old = old if isinstance(old, str) else ''
    lines, first = _diff(_split(old), _split(new))
    if not lines:
        return None
    start = _locate(path, old)
    return Preview(
        file=path, line=start + first if start else 0, lines=lines[:MAX_LINES],
        added=sum(1 for mark, _ in lines if mark == '+'),
        removed=sum(1 for mark, _ in lines if mark == '-'),
        more=max(0, len(lines) - MAX_LINES), edits=edits)
