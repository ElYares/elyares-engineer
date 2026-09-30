"""Sesiones de Claude Code y qué debe mostrar la isla.

Cada evento que manda `elyares-hook` actualiza una sesión. `view()` elige la
sesión más importante y decide el modo de la isla:

    hidden  nada que mostrar
    peek    asomado, solo la mascota (Claude trabajando, o esperando hace rato)
    open    con texto (pide permiso, recién terminó, se quedó esperando)

Si el permiso llegó por el hook `ask`, la sesión guarda el Request del hook y
la isla muestra Permitir / Denegar. El Request se suelta en cuanto la sesión
sigue por otro lado (se contestó en la terminal, terminó el turno, etc.).
"""

import os
import subprocess
import time
from dataclasses import dataclass, field

DONE_OPEN_SECS = 5        # cuánto se queda abierta la isla al terminar
WAITING_OPEN_SECS = 6     # abierta al quedarse esperando; luego se asoma
WAITING_PEEK_SECS = 600   # tras 10 min esperando deja de asomarse
WORKING_STALE_SECS = 1200 # 20 min sin eventos trabajando = se colgó o se cerró
FORGET_SECS = 6 * 3600
ASK_TIMEOUT = 600         # timeout del hook PermissionRequest en settings.json

DENY_MESSAGE = 'El usuario lo denegó desde la mascota ElYares.'

PRIORITY = {'permission': 4, 'waiting': 3, 'done': 2, 'working': 1}

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
    changed: float = field(default_factory=time.monotonic)
    updated: float = field(default_factory=time.monotonic)

    @property
    def proj(self):
        return project_name(self.cwd)

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


class Model:
    def __init__(self):
        self.sessions = {}

    def handle(self, msg, req=None, now=None):
        now = now or time.monotonic()
        ev = msg.get('event', '')
        sid = str(msg.get('session_id') or 'unknown')
        agent = msg.get('agent_id') or ''
        if ev == 'session-end':
            s = self.sessions.pop(sid, None)
            if s:
                s.release()
            if req:
                req.reply(None)
            return
        s = self.sessions.get(sid)
        if s is None:
            s = self.sessions[sid] = Session(sid)
        s.cwd = msg.get('cwd') or s.cwd
        s.pane = msg.get('pane') or s.pane
        s.tmux = msg.get('tmux') or s.tmux
        root = project_root(s.cwd)

        if s.ask is not None and agent == s.ask_agent and (
                ev in ('start', 'stop', 'failure')
                or (ev == 'tool-done' and msg.get('tool_name') == s.ask_tool)):
            # Se contestó en la terminal, o el turno siguió sin esperar.
            s.release()

        if ev == 'ask':
            s.release()
            if req is None or req.done:
                return
            s.ask, s.ask_tool, s.ask_agent = req, msg.get('tool_name', ''), agent
            s.last_tool = describe_tool(s.ask_tool, msg.get('tool_input'), root)
            s.set('permission', s.last_tool, now)
        elif ev == 'start':
            s.started = now
            s.last_tool = ''
            s.set('working', 'Pensando…', now)
        elif ev == 'tool':
            s.last_tool = describe_tool(msg.get('tool_name', ''), msg.get('tool_input'), root)
            s.set('working', s.last_tool, now)
        elif ev == 'tool-done':
            # Tras aprobar un permiso no llega otro aviso hasta la siguiente
            # herramienta: esto baja la antena roja en cuanto la herramienta corre.
            if s.state == 'permission':
                s.set('working', s.last_tool or 'Trabajando…', now)
            else:
                s.updated = now
        elif ev == 'permission':
            s.set('permission', s.last_tool or short(msg.get('message')), now)
        elif ev == 'idle':
            s.set('waiting', 'Esperando tu respuesta', now)
        elif ev == 'stop':
            if msg.get('agent_id'):
                return
            took = f' en {elapsed(now - s.started)}' if s.started else ''
            s.set('done', f'Listo{took}', now)
        elif ev == 'failure':
            reason = msg.get('error_type') or msg.get('reason') or ''
            s.set('waiting', f'Se cayó{": " + reason if reason else ""}', now)

    def decide(self, s, allow, now=None):
        """Contesta el permiso pendiente de la sesión desde la isla."""
        if s is None or s.ask is None:
            return False
        answer = {'behavior': 'allow'} if allow else {'behavior': 'deny', 'message': DENY_MESSAGE}
        s.ask.reply(answer)
        s.ask = None
        s.set('working', s.last_tool if allow else 'Pensando…', now)
        return True

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
        for sid, s in list(self.sessions.items()):
            if now - s.updated > FORGET_SECS:
                s.release()
                del self.sessions[sid]
            elif s.state == 'working' and now - s.updated > WORKING_STALE_SECS:
                s.set('idle', '', now)
            elif s.state == 'done' and now - s.changed > DONE_OPEN_SECS:
                s.set('idle', '', now)
            elif s.state == 'waiting' and now - s.changed > WAITING_PEEK_SECS:
                s.set('idle', '', now)

    def active(self):
        return [s for s in self.sessions.values() if s.state != 'idle']

    def view(self, now=None):
        now = now or time.monotonic()
        self._expire(now)
        best, best_p = None, 0
        for s in self.sessions.values():
            p = PRIORITY.get(s.state, 0)
            if p > best_p or (p == best_p and p > 0 and s.updated > best.updated):
                best, best_p = s, p
        count = len(self.active())
        if best is None:
            return View(count=0)

        st = best.state
        if st == 'permission':
            mode, title = 'open', f'{best.proj} necesita permiso'
        elif st == 'done':
            mode, title = 'open', best.proj
        elif st == 'waiting':
            mode = 'open' if now - best.changed < WAITING_OPEN_SECS else 'peek'
            title = best.proj
        else:
            mode, title = 'peek', best.proj
        pet = {'waiting': 'confused'}.get(st, st)
        ask = st == 'permission' and best.ask is not None
        return View(mode, pet, title, best.detail, count, ask, best, (best.sid, st, ask))
