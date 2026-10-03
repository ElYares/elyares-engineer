"""Los workflows: cadenas de agentes de la familia, guardadas con nombre.

Un workflow es una lista ordenada de pasos; cada paso es un agente y lo que se
le pide. Se lanza sobre un proyecto, el suyo o, si no tiene (`project` vacío),
aquel en el que estés al lanzarlo: el primer paso recibe su instrucción y
cada uno de los siguientes, además, lo que contestó el anterior. Qué pasa si
un paso falla lo dice el propio workflow (`on_fail`): parar ahí o seguir.

Aquí está lo que no necesita pantalla: el workflow y dónde se guarda
(`load`, `save`), el borrador del editor (`Draft`) y la marcha de una
ejecución (`Run`). El panel y quién le habla a cada agente están en
`workflowview`.

Se guardan en `~/.config/elyares-engineer/workflows.json`, junto a las
preferencias: son tuyos y sobreviven al apagado, no como las sesiones.
"""

import copy
import json
import os
import time
from dataclasses import asdict, dataclass, field

from . import settings, state

STOP, GO = 'stop', 'go'       # si un paso falla: parar ahí, o seguir con el siguiente
# Un paso puede acabar su turno sin haber hecho lo que se le pidió («no pude
# abrir el PR», «develop no está al día»). La isla solo ve que el turno acabó,
# así que a cada paso se le dice cómo avisar: con esta marca al final.
FAILED = 'PASO FALLIDO:'
RULE = ('\n\n---\nEsto es un paso de un workflow, y de lo que contestes depende que corra el siguiente. '
        'Si no pudiste hacer lo que se pide, o lo que había que comprobar no se cumple, acaba tu respuesta '
        f'con una línea que empiece por `{FAILED}` y el motivo en una frase. Si salió bien, no la pongas.')
VERDICT_LINES = 4             # la marca va al final: se busca en las últimas líneas de la respuesta
# Cómo va un paso de una ejecución.
WAIT, RUNNING, OK, BAD = 'wait', 'run', 'ok', 'bad'


@dataclass
class Step:
    agent: str = state.MAIN_AGENT     # el nombre entero: elyares-engineer, elyares-reviewer…
    text: str = ''                    # lo que se le pide


@dataclass
class Workflow:
    name: str = ''
    project: str = ''                 # la carpeta del proyecto sobre el que se lanza; '' es donde estés al lanzarlo
    steps: list = field(default_factory=list)
    on_fail: str = STOP


def chat_agent(name):
    """El agente de un paso como lo nombra el chat: '' es el engineer."""
    return '' if name == state.MAIN_AGENT else name


def verdict(reply):
    """Por qué el agente dice que su paso no salió (`PASO FALLIDO: …` al
    final de su respuesta), o '' si no lo dice."""
    lines = [line.strip(' *`_>-') for line in (reply or '').splitlines() if line.strip()]
    for line in reversed(lines[-VERDICT_LINES:]):
        if line.upper().startswith(FAILED):
            return line[len(FAILED):].strip(' *`_.') or 'sin motivo'
    return ''


def path():
    return os.path.join(os.path.dirname(settings.path()), 'workflows.json')


def parse(data):
    """Los workflows de lo que había guardado; lo que no sirve se salta."""
    found = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str) or not item['name'].strip():
            continue
        steps = [Step(s['agent'], s['text']) for s in (item.get('steps') if isinstance(item.get('steps'), list) else [])
                 if isinstance(s, dict) and s.get('agent') in state.ROLE_AGENTS.values()
                 and isinstance(s.get('text'), str)]
        project = item.get('project') if isinstance(item.get('project'), str) else ''
        found.append(Workflow(item['name'].strip(), project, steps, GO if item.get('on_fail') == GO else STOP))
    return found


def load():
    try:
        with open(path(), encoding='utf-8') as f:
            return parse(json.load(f))
    except (OSError, ValueError):
        return []


