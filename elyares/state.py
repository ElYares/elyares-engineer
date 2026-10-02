"""Sesiones de Claude Code y qué debe mostrar la isla.

Cada evento que manda `elyares-hook` actualiza una sesión. `view()` elige la
sesión más importante y decide el modo de la isla:

    hidden  nada que mostrar
    peek    asomado, solo la mascota (Claude trabajando, o esperando hace rato)
    open    con texto (pide permiso, recién terminó, se quedó esperando)

Si el permiso llegó por el hook `ask`, la sesión guarda el Request del hook y
la isla muestra Permitir / Denegar. El Request se suelta en cuanto la sesión
sigue por otro lado (se contestó en la terminal, terminó el turno, etc.).

Además de sesiones hay alertas (evento `alert`): no son de Claude, traen su
propio nombre y, si acaso, una URL o un pane que abre el clic. Las mandan
`devherd.py`, `github.py` y `coffe.py`, y este módulo las crea para un comando
largo que terminó (`cmd-done`) y para el uso de Claude (`status`). Recién
llegada, una alerta abre la isla; después se queda como una fila más hasta
que se resuelve, se descarta con un clic o caduca. El tono dice si es un
problema (enojada, rojo), una buena noticia (`ok`) o un aviso (`info`).

Una alerta puede traer una ficha: unas líneas de detalle (`lines`, con `where`
y `note` de encabezado) y botones propios (`actions`). La isla la muestra
debajo de la cabecera cuando alguien la está leyendo. Las de aquí llevan la
suya: un comando largo, lo último que imprimió y un botón que salta a su pane;
el contexto, la sesión que lo llenó; el límite de 5 h, las sesiones abiertas.

Las pruebas tienen su propia alerta. En una terminal, `cmd-start` avisa de que
empiezan y la isla se queda abierta con la lista de las que van pasando y
fallando (`testrun.py` las lee de lo que imprime el pane) hasta que `cmd-done`
trae el resultado. Las que corre Claude con Bash llegan al terminar, en
`tool-done` o `tool-fail`, con lo que imprimió el comando.

En foco (un pomodoro de `coffe` en curso) la isla solo se abre sola para un
permiso; lo demás se queda asomado hasta el descanso.

Una sesión lleva además la cuenta de sus subagentes (`Session.agents`): los
hooks SubagentStart y SubagentStop avisan cuándo arranca y termina cada uno
(`agent-start`, `agent-stop`), y lo que hace una herramienta dentro de uno llega
con su `agent_id` y su `agent_type`. Si alguno es de la familia (`AGENT_ROLES`),
la mascota se vuelve ese personaje mientras trabaja (`View.role`).

Una sesión se nombra «agente | proyecto» (`View.agent_name` y `View.title`): el
agente es `elyares-engineer` salvo mientras trabaja un subagente de la familia.

Para el tablero de la isla, cada sesión dice cómo están sus cuatro
(`Session.team`): quién trabaja, quién pide permiso y quién está libre, cada
uno con sus pasos (lo que fue haciendo, con la hora de cada cosa). Mientras la
sesión espera a un subagente de la familia que lanzó, el engineer está libre;
lo que hace uno que no es de la familia cuenta como trabajo del engineer.
"""

import os
import re
import subprocess
import time
from dataclasses import dataclass, field

from . import preview, testrun

DONE_OPEN_SECS = 5        # cuánto se queda abierta la isla al terminar
WAITING_OPEN_SECS = 6     # abierta al quedarse esperando; luego se asoma
WAITING_PEEK_SECS = 600   # tras 10 min esperando deja de asomarse
WORKING_STALE_SECS = 1200 # 20 min sin eventos trabajando = se colgó o se cerró
FORGET_SECS = 6 * 3600
ALERT_OPEN_SECS = 8       # una alerta nueva abre la isla este rato
ALERT_SECS = 600          # sin novedades, la alerta se va sola
ALERT_COOLDOWN_SECS = 900 # descartada con un clic, no vuelve a salir en este rato
CMD_OK_SECS = 120         # "terminó bien" es una buena noticia: se va pronto
RUN_SECS = 3600           # unas pruebas corriendo sin novedades: se da por perdida
CONTEXT_WARN = 90         # % de contexto de una sesión a partir del cual avisa
LIMIT_WARN = (80, 95)     # % del límite de 5 h en los que avisa
ASK_TIMEOUT = 600         # timeout del hook PermissionRequest en settings.json
AGENT_STALE_SECS = 1200   # un subagente tanto rato sin eventos: terminó sin avisar
STEPS_KEPT = 40           # pasos que se recuerdan de cada uno, para su desglose
CARD_LINES = 10           # líneas de detalle de una alerta que caben en la isla
CARD_ACTIONS = 2          # botones propios de una alerta, además de Descartar
# El botón de una alerta que viene de una terminal o de una sesión: lleva a su pane.
JUMP = {'label': 'Ir al pane', 'jump': True, 'after': 'dismiss'}

