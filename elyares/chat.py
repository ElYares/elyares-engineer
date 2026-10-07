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

En la conversación queda lo que escribes y lo que contesta Claude, no lo que
hace por el camino: sus herramientas no se apuntan y lo que dice antes de
seguir trabajando se quita (`_settle`). Para verlo trabajar está el tablero.

Cuánto lleva lleno el contexto lo dice el propio Claude (`get_context_usage`,
al arrancar y al acabar cada turno); entre medias se saca de lo que gasta cada
respuesta (`context`, `tokens`, `window`).

Además de los "/", al escribir "@" se nombran los agentes y los archivos del
proyecto (`mentions`).

Una conversación se puede guardar y volver a armar (`dump`, `restore`): así
sobrevive a que la isla se vuelva a arrancar. Vuelve sin proceso; lo siguiente
que escribas lo abre con `--resume`.

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
       '--include-partial-messages', '--permission-prompts', 'host', '--permission-prompt-tool', 'stdio',
       '--allow-dangerously-skip-permissions']
# En bypass, Claude no pide permiso para casi nada; lo poco que sigue
# preguntando (escribir en settings, git o la configuración de herramientas)
# llega a la isla por el stdio. El modo plan se prende encima y, al
# apagarlo, se vuelve a este. `--allow-dangerously-skip-permissions` deja
# pasar a bypass a una conversación que arrancó en modo plan.
#
# Al aprobar un plan, Claude no vuelve al modo de antes: sale al de preguntar
# por todo ('default'). El chat lo devuelve a este (`Chat._mode`); si no, el
# resto del turno pide permiso para cada comando y cada edición.
BASE_MODE = 'bypassPermissions'
# Los modelos que se eligen desde el chat: (alias para Claude, nombre).
MODELS = (('opus', 'Opus 5.5'), ('sonnet', 'Sonnet 5.5'), ('haiku', 'Haiku 4.5'), ('fable', 'Fable 5.1'))
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
EFFORT_TEXT = {'low': 'bajo', 'medium': 'medio', 'high': 'alto', 'xhigh': 'muy alto', 'max': 'máximo'}
MODEL_ID = re.compile(r'claude-([a-z]+)-(\d+)-(\d+)')
MAX_ENTRIES = 400         # lo que se recuerda de la conversación para dibujarla
SAVED_ENTRIES = 80        # de eso, lo que se guarda entre reinicios de la isla
CUT_NOTE = 'La isla se reinició a medio turno; lo siguiente que escribas retoma la conversación'
MAX_FILES = 4000          # archivos del proyecto que se ofrecen al escribir "@"
MAX_MENTIONS = 40         # lo que cabe en la lista de "@"
FILES_SECS = 30           # cada cuánto se vuelven a listar los archivos del proyecto
DENY_MESSAGE = 'El usuario lo denegó desde el chat de elyares-engineer.'
QUESTION_TOOL = 'AskUserQuestion'     # pide elegir entre opciones, no permiso
# Los que modifican el repo: dos conversaciones suyas sobre la misma carpeta se
# pisarían, así que tienen una sola por proyecto. Los demás solo leen y reportan.
SINGLE_AGENTS = ('', 'elyares-mobile', 'elyares-devops')
MAX_CHATS = 5                         # conversaciones de un agente en un proyecto


def _tmux(*args):
    """Lo que contesta cada servidor de tmux a una orden: [líneas]."""
    lines = []
    for sock in glob.glob(f'/tmp/tmux-{os.getuid()}/*'):
        try:
            out = subprocess.run(['tmux', '-S', sock, *args], capture_output=True, text=True, timeout=1).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        lines += out.splitlines()
    return lines


def active_cwd(default=None):
    """La carpeta del pane de tmux en el que estás (el del cliente que se usó
    al último), o `default` (la carpeta personal) si no hay tmux. Los clientes
    anidados (sesiones ocultas `_*`, como la terminal flotante) no cuentan."""
    best = (-1, '')
    for line in _tmux('list-clients', '-F', '#{client_activity}\t#{client_session}\t#{pane_current_path}'):
        when, _, rest = line.partition('\t')
        name, _, path = rest.partition('\t')
        if when.isdigit() and not name.startswith('_') and os.path.isdir(path) and int(when) > best[0]:
            best = (int(when), path)
    return best[1] or (os.path.expanduser('~') if default is None else default)


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


