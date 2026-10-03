"""El chat dentro de la isla: el panel donde se le piden las cosas a Claude.

Se abre con `elyares-ctl chat` (o la pastilla «Chat» del pie) y ocupa la
isla. Arriba, la mascota con «agente | proyecto» y cómo va el turno; en
medio, la conversación al estilo de OpenCode: lo tuyo en un bloque con una
barra del color del agente, lo de Claude con su markdown, sus pasos en una
línea tenue y, al acabar cada turno, su pie (`▣ agente · modelo · tiempo`).
Abajo, la caja de texto, que crece con lo que escribes hasta CHAT_INPUT_LINES
líneas y luego hace scroll; debajo de ella, la línea de estado: con quién
hablas, el modelo, el esfuerzo y el modo plan, cada uno con su clic.

El chat es para pedir; a Claude se le ve trabajar en el tablero. Al mandar
algo el panel se cierra y la isla vuelve al tablero, con la pestaña de la
conversación (`· chat`) y el agente al frente con sus pasos. Si pide permiso,
se contesta en la tarjeta del tablero, como el de cualquier sesión (`ChatAsk`).
Al terminar, un aviso con el principio de la respuesta y el botón «Ver
respuesta», que abre el chat.

Con el chat abierto, el permiso sale también en una tarjeta encima de la
caja.

Cada uno de la familia tiene su conversación (`chats`): en la línea de
estado, un clic en el nombre del agente elige con quién hablas, y en el tablero el desglose de cada uno tiene
«hablarle ›». La de un agente corre como él (`claude -p --agent X`), con su
modelo; en el tablero sale con su cara. Al escribir "/" sale la lista de comandos para elegir con las flechas y
Tab. Ctrl+V pega texto y también imágenes: van en etiquetas encima de la caja
y salen con el siguiente mensaje.

El mini chat: para encargarle algo a uno de los tres sin abrir el panel. Un
clic en él, en el tablero, abre su desglose con una caja al pie (`draw_brief`);
Enter se lo manda a su conversación, en la carpeta de esa pestaña, y la isla
vuelve al tablero. Lo que hace no saca pestaña propia: se ve en su tarjeta de
la pestaña desde la que se le encargó (`chat_hosts`, `crew`, `host`), al lado
de los demás que trabajan.

El teclado: la isla es una capa de layer-shell que normalmente no lo toma.
Mientras escribes lo toma entero (`EXCLUSIVE`); Esc lo suelta sin cerrar el
chat, y un clic en la caja lo vuelve a tomar. Si pasan CHAT_IDLE_SECS sin
teclear lo suelta solo: un descuido no deja la máquina sin teclado. Enter
manda y Shift+Enter cambia de línea; Shift+Tab prende o apaga el modo plan;
Ctrl+C sin nada seleccionado corta el turno.

La conversación la lleva `chat.Chat`; aquí solo se dibuja y se escucha.
`ChatView` es parte de la isla (`app.Island` la hereda): usa sus ayudantes
de dibujo (`_layout`, `tip_text`, `draw_button`, `face`, `ink`, `who`).
"""

import html
import time

from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo
from gi.repository import Gtk4LayerShell as LayerShell

from . import chat, mascot, paint, settings, state

CHAT_W, CHAT_H = 600, 620     # el panel: ancho de la isla con vista previa, y alto
CHAT_PAD = 16                 # margen por dentro
CHAT_HEAD = 50                # la cabecera: mascota, título y cómo va
CHAT_FACE = 34                # la mascota de la cabecera
CHAT_PICK_FACE = 20           # las caras del menú para elegir con quién hablas
CHAT_INPUT_LINES = 6          # lo que crece la caja antes de hacer scroll
CHAT_INPUT_PAD = 9            # relleno de la caja, arriba y abajo
CHAT_INPUT_INSET = 14         # dónde empieza el texto de la caja, tras su barra
CHAT_BAR = 3                  # la barra de color de la caja y de tus mensajes
CHAT_STATUS_H = 18            # la línea de estado, debajo de la caja
CHAT_GAP = 10                 # entre una cosa de la conversación y la siguiente
CHAT_INDENT = 12              # lo de Claude, un poco adentro: alineado con el texto de tus bloques
CHAT_BLOCK_PAD = 9            # relleno de tus bloques
CHAT_SCROLL = 48              # lo que baja o sube la conversación con cada paso de la rueda
CHAT_SUGGEST = 6              # comandos que se ven a la vez en la lista de "/"
CHAT_SUGGEST_H = 24           # alto de cada uno, y de cada opción de un menú
CHAT_ASK_H = 74               # la tarjeta del permiso
CHAT_CHIP_H = 22              # las etiquetas de las imágenes pegadas
CHAT_MAX_IMAGES = 5
CHAT_SHOW_AT = 40             # la caja de texto sale cuando a la isla le falta esto para abrirse
CHAT_LINK_GAP = 14            # entre los enlaces de la cabecera (Detener, Nuevo, Cerrar)
CHAT_IDLE_SECS = 90           # sin teclear tanto rato, el chat suelta el teclado solo
CHAT_REPLY_SECS = 900         # lo que dura el aviso de «ver respuesta» si no se atiende
CHAT_REPLY_LINES = 8          # de la respuesta, lo que se lee en su aviso
CHAT_WATCH_SECS = 6           # al mandar, la isla se abre en el tablero este rato (si no está fijada)
MINI_H = 60                   # lo que crece un desglose para su mini chat: la caja y su línea de estado
MINI_LINES = 3                # lo que crece la caja del mini chat antes de hacer scroll
FONT_CHAT = 'Sans 10'                             # lo que escribe Claude: prosa, se lee mejor
FONT_YOU = 'JetBrainsMono Nerd Font Medium 9'    # lo que escribes tú
FONT_INPUT = 'JetBrainsMono Nerd Font 10'        # la caja: el mismo que pone su CSS
FONT_STEP = 'JetBrainsMono Nerd Font 9'          # sus pasos y la línea de estado
FONT_LINK = 'Sans Semi-Bold 9'
FONT_HINT = 'Sans 10'
TITLE = (.95, .96, 1)
PLACEHOLDER = 'Pídele algo a {agent} · / para los comandos · Shift+Enter, otra línea'
CSS = '''
textview.elyares-chat, textview.elyares-chat text, scrolledwindow.elyares-chat {
  background: transparent; border: none; box-shadow: none; outline: none;
}
textview.elyares-chat, textview.elyares-chat text {
  color: #eef1f6; caret-color: %s; font-family: "JetBrainsMono Nerd Font"; font-size: 10pt;
}
'''


