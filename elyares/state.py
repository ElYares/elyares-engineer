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

En foco (un pomodoro de `coffe` en curso) la isla solo se abre sola para un
permiso; lo demás se queda asomado hasta el descanso.
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
ALERT_OPEN_SECS = 8       # una alerta nueva abre la isla este rato
ALERT_SECS = 600          # sin novedades, la alerta se va sola
ALERT_COOLDOWN_SECS = 900 # descartada con un clic, no vuelve a salir en este rato
CMD_OK_SECS = 120         # "terminó bien" es una buena noticia: se va pronto
CONTEXT_WARN = 90         # % de contexto de una sesión a partir del cual avisa
LIMIT_WARN = (80, 95)     # % del límite de 5 h en los que avisa
ASK_TIMEOUT = 600         # timeout del hook PermissionRequest en settings.json

DENY_MESSAGE = 'El usuario lo denegó desde la mascota ElYares.'

# Una alerta vieja queda debajo de cualquier sesión activa: si no, taparía
# durante minutos los avisos de Claude. Recién llegada vale ALERT_FRESH.
PRIORITY = {'permission': 4, 'waiting': 3, 'done': 2, 'working': 1, 'alert': .5}
ALERT_FRESH = 3.5

# Lo que se guarda de cada sesión entre reinicios del daemon.
SAVED_TEXT = ('cwd', 'pane', 'tmux', 'state', 'detail', 'last_tool', 'name', 'url', 'tone')
SAVED_NUM = ('ttl', 'context')
SAVED_TIMES = ('started', 'changed', 'updated')

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
    name: str = ''            # solo en alertas: el nombre a mostrar, sin cwd de donde sacarlo
    url: str = ''             # solo en alertas: lo que abre el clic
    tone: str = ''            # solo en alertas: '' problema, 'ok' buena noticia, 'info' aviso
    ttl: float = 0            # solo en alertas: segundos que dura sin novedades (0 = ALERT_SECS)
    context: float = 0        # % de la ventana de contexto que lleva usada la sesión
    changed: float = field(default_factory=time.monotonic)
    updated: float = field(default_factory=time.monotonic)

    @property
    def proj(self):
        return self.name or project_name(self.cwd)

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


class Model:
    def __init__(self):
        self.sessions = {}
        self.dismissed = {}       # alerta descartada -> cuándo
        self.focus = False        # hay un pomodoro en curso
        self.limit = 0.0          # % usado del límite de 5 h de Claude, el mismo para todas

    def dump(self):
        """Las sesiones como datos planos, para guardarlas entre reinicios."""
        return [{'sid': s.sid, **{k: getattr(s, k) for k in SAVED_TEXT + SAVED_NUM + SAVED_TIMES}}
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
            if s.state not in PRIORITY:
                s.state = 'idle'
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
        if ev == 'cmd-done':
            # Un comando largo de la terminal terminó: una alerta que lleva a su pane.
            rc, took = msg.get('exit_code') or 0, elapsed(msg.get('seconds') or 0)
            cmd = ' '.join((msg.get('command') or 'comando').split())
            head = 'Terminó' if rc == 0 else f'Falló (código {rc})'
            msg = {**msg, 'event': 'alert', 'name': project_name(msg.get('cwd') or ''),
                   'message': f'{head} en {took}: {cmd}', 'tone': 'ok' if rc == 0 else '',
                   'ttl': CMD_OK_SECS if rc == 0 else 0}
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
            s.set('alert', short(msg.get('message'), 300), now)
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
        elif ev == 'compact':
            s.set('working', 'Compactando el contexto…', now)
        elif ev == 'status':
            self._usage(s, msg, now)
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

    def _usage(self, s, msg, now):
        """Uso de Claude que manda la barra de estado: contexto de la sesión y
        límite de 5 h de la cuenta. Avisa al cruzar un umbral, no en cada dato."""
        try:
            context = float(msg.get('context_pct') or 0)
            limit = float(msg.get('limit_pct') or 0)
        except (TypeError, ValueError):
            return
        if s.context < CONTEXT_WARN <= context:
            self.handle({'event': 'alert', 'session_id': f'ctx:{s.sid}', 'name': s.proj,
                         'message': f'Contexto al {context:.0f}%: se va a compactar pronto',
                         'tone': 'info', 'pane': s.pane, 'tmux': s.tmux}, now=now)
        s.context = context
        for mark in LIMIT_WARN:
            if self.limit < mark <= limit:
                self.handle({'event': 'alert', 'session_id': f'limit:{mark}', 'name': 'Claude',
                             'message': f'Límite de 5 h al {limit:.0f}%',
                             'tone': 'info' if mark < LIMIT_WARN[-1] else ''}, now=now)
        if limit:
            self.limit = limit

    def dismiss(self, s, now=None):
        """Quita una alerta porque ya se atendió con un clic."""
        if self.sessions.pop(s.sid, None) is not None:
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

    def active(self):
        return [s for s in self.sessions.values() if s.state != 'idle']

    def view(self, now=None):
        now = now or time.monotonic()
        self._expire(now)
        # La más urgente primero; entre iguales, la que se movió al último.
        # Las que están en reposo (prioridad 0) quedan al final: no asoman la
        # isla, pero salen en la lista.
        def rank(s):
            if s.state == 'alert' and now - s.changed < ALERT_OPEN_SECS:
                return ALERT_FRESH
            return PRIORITY.get(s.state, 0)

        ranked = sorted(self.sessions.values(), key=lambda s: (-rank(s), -s.updated))
        count = sum(1 for s in ranked if s.state != 'alert')   # "N sesiones": las de Claude
        if not ranked or not rank(ranked[0]):
            return View(count=count, others=ranked)
        best = ranked[0]

        st = best.state
        if st == 'permission':
            mode, title = 'open', f'{best.proj} necesita permiso'
        elif st == 'done':
            mode, title = 'open', best.proj
        elif st == 'waiting':
            mode = 'open' if now - best.changed < WAITING_OPEN_SECS else 'peek'
            title = best.proj
        elif st == 'alert':
            mode = 'open' if now - best.changed < ALERT_OPEN_SECS else 'peek'
            title = best.proj
        else:
            mode, title = 'peek', best.proj
        if st == 'alert':
            pet = {'ok': 'done', 'info': 'confused'}.get(best.tone, 'annoyed')
        else:
            pet = {'waiting': 'confused'}.get(st, st)
        # En foco solo un permiso abre la isla; lo demás se queda asomado.
        if self.focus and mode == 'open' and st != 'permission':
            mode = 'peek'
        ask = st == 'permission' and best.ask is not None
        return View(mode, pet, title, best.detail, count, ask, best, (best.sid, st, ask),
                    ranked[1:])