DENY_MESSAGE = 'El usuario lo denegó desde elyares-engineer.'

# Una alerta vieja queda debajo de cualquier sesión activa: si no, taparía
# durante minutos los avisos de Claude. Recién llegada vale ALERT_FRESH.
PRIORITY = {'permission': 4, 'waiting': 3, 'done': 2, 'working': 1, 'alert': .5}
ALERT_FRESH = 3.5
RUN_RANK = 1.5            # unas pruebas corriendo: sobre una sesión trabajando, bajo lo demás

# Lo que se guarda de cada sesión entre reinicios del daemon.
SAVED_TEXT = ('cwd', 'pane', 'tmux', 'state', 'detail', 'last_tool', 'name', 'url', 'tone',
              'label', 'kind', 'proc')
SAVED_NUM = ('ttl', 'context')
SAVED_TIMES = ('started', 'changed', 'updated')

# Los subagentes de la familia y el personaje de `mascot.ROLES` que le toca a
# cada uno. Cualquier otro (Explore, general-purpose…) trabaja con la cara del
# engineer.
AGENT_ROLES = {'elyares-architect': 'architect', 'elyares-auditor': 'auditor',
               'elyares-reviewer': 'reviewer'}
# Quien trabaja en una sesión mientras no lo haga un subagente de la familia,
# y su personaje.
MAIN_AGENT, MAIN_ROLE = 'elyares-engineer', 'engineer'
# Los cuatro, en el orden de `mascot.ROLES`, y el agente de cada personaje.
TEAM = (MAIN_ROLE, *AGENT_ROLES.values())
ROLE_AGENTS = {MAIN_ROLE: MAIN_AGENT, **{role: name for name, role in AGENT_ROLES.items()}}
# Las herramientas con las que una sesión lanza un subagente.
DELEGATES = ('Task', 'Agent')

_root_cache = {}


def project_root(cwd):
    """Raíz del repo git que contiene cwd, o cwd si no es un repo."""
    if not cwd:
        return ''
    if cwd not in _root_cache:
        try:
            root = subprocess.run(['git', '-C', cwd, 'rev-parse', '--show-toplevel'],
                                  capture_output=True, text=True, timeout=1).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            root = ''
        _root_cache[cwd] = root or cwd.rstrip('/')
    return _root_cache[cwd]


def project_name(cwd):
    """Nombre del repo o de la carpeta, como lo muestra claude-notify.sh."""
    return os.path.basename(project_root(cwd)) or 'claude'


def short(text, n=90):
    text = ' '.join((text or '').split())
    return text if len(text) <= n else text[:n - 1] + '…'


_ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')


def card_lines(lines):
    """El detalle de una alerta: las últimas líneas, sin colores de terminal."""
    if not isinstance(lines, list):
        return []
    out = [_ANSI.sub('', line).expandtabs(4).rstrip()[:300]
           for line in lines if isinstance(line, str)]
    return [line for line in out if line][-CARD_LINES:]


def card_actions(items):
    """Los botones de una alerta: [{label, cmd | url | jump, term, hold, after}].

    `cmd` es una lista de argumentos; con `term` corre en una terminal nueva
    (y con `hold` espera una tecla al terminar). `jump` lleva al pane de la
    alerta. `after` dice qué pasa con la alerta al pulsarlo: 'dismiss' la
    descarta, 'clear' la quita sin silenciarla.
    """
    out = []
    for a in items if isinstance(items, list) else []:
        if not isinstance(a, dict) or not isinstance(a.get('label'), str):
            continue
        cmd = a.get('cmd')
        runs = isinstance(cmd, list) and cmd and all(isinstance(c, str) for c in cmd)
        if runs or isinstance(a.get('url'), str) or a.get('jump') is True:
            out.append(a)
    return out[:CARD_ACTIONS]


def _plural(n, one, many):
    return f'{n} {one if n == 1 else many}'


def tests_card(res):
    """Lo que dice la isla de una corrida de pruebas, a partir de sus
    resultados (`testrun.results`). None si no trae o no se vio ninguna prueba."""
    if not isinstance(res, dict) or not res.get('ran'):
        return None
    try:
        passed, failed, skipped = (int(res.get(k) or 0) for k in ('passed', 'failed', 'skipped'))
    except (TypeError, ValueError):
        return None
    words = [(failed, 'falló', 'fallaron'), (passed, 'pasó', 'pasaron'),
             (skipped, 'saltada', 'saltadas')]
    marks = [(passed, testrun.OK), (failed, testrun.FAIL), (skipped, testrun.SKIP)]
    return {'failed': failed,
            'counts': ', '.join(_plural(n, one, many) for n, one, many in words if n) or 'ninguna',
            'note': ' · '.join(f'{n} {testrun.MARKS[status]}' for n, status in marks if n),
            'lines': res.get('lines')}