def save(found):
    """Guarda la lista entera. Si no se puede, OSError: el panel lo dice."""
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd = os.open(p + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump([asdict(w) for w in found], f, ensure_ascii=False, indent=2)
    os.replace(p + '.tmp', p)


class Draft:
    """El workflow que se está editando: una copia, y el nombre con el que
    estaba guardado (None si es nuevo)."""

    def __init__(self, workflow=None, project=''):
        self.saved_as = workflow.name if workflow is not None else None
        self.w = copy.deepcopy(workflow) if workflow is not None else Workflow(project=project)
        self.clean = copy.deepcopy(self.w)

    @property
    def dirty(self):
        return self.w != self.clean

    def add(self):
        self.w.steps.append(Step())

    def remove(self, index):
        if 0 <= index < len(self.w.steps):
            del self.w.steps[index]

    def move(self, index, by):
        """Sube (-1) o baja (+1) un paso. Devuelve dónde quedó."""
        to = index + by
        if not (0 <= index < len(self.w.steps) and 0 <= to < len(self.w.steps)):
            return index
        self.w.steps[index], self.w.steps[to] = self.w.steps[to], self.w.steps[index]
        return to

    def name_problem(self, found):
        """Por qué ese nombre no vale, o ''. `found` son los ya guardados."""
        name = self.w.name.strip()
        if not name:
            return 'Ponle un nombre para guardarlo.'
        if any(w.name.lower() == name.lower() and w.name != self.saved_as for w in found):
            return 'Ya existe un workflow con ese nombre. Elige otro.'
        return ''

    def blocker(self, found):
        """Por qué no se puede guardar y lanzar todavía, o ''."""
        if not self.w.steps:
            return 'Añade al menos un paso para lanzarlo'
        problem = self.name_problem(found)
        if problem:
            return problem.rstrip('.')
        for n, step in enumerate(self.w.steps, 1):
            if not step.text.strip():
                return f'Escribe qué hace el paso {n}'
        return ''

    def store(self, found):
        """La lista de guardados con este dentro, en el sitio del que edita o
        al final si es nuevo."""
        w = copy.deepcopy(self.w)
        w.name = w.name.strip()
        for step in w.steps:
            step.text = step.text.strip()
        out = [w if old.name == self.saved_as else old for old in found]
        return out if self.saved_as is not None and w in out else [*found, w]

    def kept(self):
        """Ya está guardado tal cual: deja de estar «sin guardar»."""
        self.w.name = self.w.name.strip()
        self.saved_as, self.clean = self.w.name, copy.deepcopy(self.w)


class Run:
    """Una ejecución: cómo va cada paso, cuánto tardó y qué contestó."""

    def __init__(self, workflow, clock=time.monotonic):
        self.w, self.clock = copy.deepcopy(workflow), clock
        count = len(self.w.steps)
        self.states = [WAIT] * count
        self.started, self.took = [None] * count, [None] * count
        self.replies, self.why = [''] * count, [''] * count
        self.index = None             # el paso en curso; None si no corre ninguno
        self.stopped = False          # se detuvo a mano

    @property
    def running(self):
        return self.index is not None

    @property
    def failed(self):
        """El primer paso que falló, o None."""
        return next((i for i, s in enumerate(self.states) if s == BAD), None)

    @property
    def done(self):
        return not self.running and all(s in (OK, BAD) for s in self.states)

    def seconds(self, i):
        """Lo que lleva o lo que tardó el paso `i`; None si no ha empezado."""
        if self.took[i] is not None:
            return self.took[i]
        return None if self.started[i] is None else self.clock() - self.started[i]

    def prompt(self, i):
        """Lo que se le manda al agente del paso `i`: su instrucción, lo que
        dejó el paso anterior (si hubo, con respuesta) y cómo avisar si no sale."""
        text = self.w.steps[i].text
        before = next((j for j in range(i - 1, -1, -1) if self.replies[j]), None)
        if before is not None:
            text += (f'\n\n---\nEres el paso {i + 1} de {len(self.w.steps)} del workflow «{self.w.name}». '
                     f'Esto dejó el paso {before + 1} ({self.w.steps[before].agent}):\n\n{self.replies[before]}')
        return text + RULE

    def begin(self, i):
        """Empieza (o reintenta) el paso `i`."""
        self.index, self.stopped = i, False
        self.states[i], self.started[i], self.took[i] = RUNNING, self.clock(), None
        self.replies[i] = self.why[i] = ''

    def finish(self, ok, reply='', why=''):
        """El paso en curso acabó. Devuelve el que sigue, o None si la
        ejecución se queda ahí: era el último, falló y el workflow para, o se
        detuvo a mano."""
        i, self.index = self.index, None
        if i is None:
            return None
        self.states[i] = OK if ok else BAD
        self.took[i] = self.clock() - (self.started[i] if self.started[i] is not None else self.clock())
        self.replies[i], self.why[i] = (reply if ok else ''), ('' if ok else why or 'falló')
        last = i + 1 >= len(self.w.steps)
        if last or self.stopped or (not ok and self.w.on_fail != GO):
            return None
        return i + 1

    def refuse(self, i, why):
        """El paso `i` no pudo ni empezar. Devuelve el que sigue, como `finish`."""
        self.begin(i)
        return self.finish(False, why=f'no pudo empezar: {why}')

    def status(self):
        """Cómo va, en una línea."""
        count = len(self.w.steps)
        if self.running:
            return f'Corriendo el paso {self.index + 1} de {count}…'
        bad = self.failed
        if self.stopped:
            return 'Lo detuviste.'
        if bad is not None and self.states[-1] == WAIT:
            return f'Se paró en el paso {bad + 1} de {count}.'
        if bad is not None:
            fails = sum(s == BAD for s in self.states)
            return 'Terminó, con 1 paso fallido.' if fails == 1 else f'Terminó, con {fails} pasos fallidos.'
        return 'Terminó.' if self.done else 'Sin empezar.'
