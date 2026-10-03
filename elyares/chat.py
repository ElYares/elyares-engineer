"""El chat con Claude desde la isla.

La isla abre una conversación con Claude Code sin terminal: un proceso
`claude -p` que lee y escribe JSON por línea (`stream-json`). Lo que escribes
va por su stdin; su stdout trae la respuesta mientras se escribe, las
herramientas que usa y, cuando algo pide permiso, la pregunta, que contesta
la isla (`--permission-prompt-tool stdio`). El mismo proceso sigue la
conversación turno tras turno, y cortar un turno no lo mata.

Los comandos con "/" (las skills: /contexto, /bitacora, /commit…) los entiende
el propio Claude; la lista para autocompletarlos la da al arrancar (`init`).

El chat arranca en la carpeta del pane de tmux activo (`active_cwd`): ahí
trabaja Claude, como si lo hubieras abierto en ese pane.

El modelo y el modo plan se cambian en caliente (`set_model`,
`set_permission_mode`). El esfuerzo no: Claude solo lo toma al arrancar
(`--effort`), así que cambiarlo cierra el proceso entre turnos y lo siguiente
que escribas lo retoma con el esfuerzo nuevo (`--resume`).

Lo que escribes puede llevar imágenes (las que pegas con Ctrl+V): van como
bloques `image` antes del texto.

`Chat` no sabe nada de la pantalla: `feed()` recibe cada evento de Claude y
actualiza lo que la isla dibuja (`entries`, `busy`, `asking`). `emit` lo llama
el hilo que lee a Claude; la isla lo pasa a su hilo antes de llamar a `feed()`.
"""

import base64
import glob
import itertools
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass

from . import state

CMD = ['claude', '-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
       '--include-partial-messages', '--permission-prompts', 'host', '--permission-prompt-tool', 'stdio']
# En bypass, Claude no pide permiso para casi nada; lo poco que sigue
# preguntando (escribir en settings, git o la configuración de herramientas)
# llega a la isla por el stdio. El modo plan se prende encima y, al
# apagarlo, se vuelve a este.
BASE_MODE = 'bypassPermissions'
# Los modelos que se eligen desde el chat: (alias para Claude, nombre).
MODELS = (('opus', 'Opus 5.5'), ('sonnet', 'Sonnet 5.5'), ('haiku', 'Haiku 4.5'), ('fable', 'Fable 5.1'))
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
EFFORT_TEXT = {'low': 'bajo', 'medium': 'medio', 'high': 'alto', 'xhigh': 'muy alto', 'max': 'máximo'}
MODEL_ID = re.compile(r'claude-([a-z]+)-(\d+)-(\d+)')
MAX_ENTRIES = 400         # lo que se recuerda de la conversación para dibujarla
DENY_MESSAGE = 'El usuario lo denegó desde el chat de elyares-engineer.'


def active_cwd():
    """La carpeta del pane de tmux en el que estás (el del cliente que se usó
    al último), o la carpeta personal si no hay tmux."""
    best = (-1, '')
    for sock in glob.glob(f'/tmp/tmux-{os.getuid()}/*'):
        try:
            out = subprocess.run(['tmux', '-S', sock, 'list-clients', '-F',
                                  '#{client_activity} #{pane_current_path}'],
                                 capture_output=True, text=True, timeout=1).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for line in out.splitlines():
            when, _, path = line.partition(' ')
            if when.isdigit() and os.path.isdir(path) and int(when) > best[0]:
                best = (int(when), path)
    return best[1] or os.path.expanduser('~')


def local_commands(cwd=''):
    """Los "/" que hay antes de que Claude diga los suyos: las skills y los
    comandos propios, de `~/.claude` y del proyecto. {nombre: descripción}."""
    found = {}
    for base in (os.path.expanduser('~/.claude'), os.path.join(cwd, '.claude') if cwd else ''):
        if not base:
            continue
        for path in glob.glob(os.path.join(base, 'skills', '*', 'SKILL.md')):
            found[os.path.basename(os.path.dirname(path))] = _description(path)
        for path in glob.glob(os.path.join(base, 'commands', '*.md')):
            found[os.path.splitext(os.path.basename(path))[0]] = _description(path)
    return found


def _description(path):
    """La `description:` del encabezado de una skill o un comando, o ''."""
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            head = f.read(4000)
    except OSError:
        return ''
    if not head.startswith('---'):
        return ''
    lines = head.split('\n')[1:]
    for i, line in enumerate(lines):
        if line.startswith('---'):
            break
        if line.startswith('description:'):
            value = line.partition(':')[2].strip()
            if value in ('>', '|', '>-', '|-'):
                # En varias líneas: las que siguen, con sangría.
                more = itertools.takewhile(lambda rest: rest.startswith((' ', '\t')), lines[i + 1:])
                value = ' '.join(rest.strip() for rest in more if rest.strip())
            return value.strip('"\'')
    return ''


