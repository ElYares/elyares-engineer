"""Las fuentes de elyares-engineer: de dónde le llega lo que muestra.

Cada una es una pastilla al pie de la isla abierta a mano, y una línea de
`elyares-ctl status`. Menos Claude, todas se apagan desde ahí (o en
`settings.json`, con su misma clave).

    claude    hooks de Claude Code: las sesiones
    devherd   DevHerd Observe: errores y contenedores
    coffe     el pomodoro: modo foco y descansos
    github    checks de los PRs y revisiones pedidas
    terminal  comandos largos de bash
    usage     contexto y límite de 5 h, por la barra de estado

El estado de una fuente prendida es `on` (responde), `bad` (no responde o le
falta instalarse) o `unknown` (todavía no se sabe).

Con el cursor sobre su pastilla sale una burbuja con lo que se sabe de ella.
Una fuente que no responde dice ahí por qué (`why`) y qué hacer (`fix`).
"""

import json
import os

SOURCES = (('claude', 'Claude'), ('devherd', 'devherd'), ('coffe', 'coffe'),
           ('github', 'GitHub'), ('terminal', 'terminal'), ('usage', 'uso'))
LABELS = dict(SOURCES)
STATE_TEXT = {'on': 'conectada', 'off': 'apagada', 'bad': 'con problemas', 'unknown': 'sin datos'}
# Qué trae cada fuente, para la burbuja que sale al pasar el cursor por su pastilla.
ABOUT = {'claude': 'Sesiones de Claude Code y sus permisos',
         'devherd': 'Errores y contenedores de DevHerd Observe',
         'coffe': 'Pomodoro: modo foco y descansos',
         'github': 'Checks de tus PRs y revisiones pedidas',
         'terminal': 'Comandos de bash de 30 s o más, y pruebas en vivo',
         'usage': 'Contexto de cada sesión y límite de 5 h'}

# Por qué está en rojo una fuente a la que le falta su enganche. Las tres las
# pone install.sh.
MISSING = {'claude': 'Faltan los hooks de elyares-engineer en ~/.claude/settings.json',
           'usage': 'La barra de estado de Claude no pasa por elyares-statusline',
           'terminal': 'Falta el bloque de elyares-engineer en ~/.bashrc'}
MISSING_FIX = 'Corre install.sh en el repo de elyares-engineer'

# Con qué empieza el id de las alertas de cada fuente, para quitarlas al apagarla.
PREFIXES = {'devherd': ('devherd:',), 'github': ('gh:',), 'coffe': ('coffe',),
            'terminal': ('cmd:',), 'usage': ('ctx:', 'limit:')}


def source_of(msg):
    """De qué fuente viene un mensaje del socket."""
    ev, sid = msg.get('event'), str(msg.get('session_id') or '')
    if ev in ('cmd-start', 'cmd-done'):
        return 'terminal'
    if ev == 'status':
        return 'usage'
    if ev == 'focus':
        return 'coffe'
    for key, prefixes in PREFIXES.items():
        if sid.startswith(prefixes):
            return key
    return 'claude'


def _read(path):
    try:
        with open(os.path.expanduser(path)) as f:
            return f.read()
    except OSError:
        return ''


def installed():
    """Las fuentes que dependen de install.sh, y si están puestas: {clave: bool}.

    Estas tres no tienen a quién preguntarle si viven: mandan cuando pasa
    algo. Lo único comprobable es que su enganche esté donde debe.
    """
    try:
        claude = json.loads(_read('~/.claude/settings.json') or '{}')
    except ValueError:
        claude = {}
    hooks = json.dumps(claude.get('hooks') or {})
    bar = (claude.get('statusLine') or {}).get('command') or ''
    return {'claude': 'elyares-hook' in hooks,
            'usage': bar.endswith('elyares-statusline'),
            'terminal': '>>> elyares-engineer >>>' in _read('~/.bashrc')}