def tilde(path):
    """Una ruta con ~ en vez de la carpeta personal."""
    home = os.path.expanduser('~')
    return '~' + path[len(home):] if path == home or path.startswith(home + '/') else path


def elapsed(secs):
    secs = int(secs)
    if secs < 60:
        return f'{secs} s'
    if secs < 3600:
        return f'{secs // 60} min {secs % 60:02d} s'
    return f'{secs // 3600} h {secs % 3600 // 60:02d} min'


def describe_tool(name, ti, root):
    """Qué está haciendo Claude, en una línea legible."""
    ti = ti if isinstance(ti, dict) else {}

    def rel(p):
        if not p:
            return ''
        if root and p.startswith(root.rstrip('/') + '/'):
            return p[len(root.rstrip('/')) + 1:]
        return p.replace(os.path.expanduser('~'), '~', 1)

    path = rel(ti.get('file_path') or ti.get('notebook_path') or '')
    if name == 'Read':
        return f'Leyendo {path}'
    if name in ('Edit', 'MultiEdit', 'NotebookEdit'):
        return f'Editando {path}'
    if name == 'Write':
        return f'Escribiendo {path}'
    if name == 'Bash':
        cmd = (ti.get('command') or '').strip().splitlines()
        return f'Ejecutando {cmd[0]}' if cmd else 'Ejecutando un comando'
    if name in ('Grep', 'Glob'):
        return f'Buscando {ti.get("pattern", "")}'.strip()
    if name in ('WebFetch', 'WebSearch'):
        return 'Buscando en la web'
    if name in ('Task', 'Agent'):
        desc = ti.get('description') or ti.get('subagent_type') or ''
        return f'Subagente: {desc}' if desc else 'Lanzando un subagente'
    if name == 'TodoWrite':
        return 'Actualizando la lista de tareas'
    if name.startswith('mcp__'):
        parts = name.split('__')
        return f'Usando {parts[1]}' if len(parts) > 1 else name
    return name


def add_step(steps, text, now):
    """Apunta un paso: lo que se empieza a hacer y cuándo. El mismo dos veces
    seguidas (la herramienta y su permiso) es uno solo."""
    if text and (not steps or steps[-1][0] != text):
        steps.append((text, now))
        del steps[:-STEPS_KEPT]


@dataclass
class Member:
    """Uno de los cuatro de la familia en una sesión, como lo ve el tablero."""
    role: str
    name: str
    state: str = 'idle'       # working | permission | waiting | done | idle
    steps: list = field(default_factory=list)   # [(texto, cuándo)]; el último es lo de ahora
    since: float = 0.0        # desde cuándo trabaja

    @property
    def busy(self):
        return self.state != 'idle'

    @property
    def detail(self):
        return self.steps[-1][0] if self.steps else ''


@dataclass
class Agent:
    """Un subagente que una sesión tiene trabajando."""
    aid: str
    kind: str = ''            # el nombre del agente: Explore, elyares-auditor…
    detail: str = ''          # lo último que hizo
    started: float = 0.0
    updated: float = 0.0
    steps: list = field(default_factory=list)   # [(texto, cuándo)]

    @property
    def role(self):
        return AGENT_ROLES.get(self.kind, MAIN_ROLE)

    @property
    def name(self):
        return self.kind or 'subagente'