def local_files(cwd):
    """Los archivos del proyecto, como los ve git (sin lo ignorado), para
    nombrarlos con "@". [] si la carpeta no es un repositorio."""
    try:
        out = subprocess.run(['git', '-C', cwd, 'ls-files', '--cached', '--others', '--exclude-standard'],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return out.splitlines()[:MAX_FILES]


def tokens_text(n):
    """Una cuenta de tokens para leerla de un vistazo: 87767 -> "88k"."""
    return f'{n / 1e6:.1f}M' if n >= 1e6 else f'{n / 1e3:.0f}k' if n >= 1e3 else str(int(n))


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
    kind: str                 # you | flow (lo que manda un workflow) | claude | note | error | foot (el pie de un turno)
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
        self.agents = list(state.AGENT_ROLES)     # los agentes que se nombran con "@"
        self.files, self.files_at = [], None      # los archivos del proyecto, y cuándo se listaron
        self.tokens = 0           # lo que lleva en el contexto, en tokens
        self.window = 0           # lo que le cabe
        self.streaming = False    # la última entrada de Claude se sigue escribiendo
        self.cut = False          # se pidió cortar el turno en curso
        self.closing = False
        self.touched = time.monotonic()   # cuándo se usó por última vez

    @property
    def project(self):
        return state.project_name(self.cwd)

    def dump(self):
        """Lo que se guarda de la conversación entre reinicios de la isla."""
        return {'agent': self.agent, 'cwd': self.cwd, 'session': self.session, 'model': self.model,
                'effort': self.effort, 'model_id': self.model_id, 'plan': self.plan, 'busy': self.busy,
                'tokens': self.tokens, 'window': self.window,
                'entries': [[e.kind, e.text, e.images] for e in self.entries[-SAVED_ENTRIES:]]}

    @classmethod
    def restore(cls, data, emit, spawn=subprocess.Popen):
        """La conversación que se guardó con `dump`, sin proceso: lo siguiente
        que se escriba la retoma. None si lo guardado no sirve."""
        text = {key: data.get(key) if isinstance(data.get(key), str) else ''
                for key in ('agent', 'cwd', 'session', 'model', 'effort', 'model_id')}
        if not text['cwd']:
            return None
        c = cls(text['cwd'], emit, spawn, text['agent'], text['model'], text['effort'])
        c.session, c.model_id, c.plan = text['session'], text['model_id'], data.get('plan') is True
        for key in ('tokens', 'window'):
            if isinstance(data.get(key), int) and data[key] > 0:
                setattr(c, key, data[key])
        for entry in data.get('entries') if isinstance(data.get('entries'), list) else []:
            if (isinstance(entry, list) and len(entry) == 3 and all(isinstance(v, str) for v in entry[:2])
                    and isinstance(entry[2], int)):
                c.entries.append(Entry(*entry))
        if data.get('busy') is True:
            c._add('note', CUT_NOTE)
        return c

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

    @property
    def context(self):
        """El % del contexto que lleva lleno, o 0 si aún no se sabe."""
        return min(100.0, 100 * self.tokens / self.window) if self.window else 0.0

    def mentions(self, word, files=local_files, now=None):
        """Lo que se puede nombrar con "@" que case con `word`: primero los
        agentes y luego los archivos del proyecto, los que empiezan así antes
        que los que solo lo contienen. [(nombre, qué es)]."""
        now = time.monotonic() if now is None else now
        if self.files_at is None or now - self.files_at > FILES_SECS:
            self.files, self.files_at = files(self.cwd), now
        word = word.lower()
        found = [(name, 'agente') for name in self.agents if word in name.lower()]

        def rank(path):
            low = path.lower()
            return (not os.path.basename(low).startswith(word), not low.startswith(word), len(path), path)

        paths = sorted((p for p in self.files if word in p.lower()), key=rank)
        return (found + [(path, '') for path in paths])[:MAX_MENTIONS]

    def send(self, text, images=(), shown=None, kind='you'):
        """Le manda a Claude lo que escribiste, con las imágenes pegadas (PNG
        en bytes). Con un turno en curso, Claude lo deja en cola y lo atiende
        al terminar. False si no había nada. En la conversación queda `shown`
        si se da (lo que se ve de un mensaje largo o con instrucciones para
        Claude) y no `text`; `kind` es 'flow' para lo que manda un workflow."""
        text = text.strip()
        if not text and not images:
            return False
        if not self.alive:
            self.start()
        self.touched = time.monotonic()
        content = text
        if images:
            content = [{'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png',
                                                    'data': base64.b64encode(png).decode()}}
                       for png in images] + [{'type': 'text', 'text': text or 'Mira la imagen.'}]
        if not self._write({'type': 'user', 'message': {'role': 'user', 'content': content}}):
            self._add('error', 'No se pudo hablar con Claude')
            return False
        self._add(kind, text if shown is None else shown, len(images))
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

    def questions(self):
        """Las preguntas de opciones que Claude hace ahora, como
        [{question, header, multi, options: [(label, description)]}]; [] si
        lo pendiente no es una pregunta."""
        ask = self.asking
        if not ask or ask['tool'] != QUESTION_TOOL:
            return []
        out = []
        for q in (ask['input'].get('questions') or [])[:4]:
            if not isinstance(q, dict) or not isinstance(q.get('question'), str):
                continue
            options = [(str(o.get('label') or ''), str(o.get('description') or ''))
                       for o in q.get('options') or [] if isinstance(o, dict) and o.get('label')]
            if options:
                out.append({'question': q['question'], 'header': str(q.get('header') or ''),
                            'multi': bool(q.get('multiSelect')), 'options': options})
        return out

    def answer_questions(self, answers):
        """Contesta las preguntas pendientes: `answers` va de cada pregunta a
        lo que se eligió (varias opciones, separadas por coma)."""
        ask, self.asking = self.asking, None
        if ask is None:
            return False
        self._add('note', 'Respondiste: ' + ' · '.join(answers.values()))
        decision = {'behavior': 'allow', 'updatedInput': {**ask['input'], 'answers': answers}}
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
        self.touched = time.monotonic()
        if kind == 'system' and event.get('subtype') == 'init':
            self.session = event.get('session_id') or self.session
            self.model_id = event.get('model') or self.model_id
            self._mode(event.get('permissionMode', ''))
            # Los suyos manda Claude; las descripciones, las que ya se sabían.
            names = [*(event.get('slash_commands') or []), *(event.get('skills') or [])]
            self.commands = {n: self.commands.get(n, '') for n in names if isinstance(n, str)}
            agents = [a for a in event.get('agents') or [] if isinstance(a, str)]
            self.agents = agents or self.agents
            self._control({'subtype': 'get_context_usage'})
            return True
        if kind == 'system' and event.get('subtype') == 'status' and event.get('permissionMode'):
            self._mode(event['permissionMode'])
            return True
        if kind in ('stream_event', 'assistant') and event.get('parent_tool_use_id'):
            return False                      # lo de un subagente: ni es la respuesta ni gasta este contexto
        if kind == 'stream_event':
            return self._stream(event.get('event') or {})
        if kind == 'assistant':
            message = event.get('message') or {}
            changed = self._spent(message.get('usage'))
            for block in message.get('content') or []:
                changed |= self._block(block)
            return changed
        if kind == 'control_response':
            answer = (event.get('response') or {}).get('response')
            return isinstance(answer, dict) and self._measured(answer)
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
            else:
                self._control({'subtype': 'get_context_usage'})
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

    def _mode(self, mode):
        """El modo de permisos que dice Claude. Fuera del modo plan, el del
        chat es `BASE_MODE`: si Claude está en otro (al aprobar un plan sale a
        'default'), se le devuelve."""
        self.plan = mode == 'plan'
        if mode and mode not in ('plan', BASE_MODE):
            self._control({'subtype': 'set_permission_mode', 'mode': BASE_MODE})

    def _spent(self, usage):
        """Lo que ocupaba el contexto al pedir esta respuesta, según su gasto."""
        if not isinstance(usage, dict):
            return False
        tokens = sum(int(usage.get(key) or 0) for key in
                     ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
        if not tokens or tokens == self.tokens:
            return False
        self.tokens = tokens
        return True

    def _measured(self, answer):
        """La cuenta que da Claude de su contexto (`get_context_usage`)."""
        try:
            tokens, window = int(answer.get('totalTokens') or 0), int(answer.get('maxTokens') or 0)
        except (TypeError, ValueError):
            return False
        if not window or (tokens, window) == (self.tokens, self.window):
            return False
        self.tokens, self.window = tokens, window
        return True

    def _settle(self):
        """Claude sigue trabajando: lo que dijo en este turno no era la
        respuesta, y se quita. Lo que hace se ve en el tablero."""
        for i in range(len(self.entries) - 1, -1, -1):
            if self.entries[i].kind == 'foot':
                break
            if self.entries[i].kind == 'claude':
                del self.entries[i]

    def _block(self, block):
        """Un bloque ya completo de la respuesta: el texto manda sobre lo que
        se fue escribiendo; una herramienta dice que eso no era la respuesta."""
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
            self._settle()
            return True
        return False