class ChatAsk:
    """El permiso que pide un chat, para el tablero: se porta como el de un
    hook `ask` (`ipc.Request`), así que contestarlo en la tarjeta del tablero
    lo contesta en el chat."""

    def __init__(self, conversation):
        self.chat, self.done, self.born = conversation, False, time.time()

    def reply(self, answer):
        if self.done:
            return
        self.done = True
        if answer and answer.get('behavior') in ('allow', 'deny'):
            self.chat.answer(answer['behavior'] == 'allow')


def plain(text):
    """Lo que escribió Claude sin las marcas de markdown, para leerlo en un aviso."""
    out = []
    for line in (text or '').split('\n'):
        line = line.strip().lstrip('#').strip().replace('**', '').replace('`', '')
        if line and not set(line) <= set('|-: '):
            out.append(line)
    return out


class ChatView:
    """El chat de la isla. Lo que guarda: `chat` (la conversación, o None),
    `chat_open`, `chat_typing` (tiene el teclado), `chat_scroll` (cuánto se
    subió desde el final), `chat_pick` (el comando elegido de la lista),
    `chat_menu` (el menú abierto: 'model', 'effort' o None), `chat_images`
    (lo pegado, en PNG) y `chat_cache` (lo ya medido de la conversación)."""

    def chat_init(self):
        self.chat = None
        self.chat_open = self.chat_typing = self.chat_quiet = False
        self.chat_scroll, self.chat_pick, self.chat_cache = 0.0, 0, {}
        self.chat_menu, self.chat_images = None, []
        self.chat_sessions = set()    # las sesiones (del tablero) que son de un chat
        self.chats = {}               # la conversación de cada uno: agente ('' el engineer) -> Chat
        self.chat_watch = False       # se acaba de mandar algo: el tablero sigue a su sesión
        self.chat_box = None          # dónde va el texto de la caja, como lo midió el último dibujo
        self.chat_keyed = 0.0         # cuándo se tecleó por última vez en el chat
        self.chat_hosts = {}          # los encargos del tablero: agente -> la sesión de la pestaña desde la que se hizo
        self.chat_whom = None         # para quién es lo escrito en la caja: 'chat' o el agente de un mini chat
        self.entry = self.entry_box = None

    def chat_widgets(self, overlay):
        """La caja de texto: un Gtk.TextView de verdad, dentro de su scroll,
        encima del dibujo, que se pone donde el dibujo dejó su sitio."""
        view = Gtk.TextView()
        view.add_css_class('elyares-chat')
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_accepts_tab(False)
        view.get_buffer().connect('changed', self.on_chat_changed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.on_chat_key)
        view.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect('pressed', lambda *_: self.chat_type(True))
        view.add_controller(click)
        box = Gtk.ScrolledWindow()
        box.add_css_class('elyares-chat')
        box.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.set_child(view)
        box.set_halign(Gtk.Align.START)
        box.set_valign(Gtk.Align.START)
        box.set_visible(False)
        overlay.add_overlay(box)
        self.entry, self.entry_box = view, box
        self.chat_css = Gtk.CssProvider()
        self.chat_theme()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.chat_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', self.on_chat_scroll)
        self.da.add_controller(scroll)

    def chat_theme(self):
        """El cursor de la caja, en el color de acento del tema."""
        if getattr(self, 'chat_css', None) is not None:
            self.chat_css.load_from_string(CSS % mascot.accent('engineer'))

    def chat_text(self):
        if self.entry is None:
            return ''
        buf = self.entry.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def chat_set_text(self, text):
        if self.entry is None:
            return
        buf = self.entry.get_buffer()
        buf.set_text(text)
        buf.place_cursor(buf.get_end_iter())

    def chat_claim(self, whom):
        """La caja es una sola: lo que quedó escrito para otro (en el chat o
        en el mini chat de un agente) no se le manda a este."""
        if whom != self.chat_whom:
            self.chat_whom = whom
            self.chat_images = []
            if self.chat_text():
                self.chat_set_text('')

    # ── abrir, cerrar y el teclado ──────────────────────────────────────────

    def toggle_chat(self):
        """Abre el chat con el teclado listo para escribir; otra vez, lo cierra."""
        if self.chat_open:
            self.close_chat()
        else:
            self.open_chat(typing=True)

    def chat_for(self, agent, cwd=''):
        """La conversación con uno de la familia ('' es el engineer); si no
        hay, una nueva en `cwd` o, sin él, en la carpeta de la que se tenía a
        la vista o en la del pane activo. La de un agente usa su modelo, no el
        elegido para el engineer. Con `cwd` de otro proyecto, la que tenía en
        reposo se cierra y empieza una ahí."""
        c = self.chats.get(agent)
        if c is not None and cwd and not c.busy and state.project_root(c.cwd) != state.project_root(cwd):
            c.close()
            c = None
        if c is None:
            cwd = cwd or (self.chat.cwd if self.chat is not None else chat.active_cwd())
            pick = {} if agent else {'model': self.settings.get('chat_model', ''),
                                     'effort': self.settings.get('chat_effort', '')}
            c = chat.Chat(cwd, None, agent=agent, **pick)
            c.emit = lambda ev, c=c: GLib.idle_add(self.on_chat, ev, c)
            self.chats[agent] = c
        return c

    def open_chat(self, typing=False, agent=None):
        """Abre el chat; con `agent`, el de ese de la familia ('' el engineer)."""
        if agent is not None or self.chat is None:
            self.chat = self.chat_for(agent or '')
            self.chat_cache.clear()
            self.chat_scroll, self.chat_menu = 0.0, None
        self.chat_open, self.off = True, False
        self.chat_claim('chat')
        if self.chat.session:
            # Ya se está leyendo: su aviso sobra.
            self.model.sessions.pop(f'chat:{self.chat.session}', None)
        if typing:
            self.chat_type(True)
        self.ensure_tick()

    def close_chat(self):
        """Cierra el panel. La conversación sigue viva: al abrirlo, ahí está."""
        self.chat_open, self.chat_menu = False, None
        self.chat_type(False)
        if self.entry_box is not None:
            self.entry_box.set_visible(False)
        self.ensure_tick()

    def new_chat(self):
        """Empieza otra conversación con el mismo agente, en la carpeta del
        pane activo de ahora."""
        agent = self.chat.agent if self.chat is not None else ''
        if self.chat is not None:
            self.chat.close()
        self.chats.pop(agent, None)
        self.chat = None
        self.open_chat(typing=True, agent=agent)

    def chat_type(self, on):
        """Toma el teclado para escribir, o lo suelta."""
        self.chat_typing = bool(on) and (self.chat_open or self.briefing() is not None)
        self.chat_keyed = time.monotonic()
        win = getattr(self, 'win', None)
        if win is not None:
            LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.EXCLUSIVE if self.chat_typing
                                         else LayerShell.KeyboardMode.NONE)
        if self.chat_typing and self.entry is not None:
            self.entry_box.set_visible(True)
            self.entry.grab_focus()
        self.ensure_tick()

    def chat_tick(self, now):
        """Cada segundo: suelta el teclado si hace rato que no se teclea."""
        if self.chat_typing and now - self.chat_keyed > CHAT_IDLE_SECS:
            if self.chat_open:
                self.chat_type(False)
            else:
                self.brief_drop()

    # ── el mini chat: encargarle algo a uno desde el tablero ────────────────

    def briefing(self):
        """(sesión, agente) del mini chat que hay a la vista: el del desglose
        de uno de los tres, en el tablero. None si no hay."""
        if self.chat_open or self.target() != 'board':
            return None
        found = self.focused()
        if found is None or found[1].role == state.MAIN_ROLE:
            return None
        return found[0], state.ROLE_AGENTS[found[1].role]

    def chat_now(self):
        """La conversación a la que va lo que se teclea: la del chat o, en un
        mini chat, la de ese agente (None si aún no tiene)."""
        brief = self.briefing()
        return self.chats.get(brief[1]) if brief else self.chat

    def brief(self):
        """Toma el teclado para escribirle al del desglose abierto. La isla
        se queda abierta mientras se escribe."""
        found = self.briefing()
        if found is None:
            return
        self.chat_claim(found[1])
        self.expand()
        self.chat_type(True)

    def brief_drop(self):
        """Suelta el teclado del mini chat; la isla vuelve a cerrarse sola."""
        self.chat_type(False)
        self.expand(CHAT_WATCH_SECS)

    def brief_away(self, s, agent):
        """El proyecto en el que ese agente tiene un turno en curso, si no es
        el de `s`: hasta que acabe, aquí no se le puede encargar nada."""
        c = self.chats.get(agent)
        if c is not None and c.busy and state.project_root(c.cwd) != state.project_root(s.cwd):
            return c.project
        return ''

    def brief_send(self, s, agent, text):
        """Enter en el mini chat: se le encarga a ese agente, en la carpeta de
        la pestaña, y la isla vuelve al tablero para verlos trabajar a todos."""
        if self.brief_away(s, agent):
            return
        c = self.chat_for(agent, s.cwd)
        if not c.send(text, self.chat_images):
            return
        self.chat_hosts[agent] = s.sid
        self.chat_set_text('')
        self.chat_images = []
        self.focus = None
        self.brief_drop()

    def crew(self, s):
        """Los de la familia a los que se les encargó algo desde la pestaña
        de `s`: {personaje: su conversación}."""
        return {state.AGENT_ROLES[agent]: self.chats[agent] for agent, sid in self.chat_hosts.items()
                if sid == s.sid and agent in self.chats}

    def host(self, s):
        """La sesión en cuya pestaña se ve `s`: ella misma, salvo la de un
        encargo, que va en la pestaña desde la que se hizo mientras siga ahí."""
        for agent, sid in self.chat_hosts.items():
            c, other = self.chats.get(agent), self.model.sessions.get(sid)
            if c is None or c.session != s.sid or other is None or other is s:
                continue
            if other.state != 'alert':
                return other
        return s

    # ── lo que llega de Claude ──────────────────────────────────────────────

    def on_chat(self, event, c=None):
        c = c or self.chat
        if c is None:
            return GLib.SOURCE_REMOVE
        asked, cut = c.asking, c.cut
        if not c.feed(event):
            return GLib.SOURCE_REMOVE
        if c.session:
            self.chat_sessions.add(c.session)
            if self.chat_watch:
                self.tab = c.session
        if c.asking and not asked:
            self.chat_ask(c)
        if event.get('type') == 'result' and not cut:
            self.chat_watch = False
            if not (self.chat_open and c is self.chat) and c.reply():
                self.chat_notice(c)
        self.refresh()
        self.ensure_tick()
        return GLib.SOURCE_REMOVE

    def chat_ask(self, c):
        """Un chat pide permiso: va a la tarjeta del tablero, como el de
        cualquier sesión, y la isla se abre en su pestaña para contestarlo."""
        if not c.session:
            return
        self.model.handle({'event': 'ask', 'session_id': c.session, 'cwd': c.cwd,
                           'tool_name': c.asking['tool'], 'tool_input': c.asking['input']}, ChatAsk(c))
        self.tab = c.session
        if not self.chat_open:
            self.expand(None if self.settings['pinned'] else CHAT_WATCH_SECS * 10)

    def chat_release(self):
        """Contestado en el chat: la tarjeta del tablero ya no espera."""
        s = self.model.sessions.get(self.chat.session) if self.chat else None
        if s is not None and isinstance(s.ask, ChatAsk):
            s.ask.done = True
            s.ask = None
            s.set('working', s.last_tool or 'Trabajando…')

    def chat_notice(self, c):
        """Terminó con su chat cerrado: un aviso con el principio de la
        respuesta y el botón que abre ese chat para leerla entera."""
        lines = plain(c.reply())
        self.model.handle({'event': 'alert', 'session_id': f'chat:{c.session}', 'name': c.project,
                           'message': f'{c.name} terminó · ver respuesta', 'tone': 'ok',
                           'ttl': CHAT_REPLY_SECS, 'where': c.name, 'note': chat.model_name(c.model_id),
                           'lines': lines[:CHAT_REPLY_LINES],
                           'actions': [{'label': 'Ver respuesta', 'chat': c.agent or True, 'after': 'clear'}]})

    # ── modelo, esfuerzo y plan ─────────────────────────────────────────────

    def chat_choose(self, key):
        """Una opción de un menú de la línea de estado: 'model:opus', 'effort:high'."""
        what, _, value = key.partition(':')
        if self.chat is None:
            return
        if what == 'model':
            self.chat.set_model(value)
            self.settings['chat_model'] = value
        elif what == 'effort':
            self.chat.set_effort(value)
            self.settings['chat_effort'] = value
        settings.save(self.settings)
        self.chat_menu = None

    def chat_model_text(self):
        """El modelo que se ve en la línea de estado: el que dice Claude o,
        si se acaba de elegir otro, ese."""
        c = self.chat
        names = dict(chat.MODELS)
        if c is not None and c.model and c.model not in c.model_id:
            return names.get(c.model, c.model)
        if c is not None and c.model_id:
            return chat.model_name(c.model_id)
        return names.get(self.settings.get('chat_model', ''), 'modelo por defecto')

    def chat_effort_text(self):
        c = self.chat
        level = (c.effort if c is not None else '') or chat.default_effort(c.model_id if c else '')
        text = f'esfuerzo {chat.EFFORT_TEXT.get(level, level)}' if level else 'esfuerzo por defecto'
        return text + (' · siguiente turno' if c is not None and c.restart else '')

    # ── la caja de texto ────────────────────────────────────────────────────

    def suggestions(self):
        """Los comandos que empiezan por lo que llevas escrito tras "/":
        [(nombre, descripción)]. [] si no estás escribiendo un comando."""
        if self.chat is None or self.chat_quiet or not self.chat_open:
            return []
        text = self.chat_text()
        if not text.startswith('/') or ' ' in text or '\n' in text:
            return []
        word = text[1:].lower()
        return sorted(((name, desc) for name, desc in self.chat.commands.items()
                       if name.lower().startswith(word)), key=lambda it: (len(it[0]), it[0]))

    def complete(self, name):
        self.chat_set_text(f'/{name} ')

    def on_chat_enter(self):
        found = self.suggestions()
        text = self.chat_text()
        if found:
            name = found[min(self.chat_pick, len(found) - 1)][0]
            if text.strip() != f'/{name}':
                # Enter sobre la lista elige el comando; otro Enter lo manda.
                self.complete(name)
                return
        brief = self.briefing()
        if brief is not None:
            self.brief_send(*brief, text)
        elif self.chat is not None and self.chat.send(text, self.chat_images):
            self.chat_set_text('')
            self.chat_images = []
            self.chat_scroll = 0.0
            self.chat_watch = True
            # A ver trabajar en el tablero: el chat se cierra y la isla se
            # abre en la pestaña de la conversación.
            self.close_chat()
            if self.chat.session:
                self.tab = self.chat.session
            self.expand(None if self.settings['pinned'] else CHAT_WATCH_SECS)
        self.ensure_tick()

    def on_chat_changed(self, _buffer):
        self.chat_pick, self.chat_quiet = 0, False
        self.ensure_tick()

    def on_chat_key(self, _ctrl, keyval, _code, mods):
        self.chat_keyed = time.monotonic()
        found = self.suggestions()
        shift, ctrl = mods & Gdk.ModifierType.SHIFT_MASK, mods & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_Escape:
            if self.chat_menu:
                self.chat_menu = None
            elif found:
                self.chat_quiet = True
            elif self.chat_open:
                self.chat_type(False)
            else:
                self.brief_drop()
            self.ensure_tick()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not shift:
            self.on_chat_enter()
            return True
        if found and keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            step = -1 if keyval == Gdk.KEY_Up else 1
            self.chat_pick = (self.chat_pick + step) % len(found)
            self.ensure_tick()
            return True
        if found and keyval == Gdk.KEY_Tab:
            self.complete(found[min(self.chat_pick, len(found) - 1)][0])
            return True
        c = self.chat_now()
        if keyval == Gdk.KEY_ISO_Left_Tab and c is not None:
            c.toggle_plan()
            self.ensure_tick()
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C) and ctrl and c is not None:
            if not self.entry.get_buffer().get_has_selection():
                c.interrupt()
                self.ensure_tick()
                return True
        if keyval in (Gdk.KEY_v, Gdk.KEY_V) and ctrl:
            return self.chat_paste()
        return False

    def chat_paste(self):
        """Ctrl+V: si en el portapapeles hay una imagen, se adjunta. True si
        la toma; si no, el texto se pega como siempre."""
        clipboard = self.entry.get_clipboard()
        mimes = clipboard.get_formats().get_mime_types() or []
        if not any(m.startswith('image/') for m in mimes) or len(self.chat_images) >= CHAT_MAX_IMAGES:
            return False
        clipboard.read_texture_async(None, self.on_chat_pasted)
        return True

    def on_chat_pasted(self, clipboard, result):
        try:
            texture = clipboard.read_texture_finish(result)
        except GLib.Error:
            return
        if texture is not None:
            self.chat_images.append(texture.save_to_png_bytes().get_data())
            self.ensure_tick()

    def on_chat_scroll(self, _ctrl, _dx, dy):
        if not (self.chat_open and self.target() == 'chat'):
            return False
        self.chat_scroll = max(0.0, self.chat_scroll - dy * CHAT_SCROLL)
        self.ensure_tick()
        return True

    def on_chat_hit(self, key):
        """Un clic en el chat: sus enlaces, la línea de estado y sus menús, un
        comando de la lista, una imagen pegada o la caja."""
        menu, self.chat_menu = self.chat_menu, None
        if key == 'stop' and self.chat is not None:
            self.chat.interrupt()
        elif key == 'new':
            self.new_chat()
        elif key == 'close':
            self.close_chat()
        elif key in ('agent', 'model', 'effort'):
            self.chat_menu = None if menu == key else key
        elif key == 'plan' and self.chat is not None:
            self.chat.toggle_plan()
        elif key.startswith(('model:', 'effort:')):
            self.chat_choose(key)
        elif key.startswith('img:'):
            index = int(key[4:])
            if index < len(self.chat_images):
                del self.chat_images[index]
        elif key.startswith('/'):
            self.complete(key[1:])
            self.chat_type(True)
        elif key == 'type':
            self.chat_type(True)
        elif key.startswith('agent:'):
            self.open_chat(typing=self.chat_typing, agent=key[6:])
        self.ensure_tick()

    def on_chat_button(self, key):
        """Permitir o Denegar en la tarjeta del permiso."""
        if self.chat is not None and self.chat.asking:
            self.chat.answer(key == 'chat-allow')
            self.chat_release()
            self.refresh()
            self.ensure_tick()

    # ── dibujo ──────────────────────────────────────────────────────────────

    def chat_role(self):
        return state.AGENT_ROLES.get(self.chat.agent, state.MAIN_ROLE) if self.chat else state.MAIN_ROLE

    def chat_color(self):
        """El color del agente con el que se habla."""
        return mascot.rgba(mascot.accent(self.chat_role()))[:3]

    def chat_pet(self):
        c = self.chat
        if c is None:
            return 'idle'
        return 'permission' if c.asking else 'working' if c.busy else 'idle'

    def chat_status(self):
        """Cómo va el turno, como (texto, papel de su color)."""
        c = self.chat
        if c is None or (c.proc is None and not c.entries):
            return 'Listo para empezar', 'text'
        if c.asking:
            return 'Pide permiso', 'bad'
        if c.busy:
            return ('Escribiendo…' if c.streaming else 'Pensando…'), 'cmd'
        return 'Listo', 'pass'

    def chat_input_h(self, cr, width, most=CHAT_INPUT_LINES, text=None):
        """Alto de la caja: lo que ocupa lo escrito, entre una línea y `most`."""
        one = self._layout(cr, 'X', FONT_INPUT).get_pixel_size()[1]
        text = self.chat_text() if text is None else text
        if text:
            layout = self._layout(cr, text, FONT_INPUT, width)
            layout.set_ellipsize(Pango.EllipsizeMode.NONE)
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
            layout.set_height(-1)
            lines = max(1, min(most, round(layout.get_pixel_size()[1] / one)))
        else:
            lines = 1
        return lines * one + 2 * CHAT_INPUT_PAD

    def draw_chat(self, cr, x0, w, h, alpha, now):
        """El panel entero, de abajo arriba: la línea de estado, la caja, lo
        pegado, el permiso y la conversación. Deja anotado dónde va el texto
        de la caja (`chat_box`) para que el Gtk.TextView se ponga ahí."""
        pad = CHAT_PAD
        left, width = x0 + pad, w - 2 * pad
        self.draw_chat_head(cr, left, width, alpha, now)
        status_y = h - pad - CHAT_STATUS_H + 4
        text_w = width - CHAT_INPUT_INSET - 12
        ih = self.chat_input_h(cr, text_w)
        box_y = status_y - 6 - ih
        bottom = box_y
        if self.chat_images:
            bottom -= CHAT_CHIP_H + 6
            self.draw_chat_images(cr, left, bottom, width, alpha)
        c = self.chat
        if c is not None and c.asking:
            bottom -= CHAT_ASK_H + 8
            self.draw_chat_ask(cr, left, bottom + 4, width, alpha)
        top = CHAT_HEAD + 6
        self.draw_chat_log(cr, left, top, width, bottom - 8, alpha)
        self.draw_chat_input(cr, left, box_y, width, ih, alpha)
        self.chat_box = (int(left + CHAT_INPUT_INSET), int(box_y + CHAT_INPUT_PAD), int(text_w),
                         int(ih - 2 * CHAT_INPUT_PAD))
        anchors = self.draw_chat_status(cr, left, status_y, width, alpha)
        found = self.suggestions()
        if found:
            self.draw_chat_suggest(cr, left, width, box_y - 6, found, alpha)
        elif self.chat_menu in anchors:
            self.draw_chat_menu(cr, anchors[self.chat_menu], status_y - 4, alpha)

    def draw_chat_input(self, cr, left, y, width, ih, alpha):
        """La caja: su fondo, su barra del color del agente y, vacía, qué escribir."""
        color = self.chat_color()
        mascot.rrect(cr, left, y, width, ih, 10)
        cr.set_source_rgba(1, 1, 1, (.09 if self.chat_typing else .05) * alpha)
        cr.fill()
        cr.rectangle(left, y + 6, CHAT_BAR, ih - 12)
        cr.set_source_rgba(*color, (1 if self.chat_typing else .5) * alpha)
        cr.fill()
        self.hits.append(('chat', 'type', left, y, width, ih))
        if not self.chat_text():
            name = self.chat.name if self.chat is not None else state.MAIN_AGENT
            hint = (PLACEHOLDER.format(agent=name) if self.chat_typing
                    else 'Clic aquí, o elyares-ctl chat, para escribir')
            self.put(cr, hint, FONT_LINK, left + CHAT_INPUT_INSET, y + CHAT_INPUT_PAD, (1, 1, 1), .38 * alpha,
                     width=width - CHAT_INPUT_INSET - 12)

    def draw_chat_status(self, cr, left, y, width, alpha):
        """La línea de debajo de la caja: con quién hablas, el modelo, el
        esfuerzo y el modo plan. Devuelve dónde quedó cada uno, para su menú."""
        name = self.chat.name if self.chat is not None else state.MAIN_AGENT
        plan = self.chat is not None and self.chat.plan
        soft = mascot.rgba(self.ink('text', .66))[:3]
        parts = [('agent', name, self.chat_color()), ('model', self.chat_model_text(), mascot.rgba(self.ink('arg'))[:3]),
                 ('effort', self.chat_effort_text(), soft),
                 ('plan', 'plan' if plan else 'sin plan', mascot.rgba(self.ink('flag'))[:3] if plan else soft)]
        anchors, x = {}, left + 2
        for i, (key, text, color) in enumerate(parts):
            if i:
                x += self.put(cr, '·', FONT_STEP, x + 6, y, soft, alpha) + 12
            layout = self._layout(cr, text, FONT_STEP)
            tw, th = layout.get_pixel_size()
            if key == 'plan' and plan:
                mascot.rrect(cr, x - 6, y - 2, tw + 12, th + 4, (th + 4) / 2)
                cr.set_source_rgba(*color, .18 * alpha)
                cr.fill()
            over = key is not None and self.over(x - 4, y - 3, tw + 8, th + 6)
            self.tip_text(cr, layout, x, y, (1, 1, 1) if over else color, alpha, False)
            if key is not None:
                self.hits.append(('chat', key, x - 4, y - 3, tw + 8, th + 6))
                anchors[key] = x
            x += tw
        # El recordatorio de las teclas, solo si cabe sin pisar lo de la izquierda.
        for hint in ('Shift+Tab plan · Esc suelta el teclado', 'Shift+Tab plan'):
            if x + 24 + self._layout(cr, hint, FONT_STEP).get_pixel_size()[0] <= left + width:
                self.put(cr, hint, FONT_STEP, left + width, y, soft, .7 * alpha, align=1.0)
                break
        return anchors

    def draw_chat_menu(self, cr, x, bottom, alpha):
        """El menú de con quién hablas, de modelos o de esfuerzo, encima de la
        línea de estado. En el de los agentes va la cara de cada uno, despierta
        si tiene un turno en curso."""
        c = self.chat
        faces = {}
        if self.chat_menu == 'agent':
            items = []
            for role in state.TEAM:
                agent = '' if role == state.MAIN_ROLE else state.ROLE_AGENTS[role]
                other = self.chats.get(agent)
                key = f'agent:{agent}'
                faces[key] = (role, 'working' if other is not None and other.busy else 'idle')
                items.append((key, state.ROLE_AGENTS[role], role == self.chat_role()))
        elif self.chat_menu == 'model':
            current = c.model or next((alias for alias, _ in chat.MODELS if alias in c.model_id), '')
            items = [(f'model:{alias}', name, alias == current) for alias, name in chat.MODELS]
        else:
            current = c.effort or chat.default_effort(c.model_id)
            items = [(f'effort:{level}', chat.EFFORT_TEXT[level], level == current) for level in chat.EFFORTS]
        width = 200 if faces else 170
        hh = len(items) * CHAT_SUGGEST_H + 8
        y = bottom - hh
        mascot.rrect(cr, x - 8, y, width, hh, 10)
        cr.set_source_rgba(.07, .08, .10, .97 * alpha)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, .12 * alpha)
        cr.set_line_width(1)
        cr.stroke()
        for i, (key, text, chosen) in enumerate(items):
            ry = y + 4 + i * CHAT_SUGGEST_H
            if self.over(x - 4, ry, width - 8, CHAT_SUGGEST_H):
                mascot.rrect(cr, x - 4, ry, width - 8, CHAT_SUGGEST_H, 7)
                cr.set_source_rgba(1, 1, 1, .08 * alpha)
                cr.fill()
            color = self.chat_color() if chosen else mascot.rgba(self.ink('arg'))[:3]
            tx = x + 4
            if key in faces:
                role, pet = faces[key]
                self.face(cr, role, pet, x + 6 + CHAT_PICK_FACE / 2, ry + CHAT_SUGGEST_H / 2, CHAT_PICK_FACE, alpha)
                tx += CHAT_PICK_FACE + 10
                color = mascot.rgba(mascot.accent(role))[:3] if chosen else color
            self.put(cr, ('✓ ' if chosen else '   ') + text, FONT_STEP, tx, ry + 5, color, alpha)
            self.hits.append(('chat', key, x - 4, ry, width - 8, CHAT_SUGGEST_H))

    def draw_chat_images(self, cr, left, y, width, alpha):
        """Las imágenes pegadas, en etiquetas con su ×, encima de la caja."""
        color = self.chat_color()
        x = left
        for i, _png in enumerate(self.chat_images):
            text = f'imagen {i + 1}  ×'
            layout = self._layout(cr, text, FONT_LINK)
            tw, th = layout.get_pixel_size()
            cw = tw + 20
            mascot.rrect(cr, x, y, cw, CHAT_CHIP_H, CHAT_CHIP_H / 2)
            cr.set_source_rgba(*color, .18 * alpha)
            cr.fill_preserve()
            cr.set_source_rgba(*color, .4 * alpha)
            cr.set_line_width(1)
            cr.stroke()
            self.tip_text(cr, layout, x + 10, y + (CHAT_CHIP_H - th) / 2, color, alpha, False)
            self.hits.append(('chat', f'img:{i}', x, y, cw, CHAT_CHIP_H))
            x += cw + 6

    def chat_place(self, h):
        """Pone la caja de texto de verdad sobre la dibujada (la del chat o la
        del mini chat de un desglose), y solo con la isla ya abierta."""
        brief = self.briefing()
        if self.chat_typing and not self.chat_open and brief is None:
            self.chat_type(False)         # el desglose se cerró: el teclado no se queda tomado
        box = self.entry_box
        if box is None:
            return
        if self.target() == 'chat':
            show = h > CHAT_H - CHAT_SHOW_AT
        else:
            show = brief is not None and brief[1] == self.chat_whom and h > self.goal()[1] - CHAT_SHOW_AT
        show = show and self.chat_box is not None and (self.chat_typing or bool(self.chat_text()))
        if show:
            x, y, w, hh = self.chat_box
            if (box.get_margin_start(), box.get_margin_top()) != (x, y):
                box.set_margin_start(x)
                box.set_margin_top(y)
            box.set_size_request(w, hh)
        if box.get_visible() != show:
            box.set_visible(show)
            if show and self.chat_typing:
                self.entry.grab_focus()

    def draw_brief(self, cr, s, agent, role, left, bottom, width, alpha):
        """El mini chat de un desglose, de `bottom` hacia arriba: la línea de
        estado y la caja para encargarle algo a ese agente. Devuelve dónde
        empieza la caja, para que los pasos no pasen de ahí."""
        color = mascot.rgba(mascot.accent(role))[:3]
        mine = self.chat_whom == agent      # lo escrito en la caja es para él
        typing = mine and self.chat_typing
        text = self.chat_text() if mine else ''
        text_w = width - CHAT_INPUT_INSET - 12
        ih = self.chat_input_h(cr, text_w, MINI_LINES, text)
        status_y = bottom - CHAT_STATUS_H + 4
        y = status_y - 6 - ih
        mascot.rrect(cr, left, y, width, ih, 10)
        cr.set_source_rgba(1, 1, 1, (.09 if typing else .05) * alpha)
        cr.fill()
        cr.rectangle(left, y + 6, CHAT_BAR, ih - 12)
        cr.set_source_rgba(*color, (1 if typing else .5) * alpha)
        cr.fill()
        self.hits.append(('brief', None, left, y, width, ih))
        if mine:
            self.chat_box = (int(left + CHAT_INPUT_INSET), int(y + CHAT_INPUT_PAD), int(text_w),
                             int(ih - 2 * CHAT_INPUT_PAD))
        if not text:
            hint = f'Dile a {agent} qué hacer' if typing else f'Clic aquí para encargarle algo a {agent}'
            self.put(cr, hint, FONT_LINK, left + CHAT_INPUT_INSET, y + CHAT_INPUT_PAD, (1, 1, 1), .38 * alpha,
                     width=text_w)
        soft = mascot.rgba(self.ink('text', .66))[:3]
        away, c = self.brief_away(s, agent), self.chats.get(agent)
        images = len(self.chat_images) if mine else 0
        if away:
            note, tone = f'ocupado en {away}: aquí, cuando acabe', mascot.rgba(self.ink('bad'))[:3]
        elif c is not None and c.busy:
            note, tone = 'trabajando · lo que mandes va después', color
        elif images:
            note, tone = ('1 imagen' if images == 1 else f'{images} imágenes'), color
        else:
            note, tone = '', soft
        keys = 'Enter manda · Esc suelta' if typing else ''
        kw = self.put(cr, keys, FONT_STEP, left + width, status_y, soft, .7 * alpha, align=1.0) if keys else 0
        if note:
            self.put(cr, note, FONT_STEP, left + 2, status_y, tone, alpha, width=width - kw - 14)
        return y

    def draw_chat_head(self, cr, left, width, alpha, now):
        mid = CHAT_HEAD / 2 + 4
        role = self.chat_role()
        self.face(cr, role, self.chat_pet(), left + CHAT_FACE / 2, mid, CHAT_FACE, alpha,
                  now, now - getattr(self, 'pet_since', now))
        # Los enlaces, a la derecha: lo demás cabe en lo que queda.
        links = [('close', 'Cerrar'), ('new', 'Nuevo')]
        if self.chat is not None and self.chat.busy:
            links.append(('stop', 'Detener'))
        pick_x = left + width - self.chat_links_w(cr, links) - 18
        project = self.chat.project if self.chat is not None else state.project_name(chat.active_cwd())
        name = self.chat.name if self.chat is not None else state.MAIN_AGENT
        text, markup = self.who(name, project, mascot.accent(role))
        tx = left + CHAT_FACE + 10
        room = pick_x - tx - 12
        self.put(cr, text, 'Sans Semi-Bold 11', tx, mid - 17, TITLE, alpha, width=room, markup=markup)
        status, color_role = self.chat_status()
        where = state.tilde(self.chat.cwd) if self.chat is not None else ''
        sw = self.put(cr, status, FONT_LINK, tx, mid + 2, mascot.rgba(self.ink(color_role))[:3], alpha)
        if where and room - sw - 6 > 40:
            self.put(cr, f'· {where}', FONT_STEP, tx + sw + 6, mid + 3, mascot.rgba(self.ink('text', .62))[:3],
                     alpha, width=room - sw - 6)
        x = left + width
        for key, label in links:
            layout = self._layout(cr, label, FONT_LINK)
            lw, lh = layout.get_pixel_size()
            x -= lw
            over = self.over(x - 4, mid - lh / 2 - 3, lw + 8, lh + 6)
            color = (mascot.rgba(self.ink('bad'))[:3] if key == 'stop'
                     else (1, 1, 1) if over else mascot.rgba(self.ink('text', .7))[:3])
            self.tip_text(cr, layout, x, mid - lh / 2, color, alpha, False)
            self.hits.append(('chat', key, x - 4, mid - lh / 2 - 3, lw + 8, lh + 6))
            x -= CHAT_LINK_GAP
        cr.set_source_rgba(1, 1, 1, .07 * alpha)
        cr.rectangle(left, CHAT_HEAD + 2, width, 1)
        cr.fill()

    def chat_links_w(self, cr, links):
        return sum(self._layout(cr, label, FONT_LINK).get_pixel_size()[0] + CHAT_LINK_GAP for _, label in links)

    def chat_layout(self, cr, index, entry, width):
        """Lo que mide y dibuja una cosa de la conversación, guardado mientras
        no cambie: (layout, alto que ocupa, papel)."""
        key = (index, entry.kind, entry.text, entry.images, width)
        hit = self.chat_cache.get(key)
        if hit is not None:
            PangoCairo.update_layout(cr, hit[0])
            return hit
        inner = width - CHAT_INDENT
        if entry.kind == 'claude':
            markup = paint.markdown(entry.text, self.ink('cmd'), self.ink('head'))
            if not Pango.parse_markup(markup, -1, '\0')[0]:
                markup = html.escape(entry.text, quote=False)     # un markdown que no se pudo leer
            layout = self.chat_wrap(cr, entry.text, FONT_CHAT, inner, markup)
            hit = (layout, layout.get_pixel_size()[1], 'arg')
        elif entry.kind == 'you':
            text = entry.text
            if entry.images:
                text += ('\n' if text else '') + ('1 imagen' if entry.images == 1 else f'{entry.images} imágenes')
            layout = self.chat_wrap(cr, text, FONT_YOU, inner - CHAT_BLOCK_PAD)
            hit = (layout, layout.get_pixel_size()[1] + 2 * CHAT_BLOCK_PAD, 'arg')
        elif entry.kind == 'foot':
            color = mascot.accent(self.chat_role())
            markup = (f'<span foreground="{color}">▣</span>  '
                      f'<span foreground="{self.ink("text", .6)}">{html.escape(entry.text, quote=False)}</span>')
            layout = self._layout(cr, '▣  ' + entry.text, FONT_STEP, inner, 1, markup=markup)
            hit = (layout, layout.get_pixel_size()[1] + 4, None)
        else:
            text = {'tool': f'· {entry.text}'}.get(entry.kind, entry.text)
            font = FONT_STEP if entry.kind == 'tool' else FONT_LINK
            layout = self._layout(cr, text, font, inner, 2)
            role = {'tool': 'text', 'note': 'text', 'error': 'bad'}[entry.kind]
            hit = (layout, layout.get_pixel_size()[1], role)
        if len(self.chat_cache) > 600:
            self.chat_cache.clear()
        self.chat_cache[key] = hit
        return hit

    def chat_wrap(self, cr, text, font, width, markup=None):
        """Un texto partido en todas las líneas que haga falta, sin cortarse."""
        layout = self._layout(cr, text, font, width, 1, markup=markup)
        layout.set_ellipsize(Pango.EllipsizeMode.NONE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_height(-1)
        return layout

    def draw_chat_log(self, cr, left, top, width, bottom, alpha):
        """La conversación, pegada abajo como en cualquier chat. Se sube con la rueda."""
        c = self.chat
        if c is None or not c.entries:
            self.draw_chat_empty(cr, left, top, width, bottom, alpha)
            return
        items = [self.chat_layout(cr, i, e, width) for i, e in enumerate(c.entries)]
        total = sum(it[1] for it in items) + CHAT_GAP * (len(items) - 1)
        room = bottom - top
        self.chat_scroll = min(self.chat_scroll, max(0.0, total - room))
        cr.save()
        cr.rectangle(left - 4, top, width + 8, room)
        cr.clip()
        y = bottom + self.chat_scroll
        color = self.chat_color()
        for (layout, hh, role), entry in zip(reversed(items), reversed(c.entries)):
            y -= hh
            if y > bottom:
                y -= CHAT_GAP
                continue
            if y + hh < top:
                break
            x = left + CHAT_INDENT
            if entry.kind == 'you':
                # Tu bloque: a todo lo ancho, teñido, con la barra del color del agente.
                cr.rectangle(left, y, width, hh)
                cr.set_source_rgba(1, 1, 1, .055 * alpha)
                cr.fill()
                cr.rectangle(left, y, CHAT_BAR, hh)
                cr.set_source_rgba(*color, alpha)
                cr.fill()
                self.tip_text(cr, layout, x, y + CHAT_BLOCK_PAD, mascot.rgba(self.ink('arg'))[:3], alpha, False)
            elif role is None:
                self.tip_text(cr, layout, x, y + 2, None, alpha, False)
            else:
                light = .62 if entry.kind in ('tool', 'note') else None
                tone = mascot.rgba(self.ink(role, light) if light else self.ink(role))[:3]
                if entry.kind == 'note':
                    x = left + (width - layout.get_pixel_size()[0]) / 2
                self.tip_text(cr, layout, x, y, tone, alpha, False)
            y -= CHAT_GAP
        cr.restore()
        if self.chat_scroll > 0:
            self.put(cr, '↓ más abajo', FONT_STEP, left + width, bottom - 14, (1, 1, 1), .45 * alpha, align=1.0)

    def draw_chat_empty(self, cr, left, top, width, bottom, alpha):
        """Antes de escribir nada: qué es esto y qué se le puede pedir."""
        where = state.tilde(self.chat.cwd) if self.chat is not None else '~'
        name = self.chat.name if self.chat is not None else state.MAIN_AGENT
        lines = [(f'Pídele algo a {name}', 'Sans Semi-Bold 12', 'arg'),
                 (f'Trabaja en {where}', FONT_HINT, 'path'),
                 ('Escribe / para tus comandos: /contexto, /bitacora, /commit…', FONT_HINT, 'text')]
        y = top + (bottom - top) / 2 - 36
        for text, font, role in lines:
            layout = self._layout(cr, text, font, width)
            lw, lh = layout.get_pixel_size()
            self.tip_text(cr, layout, left + (width - lw) / 2, y, mascot.rgba(self.ink(role))[:3], alpha, False)
            y += lh + 8

    def draw_chat_ask(self, cr, left, y, width, alpha):
        """La tarjeta del permiso, encima de la caja."""
        ask = self.chat.asking
        red = mascot.rgba(self.ink('bad'))[:3]
        mascot.rrect(cr, left, y, width, CHAT_ASK_H, 12)
        cr.set_source_rgba(*red, .12 * alpha)
        cr.fill_preserve()
        cr.set_source_rgba(*red, .45 * alpha)
        cr.set_line_width(1)
        cr.stroke()
        self.put(cr, 'Pide permiso', FONT_LINK, left + 12, y + 10, red, alpha)
        self.put(cr, ask['text'], FONT_YOU, left + 12, y + 28, mascot.rgba(self.ink('arg'))[:3], alpha,
                 width=width - 24)
        by = y + CHAT_ASK_H - 8 - 26
        right = left + width - 12
        self.draw_button(cr, 'chat-allow', 'Permitir', right - 84, by, True, alpha)
        self.draw_button(cr, 'chat-deny', 'Denegar', right - 2 * 84 - 8, by, False, alpha)

    def draw_chat_suggest(self, cr, left, width, bottom, found, alpha):
        """La lista de comandos al escribir "/", justo encima de la caja."""
        pick = min(self.chat_pick, len(found) - 1)
        first = max(0, min(pick - CHAT_SUGGEST + 1, len(found) - CHAT_SUGGEST))
        shown = found[first:first + CHAT_SUGGEST]
        hh = len(shown) * CHAT_SUGGEST_H + 8
        y = bottom - hh
        mascot.rrect(cr, left, y, width, hh, 12)
        cr.set_source_rgba(.07, .08, .10, .97 * alpha)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, .12 * alpha)
        cr.set_line_width(1)
        cr.stroke()
        cmd, soft = mascot.rgba(self.ink('cmd'))[:3], mascot.rgba(self.ink('text', .66))[:3]
        for i, (name, desc) in enumerate(shown):
            ry = y + 4 + i * CHAT_SUGGEST_H
            if first + i == pick:
                mascot.rrect(cr, left + 4, ry, width - 8, CHAT_SUGGEST_H, 8)
                cr.set_source_rgba(1, 1, 1, .09 * alpha)
                cr.fill()
            layout = self._layout(cr, f'/{name}', FONT_YOU)
            nw, nh = layout.get_pixel_size()
            self.tip_text(cr, layout, left + 12, ry + (CHAT_SUGGEST_H - nh) / 2, cmd, alpha, False)
            if desc:
                self.put(cr, desc, FONT_STEP, left + 24 + max(nw, 110), ry + (CHAT_SUGGEST_H - nh) / 2 + 1,
                         soft, alpha, width=width - 44 - max(nw, 110))
            self.hits.append(('chat', f'/{name}', left, ry, width, CHAT_SUGGEST_H))