@dataclass
class Session:
    sid: str
    cwd: str = ''
    pane: str = ''
    tmux: str = ''
    state: str = 'idle'
    detail: str = ''
    last_tool: str = ''
    started: float = 0.0
    ask: object = None        # ipc.Request del hook PermissionRequest
    ask_tool: str = ''
    ask_agent: str = ''
    name: str = ''            # solo en alertas: el nombre a mostrar, sin cwd de donde sacarlo
    url: str = ''             # solo en alertas: lo que abre el clic
    tone: str = ''            # solo en alertas: '' problema, 'ok' buena noticia, 'info' aviso,
                              # 'run' algo que está corriendo (unas pruebas)
    tests: bool = False       # solo en alertas: es de pruebas, y su ficha se ve sin pedirla
    ttl: float = 0            # solo en alertas: segundos que dura sin novedades (0 = ALERT_SECS)
    where: str = ''           # solo en alertas: de dónde sale el detalle (archivo:línea, contenedor)
    note: str = ''            # solo en alertas: lo que va a la derecha de `where`
    lines: list = field(default_factory=list)     # solo en alertas: el detalle; no se guarda
    actions: list = field(default_factory=list)   # solo en alertas: sus botones; no se guardan
    context: float = 0        # % de la ventana de contexto que lleva usada la sesión
    label: str = ''           # el nombre que le puso Claude Code, si es de segundo plano
    kind: str = ''            # 'bg' si corre en segundo plano, sin terminal
    proc: str = ''            # su proceso de Claude, "pid:arranque": si muere, se olvida
    # ¿Ha hecho algo? Claude Code tiene lista una sesión de repuesto que solo
    # pinta su barra de estado: hasta que alguien la usa, no es de nadie.
    used: bool = False
    preview: object = None    # preview.Preview de lo que está editando; no se guarda
    agents: dict = field(default_factory=dict)    # sus subagentes trabajando, por id; no se guardan
    steps: list = field(default_factory=list)     # [(texto, cuándo)] del turno, sin los de la familia
    delegating: bool = False  # espera a un subagente que lanzó y no ha vuelto
    blocked: str = ''         # el subagente que pidió el permiso pendiente; '' es la propia sesión
    changed: float = field(default_factory=time.monotonic)
    updated: float = field(default_factory=time.monotonic)

    @property
    def proj(self):
        return self.name or project_name(self.cwd)

    @property
    def card(self):
        """¿Es una alerta con ficha (detalle o botones) que mostrar?"""
        return self.state == 'alert' and bool(self.lines or self.actions)

    @property
    def lead(self):
        """El subagente de la familia que arrancó al último y sigue trabajando, o None."""
        family = [a for a in self.agents.values() if a.kind in AGENT_ROLES]
        return max(family, key=lambda a: a.started) if family else None

    @property
    def role(self):
        """El personaje que le toca a la mascota: el de ese subagente, o el engineer."""
        return self.lead.role if self.lead else MAIN_ROLE

    @property
    def agent_name(self):
        """El nombre de quien trabaja en la sesión: ese subagente, o el
        engineer. Una alerta no es de ningún agente: ''."""
        if self.state == 'alert':
            return ''
        return self.lead.name if self.lead else MAIN_AGENT

    def team(self):
        """Cómo están los cuatro de la familia en esta sesión, en el orden de `TEAM`."""
        blocked = self.agents.get(self.blocked) if self.state == 'permission' else None
        family = [a for a in self.agents.values() if a.kind in AGENT_ROLES]
        if blocked is not None and blocked not in family:
            blocked = None                # lo pidió uno que cuenta como el engineer
        if self.state == 'permission' and blocked is None:
            state = 'permission'
        elif self.state in ('working', 'permission'):
            # Mientras solo espera a los de la familia, el engineer está libre.
            waits = self.delegating and family and len(family) == len(self.agents)
            state = 'idle' if waits else 'working'
        else:
            state = self.state if self.state in ('done', 'waiting') else 'idle'
        steps = list(self.steps)
        if state in ('done', 'waiting') or not (steps or family):
            # Lo último que se sabe: cómo acabó, o lo que hacía una sesión
            # recuperada de un reinicio, que vuelve sin sus pasos. Con uno de
            # la familia trabajando no: lo último de la sesión es de él.
            add_step(steps, self.detail, self.changed)
        members = [Member(MAIN_ROLE, MAIN_AGENT, state, steps, self.started)]
        for role in TEAM[1:]:
            mine = [a for a in family if a.role == role]
            if not mine:
                members.append(Member(role, ROLE_AGENTS[role]))
                continue
            a = max(mine, key=lambda a: a.started)
            members.append(Member(role, a.name, 'permission' if a is blocked else 'working',
                                  a.steps, a.started))
        return members

    def set(self, state, detail=None, now=None):
        now = now or time.monotonic()
        if state != self.state:
            self.state, self.changed = state, now
        if detail is not None:
            self.detail = detail
        self.updated = now

    def release(self):
        """Suelta el hook que espera respuesta, sin decidir."""
        if self.ask is not None:
            self.ask.reply(None)
            self.ask = None


@dataclass
class View:
    mode: str = 'hidden'
    pet: str = 'idle'
    title: str = ''
    detail: str = ''
    count: int = 0
    ask: bool = False         # mostrar Permitir / Denegar
    session: Session | None = None
    key: tuple = ()
    others: list = field(default_factory=list)   # las demás sesiones, por urgencia; al final las en reposo
    role: str = MAIN_ROLE     # el personaje de la mascota: el del subagente que trabaja
    agent_name: str = ''      # quién trabaja, para la cabecera «agente | proyecto»; '' en una alerta


