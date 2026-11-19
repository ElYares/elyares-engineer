"""Sugerir el mensaje de un commit y hacerlo, para el panel Git de la isla.

Junta lo que cambió (archivos, líneas y un diff recortado) y se lo pide a un modelo barato con
`claude -p`, con el estilo de los últimos commits del repo como ejemplo. Nunca usa `git add -A`: el
commit lleva los archivos que se listaron, uno por uno, y nunca los riesgosos (`.env`, llaves). Una
llamada a Claude no toca el repo: corre fuera de él, sin herramientas, sin sesión guardada y sin
avisarle a la isla (sin el socket de sus hooks, para que no aparezca como una sesión).
"""

import fnmatch
import os
import subprocess
from collections import namedtuple

from . import gitflow

MODEL = 'haiku'
DIFF_CHARS = 14000               # lo más que se manda del diff
RECENT = 12                      # asuntos recientes que se mandan como ejemplo de estilo
LINES_MAX = 300                  # el tope de líneas por commit (CLAUDE.md del repo)
TIMEOUT = 90
RISKY = ('.env', '.env.*', '*.pem', '*.key', 'id_rsa*', 'id_ed25519*', '*credentials*', '*secret*', '*.p12', '*.pfx')
TRAILER = 'Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>'
PROMPT = """Redacta el mensaje de un commit de git para estos cambios. Responde SOLO con el mensaje, sin comillas ni bloque de código.

Reglas:
- Primera línea: el estilo de los commits recientes de abajo (mismo idioma, mismos tipos y, si lo usan, mismo scope y acentos), en minúscula, sin punto final, de 72 caracteres o menos.
- Si el porqué no es obvio, una línea en blanco y un cuerpo corto con viñetas: por qué era necesario, no qué archivos tocaste.
- Un `fix` dice qué fallaba y por qué.
- No inventes nada que no esté en el diff.

Commits recientes (de ejemplo de estilo):
{recent}

Archivos cambiados ({count}, {lines} líneas):
{files}

Diff (recortado):
{diff}
"""

# `files`: las rutas que entrarían al commit; `risky`: las que se dejan fuera; `lines`: agregadas más quitadas.
Changes = namedtuple('Changes', 'files risky lines')
# `text`: el mensaje (con su trailer); `changes`: lo que se commitearía; `error`: por qué no hubo mensaje.
Suggestion = namedtuple('Suggestion', 'text changes error', defaults=('', None, ''))


def is_risky(path):
    name = os.path.basename(path).lower()
    return any(fnmatch.fnmatch(name, pattern) for pattern in RISKY)


def changes(root):
    """Lo que cambió en el árbol: rutas (los renombrados cuentan por su destino), riesgosas aparte y líneas."""
    out = gitflow._git(root, 'status', '--porcelain', '-z', '--untracked-files=all') or ''
    paths, parts, i = [], out.split('\0'), 0       # un renombrado cuenta con sus dos rutas: si no, el commit lo partiría
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in 'RC':
            if entry[0] == 'R' and i < len(parts) and parts[i]:
                paths.append(parts[i])   # con -z, el origen de un renombrado viene aparte
            i += 1
    risky = [p for p in paths if is_risky(p)]
    files = [p for p in paths if p not in risky]
    lines = 0
    for add, rem, _name in (row.split('\t', 2) for row in (gitflow._git(root, 'diff', 'HEAD', '--numstat') or '').splitlines()
                            if row.count('\t') >= 2):
        lines += (int(add) if add.isdigit() else 0) + (int(rem) if rem.isdigit() else 0)
    tracked = set((gitflow._git(root, 'ls-files') or '').splitlines())
    for path in files:
        if path not in tracked:          # un archivo nuevo: sus líneas, con tope para no leer un binario enorme
            try:
                with open(os.path.join(root, path), 'rb') as f:
                    lines += f.read(400000).count(b'\n')
            except OSError:
                pass
    return Changes(files, risky, lines)


def build_prompt(root, found):
    recent = (gitflow._git(root, 'log', f'-{RECENT}', '--format=%s') or '').strip() or '(sin commits todavía)'
    diff = (gitflow._git(root, 'diff', 'HEAD', '--', *found.files) or '')[:DIFF_CHARS] if found.files else ''
    return PROMPT.format(recent=recent, count=len(found.files), lines=found.lines,
                         files='\n'.join(f'- {p}' for p in found.files[:60]), diff=diff or '(archivos nuevos sin diff)')


def clean(text):
    """El mensaje tal cual lo escribió el modelo, sin cercas de código ni la advertencia de la sesión."""
    lines = [line for line in (text or '').strip().splitlines() if not line.startswith('Warning:')]
    msg = '\n'.join(lines).strip()
    if msg.startswith('```'):
        msg = '\n'.join(msg.splitlines()[1:]).rstrip('`').strip()
    return msg.strip('"').strip()


def suggest(root, run=subprocess.run):
    """Pide el mensaje. Nunca falla con una excepción: devuelve `error`."""
    found = changes(root)
    if not found.files:
        return Suggestion('', found, 'no hay nada que commitear' + (' (solo archivos riesgosos)' if found.risky else ''))
    env = {**os.environ, 'XDG_RUNTIME_DIR': '/nonexistent'}         # sin el socket de la isla: los hooks salen en silencio
    try:
        out = run(['claude', '-p', '--model', MODEL, '--tools', '', '--no-session-persistence', '--disable-slash-commands'],
                  input=build_prompt(root, found), capture_output=True, text=True, timeout=TIMEOUT, cwd='/tmp', env=env)
    except (OSError, subprocess.SubprocessError) as err:
        return Suggestion('', found, f'claude no contestó: {err}')
    text = clean(out.stdout)
    if out.returncode != 0 or not text:
        return Suggestion('', found, 'claude no devolvió un mensaje')
    return Suggestion(f'{text}\n\n{TRAILER}', found)


def commit(root, text, files):
    """Agrega esos archivos, uno por uno, y commitea con ese mensaje. (ok, lo que dijo git)."""
    files = [f for f in files if not is_risky(f)]
    if not (text.strip() and files):
        return False, 'falta el mensaje o los archivos'
    ok, said = gitflow._ok(root, 'add', '--', *files)
    if not ok:
        return False, said
    try:
        out = subprocess.run(['git', '-C', root, 'commit', '-q', '-F', '-', '--', *files], input=text, capture_output=True, text=True,
                             timeout=120)
    except (OSError, subprocess.SubprocessError) as err:
        return False, str(err)
    return out.returncode == 0, (out.stderr or out.stdout).strip() or 'commit hecho'