def model_name(model_id):
    """El nombre de un modelo para leerlo: "claude-opus-5-5" -> "Opus 5.5"."""
    m = MODEL_ID.match(model_id or '')
    return f'{m[1].capitalize()} {m[2]}.{m[3]}' if m else (model_id or '')


def default_effort(model_id, path=None):
    """El esfuerzo que usa Claude con un modelo si no se le dice otro: el de
    ese modelo en `~/.claude/settings.json` (`modelSettings`) o el general."""
    try:
        with open(path or os.path.expanduser('~/.claude/settings.json')) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ''
    m = MODEL_ID.match(model_id or '')
    key = f'claude-{m[1]}-{m[2]}-{m[3]}' if m else model_id
    per_model = ((data.get('modelSettings') or {}).get(key) or {}).get('effortLevel')
    return per_model or data.get('effortLevel') or ''


@dataclass
class Entry:
    """Una cosa de la conversación, como la dibuja la isla."""
    kind: str                 # you | claude | tool | note | error | foot (el pie de un turno)
    text: str
    images: int = 0           # solo en lo tuyo: cuántas imágenes llevaba


class Chat:
    """Una conversación. `agent` es el de la familia con el que se habla
    ('' es elyares-engineer, la sesión de siempre); `model` y `effort`, lo
    elegido ('' deja lo que use Claude)."""

    def __init__(self, cwd, emit, spawn=subprocess.Popen, agent='', model='', effort=''):
        self.cwd, self.emit, self.spawn = cwd, emit, spawn
        self.agent, self.model, self.effort = agent, model, effort
        self.model_id = ''        # el modelo con el que contesta, según Claude
        self.plan = False         # modo plan: analiza y propone, no toca nada
        self.restart = False      # cerrar el proceso al acabar el turno (cambió el esfuerzo)
        self.proc = None
        self.session = ''         # el id que le da Claude a la conversación
        self.entries = []
        self.busy = False         # hay un turno en curso
        self.asking = None        # el permiso pendiente: {id, tool, input, text}
        self.commands = local_commands(cwd)   # los "/" que entiende: {nombre: descripción}
        self.streaming = False    # la última entrada de Claude se sigue escribiendo
        self.cut = False          # se pidió cortar el turno en curso
        self.closing = False

    @property
    def project(self):
        return state.project_name(self.cwd)

    def start(self):
        """Arranca el proceso de Claude; si ya hubo conversación, la retoma."""
        cmd = (CMD + ['--permission-mode', 'plan' if self.plan else BASE_MODE]
               + (['--agent', self.agent] if self.agent else [])
               + (['--model', self.model] if self.model else [])
               + (['--effort', self.effort] if self.effort else [])
               + (['--resume', self.session] if self.session else []))
        self.proc = self.spawn(cmd, cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True, name='chat').start()

    def _read(self, proc):
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                self.emit(event)
        self.emit({'type': 'exit', 'proc': proc})

    def _write(self, obj):
        try:
            self.proc.stdin.write(json.dumps(obj) + '\n')
            self.proc.stdin.flush()
            return True
        except (OSError, ValueError, AttributeError):
            return False

    def _add(self, kind, text, images=0):
        self.entries.append(Entry(kind, text, images))
        del self.entries[:-MAX_ENTRIES]

    @property
    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def name(self):
        return self.agent or state.MAIN_AGENT

    def send(self, text, images=()):
        """Le manda a Claude lo que escribiste, con las imágenes pegadas (PNG
        en bytes). Con un turno en curso, Claude lo deja en cola y lo atiende
        al terminar. False si no había nada."""
        text = text.strip()
        if not text and not images:
            return False
        if not self.alive:
            self.start()
        content = text
        if images:
            content = [{'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png',
                                                    'data': base64.b64encode(png).decode()}}
                       for png in images] + [{'type': 'text', 'text': text or 'Mira la imagen.'}]
        if not self._write({'type': 'user', 'message': {'role': 'user', 'content': content}}):
            self._add('error', 'No se pudo hablar con Claude')
            return False
        self._add('you', text, len(images))
        self.busy, self.cut = True, False
        return True

    def _control(self, request):
        return self._write({'type': 'control_request', 'request_id': f'isla-{time.monotonic_ns()}',
                            'request': request})

    def set_model(self, alias):
        """Cambia de modelo; con Claude abierto, desde el siguiente mensaje."""
        self.model = alias
        if self.alive:
            self._control({'subtype': 'set_model', 'model': alias})

    def set_effort(self, level):
        """Cambia el esfuerzo. Claude solo lo toma al arrancar: se cierra
        (al acabar el turno, si hay uno) y lo siguiente lo retoma con este."""
        self.effort = level
        if self.alive:
            if self.busy:
                self.restart = True
            else:
                self.close()

    def toggle_plan(self):
        """Prende o apaga el modo plan."""
        self.plan = not self.plan
        if self.alive:
            self._control({'subtype': 'set_permission_mode', 'mode': 'plan' if self.plan else BASE_MODE})

    def reply(self):
        """Lo último que contestó Claude, o ''."""
        return next((e.text for e in reversed(self.entries) if e.kind == 'claude'), '')

    def interrupt(self):
        """Corta el turno en curso, como Esc en la terminal. La conversación sigue."""
        if not self.busy:
            return False
        if self.asking:
            self.answer(False)
        self.cut = True
        return self._control({'subtype': 'interrupt'})

    def answer(self, allow):
        """Contesta el permiso pendiente."""
        ask, self.asking = self.asking, None
        if ask is None:
            return False
        decision = ({'behavior': 'allow', 'updatedInput': ask['input']} if allow
                    else {'behavior': 'deny', 'message': DENY_MESSAGE})
        if not allow:
            self._add('note', f'Denegado: {ask["text"]}')
        return self._write({'type': 'control_response',
                            'response': {'subtype': 'success', 'request_id': ask['id'], 'response': decision}})

    def close(self):
        """Cierra el proceso de Claude. La conversación se puede retomar."""
        self.closing = True
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            self.proc.terminate()

    def describe(self, name, tool_input):
        return state.describe_tool(name or '', tool_input, state.project_root(self.cwd))

    def feed(self, event):
        """Un evento de Claude. True si cambió lo que se ve."""
        kind = event.get('type')
        if kind == 'system' and event.get('subtype') == 'init':
            self.session = event.get('session_id') or self.session
            self.model_id = event.get('model') or self.model_id
            self.plan = event.get('permissionMode', '') == 'plan'
            # Los suyos manda Claude; las descripciones, las que ya se sabían.
            names = [*(event.get('slash_commands') or []), *(event.get('skills') or [])]
            self.commands = {n: self.commands.get(n, '') for n in names if isinstance(n, str)}
            return True
        if kind == 'system' and event.get('subtype') == 'status' and event.get('permissionMode'):
            self.plan = event['permissionMode'] == 'plan'
            return True
        if kind == 'stream_event':
            return self._stream(event.get('event') or {})
        if kind == 'assistant':
            changed = False
            for block in (event.get('message') or {}).get('content') or []:
                changed |= self._block(block)
            return changed
        if kind == 'control_request':
            req = event.get('request') or {}
            if req.get('subtype') != 'can_use_tool':
                return False
            tool_input = req.get('input') if isinstance(req.get('input'), dict) else {}
            self.asking = {'id': event.get('request_id'), 'tool': req.get('tool_name') or '',
                           'input': tool_input, 'text': self.describe(req.get('tool_name'), tool_input)}
            return True
        if kind == 'result':
            self.busy = self.streaming = False
            self.asking = None
            if self.cut:
                self._add('note', 'Turno cortado')
            elif event.get('is_error'):
                self._add('error', str(event.get('result') or event.get('subtype') or 'Algo falló'))
            took = (event.get('duration_ms') or 0) / 1000
            when = f'{took:.1f} s' if took < 60 else state.elapsed(took)
            if took or self.model_id:
                parts = (self.name, model_name(self.model_id), when if took else '')
                self._add('foot', ' · '.join(p for p in parts if p))
            self.cut = False
            if self.restart:
                self.restart = False
                self.close()
            return True
        if kind == 'exit':
            if event.get('proc') is not self.proc:
                return False                  # uno viejo, tras empezar de nuevo
            self.busy = self.streaming = False
            self.asking = None
            if not self.closing:
                self._add('note', 'Claude se cerró; lo siguiente que escribas lo vuelve a abrir')
            self.proc, self.closing = None, False
            return True
        return False

    def _stream(self, ev):
        """Un trozo de la respuesta mientras se escribe."""
        if ev.get('type') == 'content_block_start' and (ev.get('content_block') or {}).get('type') == 'text':
            self._add('claude', '')
            self.streaming = True
            return True
        delta = ev.get('delta') or {}
        if ev.get('type') == 'content_block_delta' and delta.get('type') == 'text_delta':
            if not (self.streaming and self.entries and self.entries[-1].kind == 'claude'):
                self._add('claude', '')
                self.streaming = True
            self.entries[-1].text += delta.get('text') or ''
            return True
        return False

    def _block(self, block):
        """Un bloque ya completo de la respuesta: el texto manda sobre lo que
        se fue escribiendo; una herramienta se apunta como un paso."""
        if block.get('type') == 'text':
            text = block.get('text') or ''
            if self.streaming and self.entries and self.entries[-1].kind == 'claude':
                self.entries[-1].text = text
            elif text.strip():
                self._add('claude', text)
            self.streaming = False
            return True
        if block.get('type') == 'tool_use':
            self.streaming = False
            self._add('tool', self.describe(block.get('name'), block.get('input')))
            return True
        return False