class Model:
    def __init__(self):
        self.sessions = {}
        self.dismissed = {}       # alerta descartada -> cuándo
        self.focus = False        # hay un pomodoro en curso
        self.limit = 0.0          # % usado del límite de 5 h de Claude, el mismo para todas

    def dump(self):
        """Las sesiones como datos planos, para guardarlas entre reinicios."""
        return [{'sid': s.sid, 'used': s.used, 'delegating': s.delegating,
                 **{k: getattr(s, k) for k in SAVED_TEXT + SAVED_NUM + SAVED_TIMES}}
                for s in self.sessions.values()]

    def restore(self, items, now=None):
        """Recupera las sesiones que guardó el daemon anterior.

        Un permiso vuelve sin botones: el hook que esperaba respuesta se fue
        con el daemon, y el aviso de la terminal sigue ahí.
        """
        now = now or time.monotonic()
        for it in items:
            if not isinstance(it, dict) or not it.get('sid'):
                continue
            s = Session(str(it['sid']))
            for k in SAVED_TEXT:
                setattr(s, k, str(it.get(k) or ''))
            # Lo que guardó una versión anterior no lo dice: se da por usada.
            s.used = bool(it.get('used', True))
            # Si esperaba a un subagente, lo sigue esperando: él no se guarda,
            # pero vuelve a salir con lo siguiente que haga.
            s.delegating = bool(it.get('delegating'))
            if s.state not in PRIORITY:
                s.state = 'idle'
            if s.state == 'alert' and s.tone == 'run':
                # Unas pruebas a medias: quien las seguía se fue con el daemon anterior.
                continue
            try:
                for k in SAVED_NUM:
                    setattr(s, k, float(it.get(k) or 0))
                # Nunca en el futuro: un archivo de otro arranque no caducaría.
                s.started = min(now, float(it.get('started') or 0))
                s.changed = min(now, float(it.get('changed') or now))
                s.updated = min(now, float(it.get('updated') or now))
            except (TypeError, ValueError):
                continue
            self.sessions[s.sid] = s

    def handle(self, msg, req=None, now=None):
        now = now or time.monotonic()
        ev = msg.get('event', '')
        sid = str(msg.get('session_id') or 'unknown')
        agent = msg.get('agent_id') or ''
        if ev in ('session-end', 'alert-clear'):
            s = self.sessions.pop(sid, None)
            if s:
                s.release()
            if req:
                req.reply(None)
            return
        if ev == 'focus':
            self.focus = bool(msg.get('on'))
            return
        if ev == 'cmd-start':
            # Empiezan unas pruebas en una terminal, o llega cómo van (`results`).
            card = tests_card(msg.get('results'))
            cmd = ' '.join((msg.get('command') or 'pruebas').split())
            if card is None:
                # Una corrida nueva es otra noticia, aunque la alerta de la
                # anterior siga ahí o se haya descartado.
                self.sessions.pop(sid, None)
                self.dismissed.pop(sid, None)
            msg = {**msg, 'event': 'alert', 'name': project_name(msg.get('cwd') or ''),
                   'message': f'Corriendo pruebas: {card["counts"] if card else cmd}',
                   'tone': 'run', 'ttl': RUN_SECS, 'tests': True, 'where': cmd,
                   'note': card['note'] if card else '', 'lines': card['lines'] if card else [],
                   'actions': [JUMP] if msg.get('pane') else []}
            ev = 'alert'
        if ev == 'cmd-done':
            # Un comando largo de la terminal terminó: una alerta que lleva a su pane.
            rc, took = msg.get('exit_code') or 0, elapsed(msg.get('seconds') or 0)
            cmd = ' '.join((msg.get('command') or 'comando').split())
            head = 'Terminó' if rc == 0 else f'Falló (código {rc})'
            cwd = msg.get('cwd') or ''
            # La ficha: dónde corrió, lo último que imprimió (shell/elyares.bash
            # lo copia del pane) y, si hay pane, el botón que lleva a él.
            alert = {'message': f'{head} en {took}: {cmd}', 'tone': 'ok' if rc == 0 else '',
                     'where': tilde(cwd), 'note': took if rc == 0 else f'código {rc} · {took}',
                     'lines': msg.get('output')}
            card = tests_card(msg.get('results'))
            if card:
                alert.update(lines=card['lines'], tests=True)
            if card and (card['failed'] or rc == 0):
                # Eran pruebas y se sabe cómo quedaron. Si el comando falló sin
                # ninguna en rojo (no compiló, faltó cobertura), manda su código.
                head = 'Pruebas en rojo' if card['failed'] else 'Pruebas en verde'
                alert.update(message=f'{head}: {card["counts"]} en {took}', where=cmd,
                             note=card['note'], tone='' if card['failed'] else 'ok')
            msg = {**msg, 'event': 'alert', 'name': project_name(cwd), **alert,
                   'ttl': CMD_OK_SECS if alert['tone'] == 'ok' else 0,
                   'actions': [JUMP] if msg.get('pane') else []}
            ev = 'alert'
        if ev == 'alert':
            if sid in self.dismissed and now - self.dismissed[sid] < ALERT_COOLDOWN_SECS:
                return
            s = self.sessions.get(sid)
            if s is None:
                s = self.sessions[sid] = Session(sid, changed=now)
            s.name = msg.get('name') or s.name or 'alerta'
            s.url = msg.get('url') or s.url
            s.pane = msg.get('pane') or s.pane
            s.tmux = msg.get('tmux') or s.tmux
            tone, ttl = msg.get('tone') or '', float(msg.get('ttl') or 0)
            if tone != s.tone:
                # De rojo a verde (o al revés) es otra noticia: vuelve a abrir.
                s.tone, s.changed = tone, now
            s.ttl = ttl
            s.where, s.note = short(msg.get('where'), 120), short(msg.get('note'), 60)
            s.lines, s.actions = card_lines(msg.get('lines')), card_actions(msg.get('actions'))
            s.tests = bool(msg.get('tests'))
            s.set('alert', short(msg.get('message'), 300), now)
            return
        s = self.sessions.get(sid)
        if s is None:
            s = self.sessions[sid] = Session(sid)
        s.cwd = msg.get('cwd') or s.cwd
        s.pane = msg.get('pane') or s.pane
        s.tmux = msg.get('tmux') or s.tmux
        s.proc = msg.get('proc') or s.proc
        s.kind = msg.get('kind') or s.kind
        s.label = short(msg.get('label'), 60) or s.label
        if ev != 'status':
            s.used = True
        root = project_root(s.cwd)

        if s.ask is not None and agent == s.ask_agent and (
                ev in ('start', 'stop', 'failure', 'agent-stop')
                or (ev == 'tool-done' and msg.get('tool_name') == s.ask_tool)):
            # Se contestó en la terminal, o el turno siguió sin esperar.
            s.release()

        if agent and ev in ('agent-stop', 'stop'):
            # Terminó un subagente: el turno de la sesión sigue.
            s.agents.pop(agent, None)
            s.updated = now
            return
        if agent:
            # Lo que pasa dentro de un subagente lo da de alta, aunque su
            # arranque no se haya visto (los hooks se instalaron después).
            a = s.agents.get(agent)
            if a is None:
                a = s.agents[agent] = Agent(agent, short(msg.get('agent_type'), 40), started=now)
            a.updated = now

        if ev == 'ask':
            s.release()
            if req is None or req.done:
                return
            s.ask, s.ask_tool, s.ask_agent = req, msg.get('tool_name', ''), agent
            s.last_tool = describe_tool(s.ask_tool, msg.get('tool_input'), root)
            s.preview = preview.build(s.ask_tool, msg.get('tool_input'))
            self._step(s, agent, now)
            s.blocked = agent
            s.set('permission', s.last_tool, now)
        elif ev == 'start':
            s.started = now
            s.last_tool = ''
            s.preview = None
            s.steps, s.delegating = [('Pensando…', now)], False
            s.set('working', 'Pensando…', now)
        elif ev == 'tool':
            s.last_tool = describe_tool(msg.get('tool_name', ''), msg.get('tool_input'), root)
            # La vista previa dura lo que dura la edición: otra herramienta la quita.
            s.preview = preview.build(msg.get('tool_name', ''), msg.get('tool_input'))
            self._step(s, agent, now)
            if not agent:
                s.delegating = msg.get('tool_name') in DELEGATES
            s.set('working', s.last_tool, now)
        elif ev == 'agent-start':
            s.updated = now
        elif ev in ('tool-done', 'tool-fail'):
            if not agent and msg.get('tool_name') in DELEGATES:
                s.delegating = False      # el subagente volvió, o quedó en segundo plano
            # Tras aprobar un permiso no llega otro aviso hasta la siguiente
            # herramienta: esto baja la antena roja en cuanto la herramienta corre.
            if ev == 'tool-done' and s.state == 'permission':
                s.set('working', s.last_tool or 'Trabajando…', now)
            else:
                s.updated = now
            if isinstance(msg.get('output'), str):
                self._claude_tests(s, msg, ev == 'tool-fail', now)
        elif ev == 'permission':
            if s.state != 'permission':
                s.blocked = agent         # sin el hook `ask` delante: es lo que se sabe
            s.set('permission', s.last_tool or short(msg.get('message')), now)
        elif ev == 'compact':
            s.set('working', 'Compactando el contexto…', now)
        elif ev == 'status':
            self._usage(s, msg, now)
        elif ev == 'idle':
            s.set('waiting', 'Esperando tu respuesta', now)
        elif ev == 'stop':
            took = f' en {elapsed(now - s.started)}' if s.started else ''
            s.preview, s.delegating = None, False
            s.set('done', f'Listo{took}', now)
        elif ev == 'failure':
            reason = msg.get('error_type') or msg.get('reason') or ''
            s.set('waiting', f'Se cayó{": " + reason if reason else ""}', now)

    @staticmethod
    def _step(s, agent, now):
        """Apunta lo que se acaba de empezar (`s.last_tool`) a quien lo hace.
        Lo de un subagente que no es de la familia cuenta también como paso
        del engineer."""
        a = s.agents.get(agent)
        if a is not None:
            a.detail = s.last_tool
            add_step(a.steps, s.last_tool, now)
        if a is None or a.kind not in AGENT_ROLES:
            add_step(s.steps, s.last_tool, now)

    def decide(self, s, allow, now=None):
        """Contesta el permiso pendiente de la sesión desde la isla."""
        if s is None or s.ask is None:
            return False
        if allow:
            answer = {'behavior': 'allow'}
        else:
            # interrupt corta el turno, como el No de la terminal.
            answer = {'behavior': 'deny', 'message': DENY_MESSAGE, 'interrupt': True}
        s.ask.reply(answer)
        s.ask = None
        if allow:
            s.set('working', s.last_tool, now)
        else:
            # Un turno cortado no manda stop: Claude se queda en el prompt.
            s.set('waiting', 'Esperando tu respuesta', now)
        return True

    def _claude_tests(self, s, msg, failed, now):
        """Claude corrió pruebas con Bash: una alerta con cuáles pasaron y
        cuáles no. `failed` es si el comando salió con error."""
        card = tests_card(testrun.results(testrun.parse(testrun.clean(msg['output']))))
        if card is None:
            return
        ti = msg.get('tool_input') if isinstance(msg.get('tool_input'), dict) else {}
        red = card['failed'] or failed
        # Cada corrida es otra noticia: vuelve a abrir la isla aunque quede igual.
        self.sessions.pop(f'tests:{s.sid}', None)
        self.dismissed.pop(f'tests:{s.sid}', None)
        self.handle({'event': 'alert', 'session_id': f'tests:{s.sid}', 'name': s.proj,
                     'message': f'{"Pruebas en rojo" if red else "Pruebas en verde"}: {card["counts"]}',
                     'tone': '' if red else 'ok', 'ttl': 0 if red else CMD_OK_SECS, 'tests': True,
                     'where': ' '.join(str(ti.get('command') or '').split()), 'note': card['note'],
                     'lines': card['lines'], 'pane': s.pane, 'tmux': s.tmux,
                     'actions': [JUMP] if s.pane else []}, now=now)

    def _usage(self, s, msg, now):
        """Uso de Claude que manda la barra de estado: contexto de la sesión y
        límite de 5 h de la cuenta. Avisa al cruzar un umbral, no en cada dato."""
        try:
            context = float(msg.get('context_pct') or 0)
            limit = float(msg.get('limit_pct') or 0)
        except (TypeError, ValueError):
            return
        if s.context < CONTEXT_WARN <= context:
            # La ficha dice qué sesión es: su carpeta y lo que hacía al llenarse.
            self.handle({'event': 'alert', 'session_id': f'ctx:{s.sid}', 'name': s.proj,
                         'message': f'Contexto al {context:.0f}%: se va a compactar pronto',
                         'tone': 'info', 'pane': s.pane, 'tmux': s.tmux,
                         'where': tilde(s.cwd), 'note': f'{context:.0f}% de contexto',
                         'lines': [f'Al llegar al {CONTEXT_WARN}%: {s.detail}'] if s.detail else [],
                         'actions': [JUMP] if s.pane else []}, now=now)
        s.context = context
        for mark in LIMIT_WARN:
            if self.limit < mark <= limit:
                # El límite es de la cuenta: la ficha dice quién lo está gastando.
                claude = sorted((o for o in self.sessions.values() if o.state != 'alert'),
                                key=lambda o: -o.context)
                n = len(claude)
                self.handle({'event': 'alert', 'session_id': f'limit:{mark}', 'name': 'Claude',
                             'message': f'Límite de 5 h al {limit:.0f}%',
                             'tone': 'info' if mark < LIMIT_WARN[-1] else '',
                             'where': 'Sesiones abiertas',
                             'note': '1 sesión' if n == 1 else f'{n} sesiones',
                             'lines': [f'{o.proj[:24]:<24} {o.context:>3.0f}%  '
                                       f'{o.detail or "en reposo"}' for o in claude[:CARD_LINES]]}, now=now)
        if limit:
            self.limit = limit

    def dismiss(self, s, now=None, cooldown=True):
        """Quita una alerta porque ya se atendió con un clic. Sin cooldown puede
        volver enseguida: es lo que toca tras intentar arreglar el problema."""
        if self.sessions.pop(s.sid, None) is not None and cooldown:
            self.dismissed[s.sid] = now or time.monotonic()

    def gone(self, req, now=None):
        """El hook se fue sin respuesta: Claude lo mató o se le acabó el tiempo."""
        for s in self.sessions.values():
            if s.ask is req:
                s.ask = None
                # Claude lo mata al contestar No en la terminal y el turno se
                # corta; si fue timeout, el aviso de la terminal sigue ahí.
                if s.state == 'permission' and time.time() - req.born < ASK_TIMEOUT - 5:
                    s.set('waiting', 'Esperando tu respuesta', now)
                return

    def _expire(self, now):
        self.dismissed = {sid: t for sid, t in self.dismissed.items()
                          if now - t < ALERT_COOLDOWN_SECS}
        for sid, s in list(self.sessions.items()):
            s.agents = {aid: a for aid, a in s.agents.items()
                        if now - a.updated < AGENT_STALE_SECS}
            if now - s.updated > FORGET_SECS:
                s.release()
                del self.sessions[sid]
            elif s.state == 'alert' and now - s.updated > (s.ttl or ALERT_SECS):
                del self.sessions[sid]
            elif s.state == 'working' and now - s.updated > WORKING_STALE_SECS:
                s.set('idle', '', now)
            elif s.state == 'done' and now - s.changed > DONE_OPEN_SECS:
                s.set('idle', '', now)
            elif s.state == 'waiting' and now - s.changed > WAITING_PEEK_SECS:
                s.set('idle', '', now)

    def prune(self, live):
        """Olvida las sesiones cuyo pane de tmux ya no existe. True si quitó alguna.

        `live` es lo que devuelve actions.live_panes. Las sesiones de un socket
        que no está ahí se quedan: no se pudo preguntar por ellas.
        """
        dead = []
        for sid, s in self.sessions.items():
            sock, pid = (s.tmux.split(',') + [''])[:2]
            if s.pane and pid and sock in live and (pid, s.pane) not in live[sock]:
                dead.append(sid)
        for sid in dead:
            self.sessions.pop(sid).release()
        return bool(dead)

    def reap(self, alive):
        """Olvida las sesiones cuyo proceso de Claude ya no existe: las que se
        cerraron sin avisar y no tienen un pane por el que preguntar (las de
        segundo plano). `alive(proc)` dice si el proceso sigue ahí. True si
        quitó alguna."""
        dead = [sid for sid, s in self.sessions.items()
                if s.proc and s.state != 'alert' and not alive(s.proc)]
        for sid in dead:
            self.sessions.pop(sid).release()
        return bool(dead)

    def active(self):
        return [s for s in self.sessions.values() if s.state != 'idle']

    def view(self, now=None, pin=''):
        """Lo que debe mostrar la isla. `pin` es la alerta que se eligió en la
        lista: pasa a la cabecera mientras se lee, aunque haya algo más urgente."""
        now = now or time.monotonic()
        self._expire(now)
        # La más urgente primero; entre iguales, la que se movió al último.
        # Las que están en reposo (prioridad 0) quedan al final: no asoman la
        # isla, pero salen en la lista.
        def rank(s):
            if s.state == 'alert' and now - s.changed < ALERT_OPEN_SECS:
                return ALERT_FRESH
            if s.state == 'alert' and s.tone == 'run':
                return RUN_RANK
            return PRIORITY.get(s.state, 0)

        # Una que nunca ha hecho nada (la de repuesto) no sale ni se cuenta.
        ranked = sorted((s for s in self.sessions.values() if s.used or s.state != 'idle'),
                        key=lambda s: (-rank(s), -s.updated))
        count = sum(1 for s in ranked if s.state != 'alert')   # "N sesiones": las de Claude
        chosen = self.sessions.get(pin)
        if chosen is not None and chosen.state == 'alert':
            ranked.remove(chosen)
            ranked.insert(0, chosen)
        if not ranked or not rank(ranked[0]):
            return View(count=count, others=ranked)
        best = ranked[0]

        st = best.state
        # Dos sesiones del mismo repo se distinguen por el nombre de la que lo tiene.
        name = f'{best.proj} · {best.label}' if best.label else best.proj
        if st in ('permission', 'done'):
            # Que pide permiso lo dicen la antena roja y la nota de la cabecera.
            mode, title = 'open', name
        elif st == 'waiting':
            mode = 'open' if now - best.changed < WAITING_OPEN_SECS else 'peek'
            title = name
        elif st == 'alert':
            # Unas pruebas corriendo dejan la isla abierta: se van viendo pasar.
            fresh = now - best.changed < ALERT_OPEN_SECS
            mode = 'open' if fresh or best.tone == 'run' else 'peek'
            title = best.proj
        else:
            mode, title = 'peek', name
        if st == 'alert':
            pet = {'ok': 'done', 'info': 'confused', 'run': 'working'}.get(best.tone, 'annoyed')
        else:
            pet = {'waiting': 'confused'}.get(st, st)
        # En foco solo un permiso abre la isla; lo demás se queda asomado.
        if self.focus and mode == 'open' and st != 'permission':
            mode = 'peek'
        ask = st == 'permission' and best.ask is not None
        return View(mode, pet, title, best.detail, count, ask, best, (best.sid, st, ask),
                    ranked[1:], best.role, best.agent_name)
