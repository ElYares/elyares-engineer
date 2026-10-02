"""La isla: una capa layer-shell arriba del monitor enfocado, con ElYares dentro.

La ventana mide siempre WIN_W x WIN_H y es transparente. Lo que crece y se
encoge es la isla negra que se dibuja dentro, y la región de entrada la sigue:
fuera de la isla, los clics pasan a las ventanas de abajo.

En modo compacto (clic derecho en la isla lo prende y lo apaga) la isla se
queda en una pastilla con la mascota en miniatura, y solo se abre con un clic
o cuando hay que contestar un permiso.

`elyares-ctl` manda órdenes por el mismo socket (para atajos de Hyprland):
abrir la isla, esconderla del todo o cambiar de modo. Con `theme` vuelve a leer
el color de acento del tema de omarchy y con `glass` prende o apaga el modo
vidrio (fondo translúcido; el desenfoque lo pone una regla de Hyprland). Con
`allow` y `deny` contesta desde el teclado el permiso que la isla tiene a la
vista. Con `pin` (o con el clic central) la isla se queda fijada: abierta con
todo a la vista (el detalle entero, la lista, las fuentes) aunque el ratón se
vaya, hasta que se desfija.

Además de las sesiones de Claude muestra alertas: de DevHerd Observe
(`devherd.py`), de GitHub (`github.py`), del pomodoro (`coffe.py`), de un
comando largo que terminó y del uso de Claude. Se ven como una sesión más y el
clic abre su URL o salta a su pane.

Una alerta puede traer una ficha: unas líneas de detalle y botones propios
(las de devherd traen Logs, Timeline, Levantar…; las de GitHub, Reintentar y
Abrir PR; las de la terminal y del uso, Ir al pane), además de Descartar. Sale
debajo de la cabecera con el ratón encima o abierta a mano. Si la alerta está
en la lista, un clic en su fila la sube a la cabecera para leerla.

Abierta a mano lleva al pie una pastilla por fuente (`sources.py`): dice si
está conectada y un clic la prende o la apaga. Con el cursor sobre una
pastilla sale debajo de la isla una burbuja con lo que se sabe de esa fuente
y, para consultar, sus comandos (`commands.py`). Al final de la franja, la
pastilla "?" trae los del propio elyares-engineer: atajos de teclado, clics y órdenes.

Mientras corren unas pruebas en una terminal la isla se queda abierta con su
ficha a la vista: la lista de las que van pasando (✓) y fallando (✗), que
`testrun.Follower` va leyendo de lo que imprime el pane. Al terminar, y cuando
las corre Claude, la ficha con el resultado se ve el rato que la isla está
abierta por la noticia.

Si la sesión principal está editando un archivo, abierta a mano (o al pedir
permiso para editarlo) la isla se ensancha y muestra el fragmento que cambia,
como un diff de pocas líneas (`preview.py`). Es solo para mirar.

Abierta a mano (o con el ratón encima) y con alguna sesión de Claude, la isla
es un tablero: una pestaña por sesión y, de la elegida, sus cuatro agentes
(`state.Session.team`). Los que trabajan van al frente, en grande, con su gesto
y sus últimos pasos; los libres, en chiquito en la banca. El frente se parte
según cuántos trabajen, y con los cuatro son cuatro cuadros. Un clic en uno
abre su desglose: todos sus pasos y lo que tardó cada uno. Un clic en la
pestaña elegida lleva al pane de tmux de esa sesión. La pestaña se va sola a
la sesión que pide permiso o acaba de terminar y, cuando la elegida se queda
en reposo, a la que sigue trabajando. Debajo del tablero van las alertas, una
fila cada una.

Sin abrirla, la isla sigue como siempre: asomada, con la mascota (que es el
personaje del que trabaja: `mascot.py` dibuja a los cuatro) y, a su lado, las
caritas de los demás que trabajan; y cuando se abre sola por un aviso, con la
cabecera «agente | proyecto» y lo que pasa.
"""

import html
import math
import os
import random
import threading
import time

import cairo
import gi

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from . import (actions, coffe, commands, devherd, github, hypr, ipc, mascot, paint,  # noqa: E402
               preview, settings, sources, store, testrun, theme)
from .state import MAIN_ROLE, Model, elapsed  # noqa: E402

MAX_ROWS = 5          # filas de la lista de alertas, con la cabecera de siempre
ROW_H, LIST_PAD = 28, 10
OPEN_H = 88
DETAIL_LINES = 4      # líneas del detalle cuando se muestra entero
MAX_EXTRA = 54        # alto de más que puede pedir el detalle entero
PILLS_H = 34          # la franja de pastillas de las fuentes
PILL_H, PILL_GAP = 20, 5
PILL_PAD = 22         # lo que mide una pastilla además de su texto: el punto y los bordes
PREVIEW_W = 600       # con vista previa la isla se ensancha: el código pide ancho
CODE_LINE_H, PREVIEW_HEAD, PREVIEW_PAD = 15, 24, 8
PREVIEW_MAX = PREVIEW_HEAD + (preview.MAX_LINES + 1) * CODE_LINE_H + 2 * PREVIEW_PAD
ASK_TALL = 24         # con vista previa, los botones bajan debajo de ella
PREVIEW_OPEN_SECS = 20    # abierta con el teclado y con código que leer
CARD_BUTTONS = 40     # la fila de botones de la ficha de una alerta
TIP_W, TIP_PAD, TIP_GAP = 400, 11, 6   # la burbuja de una fuente, debajo de la isla
TIP_ROOM = 440        # el alto que se le reserva en la ventana
TIP_COL_GAP = 16      # entre un comando y lo que hace
TIP_HEAD_GAP = 7      # aire sobre el título de un bloque de comandos
TIP_LINES = 3         # líneas propias que puede traer una fuente
TIP_FADE = .12        # segundos que tarda en aparecer
# 8: margen del rebote
# El tablero: una pestaña por sesión y, dentro, sus cuatro.
BOARD_W = PREVIEW_W
TABS_H = 34
BOARD_H = 172         # el frente (los que trabajan) y la banca (los libres)
BOARD_PAD, BOARD_GAP = 10, 8
BENCH_W = 132
FOCUS_H = 236         # el desglose de uno, con sus pasos
FOCUS_STEPS = 8
FOCUS_SIDE, FOCUS_MINIS = 150, 34   # a la izquierda, quién es; a la derecha, los demás
ALERT_ROWS = 3        # filas de alertas que caben debajo del tablero
MINI, MAX_MINIS = 24, 4             # las caritas de los demás, con la isla asomada
WIN_W = PREVIEW_W + 40
# Lo más alto que se puede dibujar, con la cabecera de siempre o con el tablero.
HEAD_MAX = OPEN_H + MAX_EXTRA + PREVIEW_MAX + ASK_TALL + MAX_ROWS * ROW_H + LIST_PAD
BOARD_MAX = (TABS_H + max(BOARD_H + PREVIEW_MAX, FOCUS_H) + BOARD_PAD
             + ALERT_ROWS * ROW_H + LIST_PAD)
WIN_H = max(HEAD_MAX, BOARD_MAX) + PILLS_H + 8 + TIP_ROOM
SIZES = {'off': (120, 0), 'hidden': (120, 6), 'petit': (56, 34), 'peek': (92, 80),
         'open': (560, OPEN_H), 'ask': (560, 108)}
HOVER_STRIP = 10     # alto de la franja que detecta el ratón cuando está escondida
PET = 72             # lado del cuadro de la mascota
PET_SCALE = PET / 260
TEXT_INSET = 12 + PET + 10 + 18   # lo que le quitan al texto la mascota y los márgenes
ISLAND_BG = (5 / 255, 6 / 255, 8 / 255, .97)
GLASS_ALPHA, GLASS_EDGE = .5, .16    # modo vidrio: fondo translúcido y filo claro
TIP_GLASS_ALPHA = .82                # la burbuja, en vidrio: se lee más rato que la isla
TITLE_COLOR = (.95, .96, 1, 1)
MUTED_COLOR = (.44, .49, .63, 1)
# La barra entre el agente y el proyecto, en el mismo gris.
SEP_COLOR = '#%02x%02x%02x' % tuple(round(c * 255) for c in MUTED_COLOR[:3])
FONT_TITLE = 'Sans Semi-Bold 11'
FONT_DETAIL = 'JetBrainsMono Nerd Font 9'
FONT_BUTTON = 'Sans Semi-Bold 10'
FONT_ROW = 'Sans Semi-Bold 10'
FONT_PILL = 'Sans Semi-Bold 8'
FONT_CODE = 'JetBrainsMono Nerd Font 8'
ROW_NAME_W = 130     # ancho de la columna del nombre en la lista de alertas
STATE_COLORS = {'permission': 'red', 'alert': 'red', 'waiting': 'yellow', 'done': 'green',
                'working': 'accent'}
# El punto de una alerta, según su tono.
TONE_COLORS = {'ok': 'green', 'info': 'yellow', 'run': 'accent'}
# Una línea de la ficha que empieza con la marca de una prueba: el color de
# la marca y el del nombre. Verde y rojo son fijos, como los puntos de estado:
# el "verde" de algunos temas es un gris.
MARK_COLORS = {testrun.MARKS[testrun.OK]: ('green', 'text'), testrun.MARKS[testrun.FAIL]: ('red', 'bad'),
               testrun.MARKS[testrun.SKIP]: ('metal', 'dim')}
CONTEXT_SHOW = 1     # % de contexto desde el que se muestra junto a la sesión: siempre que se sepa
BUTTON_H, BUTTON_W, BUTTON_GAP = 26, 84, 8
ALLOW_BG, ALLOW_FG = (.95, .96, 1), (5 / 255, 6 / 255, 8 / 255)
DENY_BG, DENY_FG = (1, 1, 1), (.95, .96, 1)
SPRING_K, SPRING_C = 220.0, 22.0   # rigidez y amortiguación: rebota un poquito
LOOK_EVERY = 1 / 15                # frecuencia con la que se pregunta el cursor
IDLE_FPS = 12                      # asomada y quieta: ~3% de CPU en vez de ~8% a 30
KEY_OPEN_SECS = 6                  # abierta con el teclado: se cierra sola
ASK_GUARD_SECS = .6                # un permiso recién salido no se contesta con el teclado
REAP_SECS = 15                     # cada cuánto se mira si los procesos de Claude siguen ahí
BG_TAG = '2º plano'                # una sesión de segundo plano sin nombre, en su pestaña
# El gesto de uno del tablero según cómo está, y el color que tiñe su tarjeta
# (si no está aquí, el de su personaje).
MEMBER_PET = {'working': 'working', 'permission': 'permission', 'done': 'done',
              'waiting': 'confused'}
MEMBER_TINT = {'permission': 'red', 'done': 'green', 'waiting': 'yellow'}


def ago(secs):
    mins = int(secs // 60)
    if mins < 1:
        return 'hace un momento'
    return f'hace {mins} min' if mins < 60 else f'hace {mins // 60} h'


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def dot_color(s):
    """Color del punto de una fila, o None si está en reposo."""
    if s.state == 'alert':
        return TONE_COLORS.get(s.tone, 'red')
    return STATE_COLORS.get(s.state)


def rgb(color):
    return mascot.rgba(color)[:3]


class Island:
    def __init__(self, app):
        self.model = Model()
        self.model.restore(store.load())
        store.forget_usage()
        self.saved = self.model.dump()
        self.view = self.model.view()
        self.key_since = time.monotonic()   # desde cuándo la cabecera muestra lo que muestra
        self.title, self.detail = '', ''
        self.agent_name, self.role = '', MAIN_ROLE   # de quién es la cabecera
        self.tab = ''                   # la sesión de la pestaña elegida en el tablero
        self.focus = None               # (sesión, personaje) del desglose abierto
        self.hits = []                  # (qué, cuál, x, y, ancho, alto) del tablero, del último dibujo
        self.dnd = False
        self.hover = False
        self.settings = settings.load()
        self.load_theme()
        # Abierta a mano, con un clic o con elyares-ctl. Fijada (preferencia
        # `pinned`) se queda así: no se cierra sola ni cuando el ratón se va.
        self.expanded = self.settings['pinned']
        self.collapse_id = 0
        self.seconds = 0
        self.off = False                # escondida del todo con elyares-ctl hide
        self.w, self.h = SIZES['hidden']
        self.vw = self.vh = 0.0
        self.pet_state, self.pet_since = 'idle', time.monotonic()
        self.override = None            # (estado, desde, hasta)
        self.clicks = []
        self.look = [0.0, 0.0]
        self.look_target = (0.0, 0.0)
        self.last_look = 0.0
        self.next_blink = time.monotonic() + 2
        self.blink_until = 0.0
        self.ticking = False
        self.slow_id = 0
        self.last_frame = None
        self.region = None
        # 'allow'/'deny' del permiso, o 'dismiss' y el índice de cada botón de
        # la ficha de una alerta -> (x, y, w, h), del último dibujo
        self.buttons = {}
        self.card_span = None           # (arriba, abajo) de la ficha, del último dibujo
        self.pin = ''                   # la alerta que se eligió en la lista para leerla
        self.rows = []                  # (sesión, y, alto) de la lista, del último dibujo
        self.list_layout = False        # la cabecera se queda arriba mientras hay lista
        self.wrap = (None, 0)           # (detalle, alto de más que pide entero)
        self.pills = []                 # (fuente, x, y, ancho, alto), del último dibujo
        self.tip = None                 # (fuente, centro, opacidad) de la pastilla bajo el cursor
        self.tip_key, self.tip_since = None, 0.0
        self.tip_ref = []               # los comandos de la burbuja que se está viendo
        # Lo que se sabe de cada fuente: si responde, una nota y lo que dirá
        # su burbuja. Las que dependen de install.sh arrancan con lo que haya
        # instalado.
        self.sources = {}
        for key, ok in sources.installed().items():
            if ok:
                self.on_source({'name': key, 'ok': True})
            else:
                self.on_source({'name': key, 'ok': False, 'note': 'sin instalar',
                                'why': sources.MISSING[key], 'fix': sources.MISSING_FIX})
        self.focus_seen = False         # lo último que dijo coffe, aunque esté apagada
        self.pointer = None
        self.monitor = hypr.focused_monitor()

        win = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(win)
        LayerShell.set_namespace(win, 'elyares')
        LayerShell.set_layer(win, LayerShell.Layer.TOP)
        LayerShell.set_anchor(win, LayerShell.Edge.TOP, True)
        # Zona exclusiva 0: el compositor la pone debajo de Waybar, no encima.
        LayerShell.set_exclusive_zone(win, 0)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
        win.set_default_size(WIN_W, WIN_H)
        self.win = win
        if self.monitor:
            self._set_monitor(self.monitor['name'])

        da = Gtk.DrawingArea()
        da.set_content_width(WIN_W)
        da.set_content_height(WIN_H)
        da.set_draw_func(self.draw)
        motion = Gtk.EventControllerMotion()
        motion.connect('enter', lambda *_: self.set_hover(True))
        motion.connect('leave', lambda *_: self.set_hover(False))
        motion.connect('motion', self.on_motion)
        da.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect('pressed', self.on_click)
        da.add_controller(click)
        right = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right.connect('pressed', self.on_right_click)
        da.add_controller(right)
        middle = Gtk.GestureClick(button=Gdk.BUTTON_MIDDLE)
        middle.connect('pressed', self.on_middle_click)
        da.add_controller(middle)
        win.set_child(da)
        self.da = da

        css = Gtk.CssProvider()
        css.load_from_string('window, window.background { background: transparent; }')
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        win.present()
        self.update_region()

        ipc.serve(lambda msg, req: GLib.idle_add(self.on_socket, msg, req),
                  lambda req: GLib.idle_add(self.on_gone, req))
        hypr.listen(lambda name: GLib.idle_add(self.on_focused_monitor, name))
        # Los vigilantes corren siempre y miran la preferencia en cada vuelta:
        # así una fuente se prende y se apaga sin reiniciar elyares-engineer.
        emit = lambda msg: GLib.idle_add(self.on_message, msg, None)  # noqa: E731
        self.tests = testrun.Follower(emit)
        devherd.watch(emit, lambda: self.settings['devherd'])
        coffe.watch(emit)
        github.watch(emit, lambda: self.settings['github'],
                     lambda: self.settings['github_accounts'])
        GLib.timeout_add_seconds(3, self.poll_dnd)
        # "Terminó" y "esperando" caducan solos aunque no lleguen más eventos.
        GLib.timeout_add_seconds(1, self.on_second)
        if self.model.sessions:
            # Sesiones del daemon anterior: algún pane pudo cerrarse entre tanto.
            self.refresh()
            self.check_panes()

    # ── estado ───────────────────────────────────────────────────────────────

    def on_socket(self, msg, req):
        # Un botón que corre un comando solo lo ponen los vigilantes del
        # propio elyares-engineer. Por el socket una alerta puede traer ficha y botones
        # que abren una URL, pero no comandos: quien pueda escribir aquí no
        # debe poder disfrazar de "Logs" lo que quiera correr.
        if isinstance(msg.get('actions'), list):
            msg['actions'] = [a for a in msg['actions'] if isinstance(a, dict) and 'cmd' not in a]
        return self.on_message(msg, req)

    def on_message(self, msg, req):
        if 'control' in msg:
            self.on_control(msg['control'], msg, req)
            if req and not req.done:
                req.reply(None)
            return GLib.SOURCE_REMOVE
        if msg.get('event') == 'source':
            if self.on_source(msg):
                self.ensure_tick()
            return GLib.SOURCE_REMOVE
        if msg.get('event') == 'focus':
            self.focus_seen = bool(msg.get('on'))
        source = sources.source_of(msg)
        if source != 'claude' and not self.settings[source]:
            # Fuente apagada: lo que mande se ignora.
            if req:
                req.reply(None)
            return GLib.SOURCE_REMOVE
        if 'results' not in msg:
            # Pruebas en una terminal: al empezar se las sigue y al terminar
            # el mensaje vuelve con sus resultados (`results`).
            if msg.get('event') == 'cmd-start' and not self.tests.start(msg):
                return GLib.SOURCE_REMOVE
            if msg.get('event') == 'cmd-done' and self.tests.finish(msg):
                return GLib.SOURCE_REMOVE
        focus = self.model.focus
        self.model.handle(msg, req)
        self.refresh()
        if focus and not self.model.focus and any(
                s.state in ('waiting', 'alert') for s in self.model.sessions.values()):
            # Se acabó el pomodoro: ahora sí, lo que se quedó esperando.
            self.expand(KEY_OPEN_SECS)
        return GLib.SOURCE_REMOVE

    def on_source(self, msg):
        """Una fuente cuenta cómo está. True si cambió lo que se ve en su pastilla.

        Además de `ok` y `note` puede traer lo que dirá su burbuja: `tip`
        (unas líneas con cómo están las cosas) y, si no responde, `why` y
        `fix`. Con `polled` avisa de que acaba de consultar.
        """
        name, now = msg.get('name'), time.monotonic()
        if name not in sources.LABELS:
            return False
        old = self.sources.get(name) or {}
        ok = msg.get('ok')
        tip = msg.get('tip') if isinstance(msg.get('tip'), list) else []
        self.sources[name] = {
            'ok': ok, 'note': str(msg.get('note') or ''),
            'why': str(msg.get('why') or ''), 'fix': str(msg.get('fix') or ''),
            'tip': [t for t in tip if isinstance(t, str)][:TIP_LINES],
            'since': old.get('since', now) if old.get('ok') == ok else now,   # desde cuándo está así
            'polled': now if msg.get('polled') else old.get('polled', 0)}
        return (ok, self.sources[name]['note']) != (old.get('ok'), old.get('note'))

    def on_gone(self, req):
        self.model.gone(req)
        self.refresh()
        return GLib.SOURCE_REMOVE

    def on_second(self):
        self.seconds += 1
        if self.seconds % REAP_SECS == 0:
            # Las sesiones sin pane (las de segundo plano) no tienen otra
            # forma de irse si se cierran sin avisar.
            self.model.reap(actions.proc_alive)
        if self.model.sessions:
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def poll_dnd(self):
        dnd = actions.do_not_disturb()
        if dnd != self.dnd:
            self.dnd = dnd
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self):
        v = self.model.view(pin=self.pin)
        if self.dnd and v.mode != 'hidden' and v.pet != 'permission':
            v.mode, v.pet = 'peek', 'sleep'
        if v.pet != self.pet_state:
            self.pet_state, self.pet_since = v.pet, time.monotonic()
        if v.title:
            self.title, self.detail = v.title, v.detail
            self.agent_name, self.role = v.agent_name, v.role
        elif self.expanded and v.others:
            # Abierta a mano sin nada corriendo: la cabecera lo dice y la lista
            # trae las sesiones en reposo.
            self.title, self.detail = 'Sin sesiones activas', f'{len(v.others)} en reposo'
            self.agent_name = ''
        elif self.expanded:
            self.title, self.detail, self.agent_name = 'Sin sesiones', 'Nada corriendo ahora', ''
        self.follow(v)
        changed = v.mode != self.view.mode or v.key != self.view.key
        if v.key != self.view.key:
            self.key_since = time.monotonic()
        self.view = v
        if changed or v.mode != 'hidden':
            self.ensure_tick()
        data = self.model.dump()
        if data != self.saved:
            self.saved = data
            store.save(data)

    def load_theme(self):
        """Acento de la mascota y colores del texto, del tema de omarchy."""
        palette = theme.palette()
        mascot.set_accent(palette.get('accent'))
        self.colors = paint.colors(palette)
        self.markups = {}

    def markup(self, detail):
        """El detalle con su resaltado, como marcado de Pango."""
        if detail not in self.markups:
            if len(self.markups) > 200:
                self.markups.clear()
            self.markups[detail] = ''.join(
                f'<span foreground="{self.colors[role]}">{html.escape(text, quote=False)}</span>'
                for text, role in paint.segments(detail))
        return self.markups[detail]

    def source_state(self, key):
        if key != 'claude' and not self.settings[key]:
            return 'off'
        ok = self.sources.get(key, {}).get('ok')
        return 'unknown' if ok is None else 'on' if ok else 'bad'

    def source_note(self, key):
        if key == 'claude':
            n = self.view.count
            return f'{n} sesión' if n == 1 else f'{n} sesiones'
        return self.sources.get(key, {}).get('note', '')

    def source_tip(self, key):
        """Lo que dice la burbuja de una pastilla: (título, filas). Una fila es
        ('text', texto, color), ('head', título de un bloque) o
        ('cmd', comando, qué hace)."""
        text, dim = rgb(self.colors['text']), rgb(self.colors['dim'])
        if key == commands.HELP:
            return 'Atajos de elyares-engineer', [('text', 'Para consultar: nada de aquí se ejecuta', dim)
                                            ] + self.tip_ref
        state, now = self.source_state(key), time.monotonic()
        src = self.sources.get(key) or {}
        facts = [sources.STATE_TEXT[state].capitalize()]
        # En rojo, la nota es la de la avería, no el número de sesiones.
        note = src.get('note', '') if state == 'bad' else self.source_note(key)
        if state == 'bad' and src.get('why') and key not in sources.MISSING:
            # Lo que falta instalar falta desde siempre; lo que dejó de
            # responder, desde un momento que vale la pena saber.
            facts[0] += f' desde {ago(now - src["since"])}'
        elif note and state != 'off':
            facts.append(note)
        if key == 'usage' and state == 'on' and self.model.limit:
            facts.append(f'límite de 5 h al {self.model.limit:.0f}%')
        if key != 'claude' and state == 'on':
            n = sum(1 for sid in self.model.sessions if sid.startswith(sources.PREFIXES[key]))
            facts.append('sin alertas' if not n else '1 alerta' if n == 1 else f'{n} alertas')
        lines = [(sources.ABOUT[key], text),
                 (' · '.join(facts), rgb(paint.RED) if state == 'bad' else dim)]
        if state == 'bad':
            # Por qué está en rojo y qué hacer.
            lines += [(line, text) for line in (src.get('why') or note, src.get('fix')) if line]
        elif state == 'on':
            lines += [(line, text) for line in src.get('tip') or []]
            if key == 'coffe' and self.model.focus:
                held = sum(1 for s in self.model.sessions.values() if s.state in ('waiting', 'alert'))
                if held:
                    lines.append(('1 aviso espera al descanso' if held == 1
                                  else f'{held} avisos esperan al descanso', text))
            if src.get('polled'):
                lines.append((f'Consultado {ago(now - src["polled"])}', dim))
        if key != 'claude':
            # Claude no se apaga desde aquí: sin sus hooks no hay nada que mostrar.
            lines.append(('Clic para prenderla' if state == 'off' else 'Clic para apagarla',
                          MUTED_COLOR[:3]))
        return sources.LABELS[key], [('text', *line) for line in lines] + self.tip_ref

    def toggle_source(self, key):
        """Prende o apaga una fuente. Al apagarla se van sus alertas."""
        on = not self.settings[key]
        self.settings[key] = on
        settings.save(self.settings)
        if not on:
            for sid in [s for s in self.model.sessions if s.startswith(sources.PREFIXES[key])]:
                self.model.sessions.pop(sid)
            if key == 'usage':
                for s in self.model.sessions.values():
                    s.context = 0
                store.forget_usage()
        elif key == 'usage':
            # Que la barra de estado vuelva a mandar lo que ya había mandado.
            store.forget_usage()
        if key == 'coffe':
            self.model.focus = on and self.focus_seen
        self.refresh()
        self.ensure_tick()

    def on_control(self, order, msg=None, req=None):
        if order == 'status':
            if req:
                req.reply({'sources': [
                    {'key': key, 'label': label, 'state': self.source_state(key),
                     'note': self.source_note(key)} for key, label in sources.SOURCES]})
        elif order in ('allow', 'deny'):
            why = self.answer(order == 'allow', (msg or {}).get('peer'))
            if req:
                req.reply({'ok': not why, 'why': why})
        elif order == 'toggle':
            if (msg or {}).get('source') in sources.PREFIXES:
                self.toggle_source(msg['source'])
        elif order == 'hide':
            self.off = not self.off
            self.collapse()
        elif order == 'compact':
            self.toggle_compact()
        elif order == 'pin':
            self.toggle_pinned()
        elif order == 'theme':
            self.load_theme()
            self.ensure_tick()
        elif order == 'glass':
            self.settings['glass'] = not self.settings['glass']
            settings.save(self.settings)
            self.ensure_tick()
        elif order in ('tab', 'steps'):
            # Con el teclado: la pestaña que sigue, o el desglose del que sigue.
            self.off = False
            if order == 'tab':
                self.next_tab()
            else:
                self.next_focus()
            self.expand(KEY_OPEN_SECS)
        elif order == 'open':
            if self.expanded and not self.off:
                # Cerrarla a mano también la desfija: si no, no se cerraría.
                if self.settings['pinned']:
                    self.toggle_pinned()
                else:
                    self.collapse()
            else:
                self.off = False
                self.expand(PREVIEW_OPEN_SECS if self.preview() else KEY_OPEN_SECS)

    def answer(self, allow, peer=None, now=None):
        """Contesta con el teclado el permiso que está a la vista. Devuelve por
        qué no lo hizo, o '' si lo contestó.

        Solo el que se ve (en la cabecera o, en el tablero, en la pestaña
        elegida): no uno tapado por otra sesión, ni con la isla escondida, ni
        uno que acaba de salir y no dio tiempo de leer. Y permitir no puede
        pedirlo un proceso lanzado por Claude: se estaría aprobando a sí
        mismo. Denegar, sí.
        """
        if allow and (not peer or 'claude' in peer):
            return 'permitir no se puede pedir desde una sesión de Claude'
        s = self.asking()
        if self.off or s is None:
            return 'no hay ningún permiso a la vista'
        if (now or time.monotonic()) - self.key_since < ASK_GUARD_SECS:
            return 'el permiso acaba de salir: léelo y pulsa otra vez'
        self.model.decide(s, allow)
        self.refresh()
        return ''

    @staticmethod
    def who(agent_name, project, color=None):
        """«agente | proyecto», como texto y como marcado de Pango. El agente
        va en su color; sin color (uno que no es de la familia), en blanco
        como el proyecto."""
        tint = f' foreground="{color}"' if color else ''
        return (f'{agent_name} | {project}',
                f'<span{tint}>{html.escape(agent_name, quote=False)}</span>'
                f'<span foreground="{SEP_COLOR}"> | </span>{html.escape(project, quote=False)}')

    def head_notes(self):
        """Lo que va a la derecha del título, como (texto, color) y de derecha
        a izquierda: si está fijada, cuántas sesiones hay, el contexto de la
        que se muestra y si pide permiso."""
        best = self.view.session
        notes = [('fijada', rgb('accent'))] if self.settings['pinned'] else []
        if self.view.count > 1:
            notes.append((f'{self.view.count} sesiones', MUTED_COLOR[:3]))
        if best and best.context >= CONTEXT_SHOW:
            notes.append((f'{best.context:.0f}%',
                          rgb(self.colors[paint.context_role(best.context)])))
        if best and best.state == 'permission':
            notes.append(('pide permiso', rgb('red')))
        return notes

    # ── el tablero ───────────────────────────────────────────────────────────

    def everyone(self):
        v = self.view
        return ([v.session] if v.session else []) + v.others

    def claude(self):
        """Las sesiones de Claude, de la más urgente a la que lleva más en reposo."""
        return [s for s in self.everyone() if s.state != 'alert']

    def alerts(self):
        return [s for s in self.everyone() if s.state == 'alert']

    def tabs(self):
        """Las pestañas del tablero: las sesiones, por nombre para que no cambien de sitio."""
        return sorted(self.claude(), key=lambda s: (s.proj.lower(), s.sid))

    def tab_session(self):
        """La sesión de la pestaña elegida. Si no hay ninguna elegida, o se
        fue, se queda con la más urgente."""
        sessions = self.claude()
        chosen = next((s for s in sessions if s.sid == self.tab), None)
        if chosen is None and sessions:
            chosen = sessions[0]
            self.tab = chosen.sid
        return chosen

    def follow(self, v):
        """La pestaña se va sola a la sesión que pide permiso o acaba de
        terminar: es lo que no debe quedarse tapado en otra carpeta. Y si la
        elegida se quedó en reposo, a la más urgente de las que trabajan: con
        los cuatro libres a la vista mientras otra sesión trabaja, la isla
        parece desconectada. Solo con una novedad: sin ella, la pestaña que
        se eligió a mano se queda."""
        if v.key == self.view.key:
            return
        s = v.session
        if s is None or s.state not in ('permission', 'done'):
            sessions = [o for o in ([s] if s else []) + v.others if o.state != 'alert']
            chosen = next((o for o in sessions if o.sid == self.tab), None)
            if chosen is None or self.busy(chosen):
                return
            s = next((o for o in sessions if self.busy(o)), None)
            if s is None:
                return
        if self.tab != s.sid:
            self.focus = None
        self.tab = s.sid

    @staticmethod
    def busy(s):
        """¿Alguno de los cuatro de la sesión hace algo? Es lo que dice su tablero."""
        return any(m.busy for m in s.team())

    def focused(self):
        """(sesión, miembro) del desglose abierto, o None. Se cierra solo si
        se cambió de pestaña o ya no quedan pasos que leer."""
        s = self.tab_session()
        if not self.focus or s is None or s.sid != self.focus[0]:
            return None
        member = next((m for m in s.team() if m.role == self.focus[1]), None)
        return (s, member) if member is not None and member.steps else None

    def next_tab(self):
        """Pasa a la pestaña que sigue, y de la última a la primera."""
        tabs = [s.sid for s in self.tabs()]
        if tabs:
            here = self.tab_session().sid
            self.tab, self.focus = tabs[(tabs.index(here) + 1) % len(tabs)], None

    def next_focus(self):
        """Abre el desglose del primero que tenga pasos, luego el del que
        sigue, y después del último vuelve al tablero."""
        s = self.tab_session()
        if s is None:
            return
        roles = [m.role for m in s.team() if m.steps]
        now = self.focus[1] if self.focused() else None
        after = roles[roles.index(now) + 1:] if now in roles else roles
        self.focus = (s.sid, after[0]) if after else None

    def asking(self):
        """La sesión cuyo permiso se puede contestar desde la isla: la de la
        cabecera o, en el tablero, la de la pestaña elegida."""
        s = self.tab_session() if self.target() == 'board' else self.view.session
        return s if s is not None and s.state == 'permission' and s.ask is not None else None

    def minis(self):
        """Los demás que trabajan, para la isla asomada: (personaje, gesto) de
        cada uno, sin el que ya es la mascota grande."""
        out = [(s.sid, m.role, MEMBER_PET[m.state]) for s in self.claude() for m in s.team() if m.busy]
        big = self.view.session
        if big is not None:
            mine = next((it for it in out if it[:2] == (big.sid, self.view.role)), None)
            if mine in out:
                out.remove(mine)
        return [(role, pet) for _sid, role, pet in out[:MAX_MINIS]]

    def rows_for(self, mode):
        """Las alertas que van en filas: en el tablero, todas; con la cabecera
        de siempre, las que no están en ella."""
        return self.alerts() if mode == 'board' else self.view.others

    def expand(self, secs=None):
        """Abre la isla a mano. Con secs se cierra sola si el ratón no está encima."""
        if self.collapse_id:
            GLib.source_remove(self.collapse_id)
            self.collapse_id = 0
        self.expanded = True
        if secs and not self.settings['pinned']:
            self.collapse_id = GLib.timeout_add_seconds(secs, self.on_collapse)
        self.refresh()
        self.ensure_tick()
        self.check_panes()

    def check_panes(self):
        """Olvida, sin frenar la isla, las sesiones cuyo pane se cerró sin avisar."""
        socks = {s.tmux.split(',')[0] for s in self.model.sessions.values() if s.pane and s.tmux}
        if socks:
            threading.Thread(
                target=lambda: GLib.idle_add(self.on_panes, actions.live_panes(socks)),
                daemon=True).start()

    def on_panes(self, panes):
        if self.model.prune(panes):
            self.refresh()
        return GLib.SOURCE_REMOVE

    def collapse(self):
        if self.collapse_id:
            GLib.source_remove(self.collapse_id)
            self.collapse_id = 0
        # Fijada no se cierra: solo suelta la alerta que se había elegido en la
        # lista, para que no tape algo más urgente.
        self.expanded = self.settings['pinned']
        if not self.expanded:
            self.focus = None           # al volver a abrirla, el tablero y no un desglose
        if self.pin:
            self.pin = ''
            self.refresh()
        self.ensure_tick()

    def on_collapse(self):
        self.collapse_id = 0
        # Con el ratón encima se queda abierta; la cierra el 'leave'.
        if not self.hover:
            self.collapse()
        return GLib.SOURCE_REMOVE

    def toggle_pinned(self):
        """Fija la isla abierta, o la suelta para que vuelva a cerrarse sola."""
        self.settings['pinned'] = not self.settings['pinned']
        settings.save(self.settings)
        if self.settings['pinned']:
            self.off = False
            self.expand()
        else:
            self.collapse()

    def toggle_compact(self):
        self.settings['compact'] = not self.settings['compact']
        settings.save(self.settings)
        self.collapse()

    def target(self):
        if self.off:
            return 'off'
        mode = self.view.mode
        if self.expanded:
            # Abierta a mano: el tablero. Sin ninguna sesión se abre igual, con
            # la cabecera de siempre: es donde están las fuentes.
            if self.claude():
                return 'board'
            return 'list' if self.view.others else 'open'
        if mode == 'open' and self.view.ask:
            return 'ask'
        # Un permiso se abre solo aunque esté compacta: hay que contestarlo.
        if self.settings['compact'] and self.view.pet != 'permission':
            return 'petit' if mode != 'hidden' or self.hover else 'hidden'
        if self.hover:
            if mode == 'hidden':
                mode = 'peek'
            elif mode == 'peek' and self.view.session:
                mode = 'open'
            if mode == 'open':
                mode = 'board' if self.claude() else 'list' if self.view.others else 'open'
        return mode

    def extra(self, mode):
        """Alto de más para que el detalle se vea entero, en vez de cortado con "…".

        Solo cuando alguien lo está leyendo (isla abierta a mano o ratón encima)
        o hay que contestar un permiso, que es cuando importa ver el comando
        completo. Abierta sola por un aviso se queda en una línea.
        """
        if mode not in ('open', 'list', 'ask') or not self.title:
            return 0
        if not (self.view.ask or self.hover or self.expanded):
            return 0
        wide = self.preview_h(mode) or self.card_h(mode)
        width = (PREVIEW_W if wide else SIZES['open'][0]) - TEXT_INSET
        if self.wrap[0] != (self.detail, width):
            one = self._shape(self.da.create_pango_layout('X'), FONT_DETAIL)
            full = self._shape(self.da.create_pango_layout(self.detail or ''), FONT_DETAIL,
                               width, DETAIL_LINES)
            more = full.get_pixel_size()[1] - one.get_pixel_size()[1]
            self.wrap = ((self.detail, width), int(clamp(more, 0, MAX_EXTRA)))
        return self.wrap[1]

    def preview(self):
        """Lo que está editando la sesión que se ve (la de la cabecera o la de
        la pestaña elegida), si edita algo."""
        s = self.tab_session() if self.target() == 'board' else self.view.session
        return s.preview if s else None

    def preview_h(self, mode):
        """Alto de la vista previa del código: cuando alguien abrió la isla a
        mano, o cuando piden permiso para esa edición. En el tablero cede el
        sitio al desglose y a la ficha de una alerta."""
        p = self.preview()
        if not p or mode not in ('open', 'list', 'ask', 'board'):
            return 0
        if not (self.view.ask or self.hover or self.expanded):
            return 0
        if mode == 'board' and (self.focused() or self.card_h(mode)):
            return 0
        lines = len(p.lines) + (1 if p.more else 0)
        return PREVIEW_HEAD + lines * CODE_LINE_H + 2 * PREVIEW_PAD

    def card_h(self, mode):
        """Alto de la ficha de una alerta (su detalle y sus botones): cuando
        alguien la está leyendo, con el ratón encima o abierta a mano."""
        s = self.view.session
        if not s or not s.card or mode not in ('open', 'list', 'board'):
            return 0
        if mode == 'board' and self.focused():
            return 0
        # La de unas pruebas se ve sin pedirla mientras la isla está abierta
        # por ellas: para eso se abrió.
        if not (self.hover or self.expanded or (s.tests and self.view.mode == 'open')):
            return 0
        body = (PREVIEW_HEAD if s.where or s.note else 0) + len(s.lines) * CODE_LINE_H
        return (body + 2 * PREVIEW_PAD if body else 0) + CARD_BUTTONS

    def pills_h(self, mode):
        """Alto de la franja de fuentes: solo cuando alguien abrió la isla a mano."""
        by_hand = self.expanded or self.hover
        return PILLS_H if by_hand and mode in ('open', 'list', 'board') else 0

    def goal(self):
        """Tamaño al que va la isla: el del modo, más el detalle entero, las
        filas y las fuentes."""
        mode = self.target()
        prev = self.preview_h(mode)
        card = self.card_h(mode)
        more = self.extra(mode) + prev + card + self.pills_h(mode)
        rows = len(self.rows_for(mode))
        if mode == 'board':
            # Mide lo mismo trabajen uno, dos o los cuatro: solo crece el desglose.
            h = TABS_H + (FOCUS_H if self.focused() else BOARD_H) + BOARD_PAD
            if rows:
                h += LIST_PAD + ROW_H * min(ALERT_ROWS, rows)
            return BOARD_W, h + more
        if mode == 'list':
            w, h = SIZES['open']
            h += LIST_PAD + ROW_H * min(MAX_ROWS, rows)
        else:
            w, h = SIZES[mode]
        if mode == 'peek':
            # Asomada, con sitio para las caritas de los demás que trabajan.
            minis = len(self.minis())
            w += (6 + (MINI + 4) * ((minis + 1) // 2)) if minis else 0
        if prev:
            w, h = PREVIEW_W, h + (ASK_TALL if mode == 'ask' else 0)
        elif card:
            w = PREVIEW_W
        return w, h + more

    def set_hover(self, value):
        self.hover = value
        if not value:
            self.pointer = None
            self.collapse()
        self.ensure_tick()

    def on_motion(self, _ctrl, x, y):
        self.pointer = (x, y)

    def pet(self, now):
        if self.override:
            state, since, until = self.override
            if now < until:
                return state, now - since
            self.override = None
        return self.pet_state, now - self.pet_since

    def poke(self):
        now = time.monotonic()
        self.clicks = [c for c in self.clicks if now - c < 1.2] + [now]
        if len(self.clicks) >= 3:
            self.override = ('dizzy', now, now + 3)
            self.clicks = []
        elif not self.override or self.override[0] != 'dizzy':
            self.override = ('annoyed', now, now + 0.9)
        self.ensure_tick()

    # ── monitores ────────────────────────────────────────────────────────────

    def _set_monitor(self, name):
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            mon = monitors.get_item(i)
            if mon.get_connector() == name:
                LayerShell.set_monitor(self.win, mon)
                return True
        return False

    def on_focused_monitor(self, name):
        if self.monitor and self.monitor.get('name') == name:
            return GLib.SOURCE_REMOVE
        if self._set_monitor(name):
            self.monitor = next((m for m in hypr.monitors() if m.get('name') == name), None)
            self.region = None
            self.update_region()
        return GLib.SOURCE_REMOVE

    # ── animación ────────────────────────────────────────────────────────────

    def ensure_tick(self):
        if self.slow_id:
            GLib.source_remove(self.slow_id)
            self.slow_id = 0
        if not self.ticking:
            self.ticking = True
            self.last_frame = None
            self.da.add_tick_callback(self.on_tick)

    def on_tick(self, widget, _clock):
        now = time.monotonic()
        dt = 1 / 60 if self.last_frame is None else min(0.05, now - self.last_frame)
        self.last_frame = now

        tw, th = self.goal()
        for pos, vel, goal in (('w', 'vw', tw), ('h', 'vh', th)):
            x, v = getattr(self, pos), getattr(self, vel)
            v += (SPRING_K * (goal - x) - SPRING_C * v) * dt
            setattr(self, vel, v)
            setattr(self, pos, x + v * dt)
        settled = (abs(tw - self.w) < 0.5 and abs(th - self.h) < 0.5
                   and abs(self.vw) < 1 and abs(self.vh) < 1)
        if settled:
            self.w, self.h, self.vw, self.vh = tw, th, 0.0, 0.0

        if now > self.next_blink:
            self.blink_until = now + 0.13
            self.next_blink = now + 2 + random.random() * 3.5
        self.update_look(now)
        self.update_region()

        widget.queue_draw()
        if settled and not self.hover and not self.override:
            # Quieta: escondida no dibuja nada y asomada basta con IDLE_FPS. El
            # reloj de GTK despierta al proceso 60 veces por segundo aunque no
            # haya nada que redibujar.
            self.ticking = False
            if self.target() not in ('hidden', 'off'):
                self.slow_id = GLib.timeout_add(1000 // IDLE_FPS, self.on_slow)
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def on_slow(self):
        now = time.monotonic()
        if now > self.next_blink:
            self.blink_until = now + 0.13
            self.next_blink = now + 2 + random.random() * 3.5
        self.update_look(now)
        self.da.queue_draw()
        return GLib.SOURCE_CONTINUE

    def update_look(self, now):
        if now - self.last_look >= LOOK_EVERY and self.monitor:
            self.last_look = now
            pos = hypr.cursor_pos()
            if pos:
                m = self.monitor
                top = m['y'] + (m.get('reserved') or [0, 0])[1]
                dx = pos[0] - (m['x'] + m['width'] / 2)
                dy = pos[1] - (top + min(self.h, SIZES['ask'][1]) / 2)
                d = math.hypot(dx, dy) or 1
                k = min(1.0, d / 400)
                self.look_target = (dx / d * k, dy / d * k)
        self.look[0] += (self.look_target[0] - self.look[0]) * 0.15
        self.look[1] += (self.look_target[1] - self.look[1]) * 0.15

    def update_region(self):
        w = int(max(self.w, SIZES['hidden'][0]))
        h = int(max(self.h, HOVER_STRIP))
        # Escondida del todo no recibe nada: ni la franja que la hace asomarse.
        region = (0, 0, 0, 0) if self.off else ((WIN_W - w) // 2, 0, w, h)
        surface = self.win.get_surface()
        if surface and region != self.region:
            surface.set_input_region(cairo.Region(cairo.RectangleInt(*region)))
            self.region = region

    # ── dibujo ───────────────────────────────────────────────────────────────

    def island_rect(self, width):
        w = clamp(self.w, 0, width)
        h = clamp(self.h, 0, WIN_H)
        return (width - w) / 2, w, h

    def draw(self, _da, cr, width, _height):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        x0, w, h = self.island_rect(width)
        if h < 0.5 or w < 1:
            return
        r = min(26, h / 2, w / 2) if h > 12 else min(8, h)
        cr.move_to(x0, 0)
        cr.line_to(x0 + w, 0)
        cr.line_to(x0 + w, h - r)
        cr.arc(x0 + w - r, h - r, r, 0, math.pi / 2)
        cr.line_to(x0 + r, h)
        cr.arc(x0 + r, h - r, r, math.pi / 2, math.pi)
        cr.close_path()
        glass = self.settings['glass']
        cr.set_source_rgba(*ISLAND_BG[:3], GLASS_ALPHA if glass else ISLAND_BG[3])
        cr.fill_preserve()
        edge = cr.copy_path() if glass else None
        cr.save()
        cr.clip()

        now = time.monotonic()
        mode = self.target()
        pills = self.pills_h(mode)
        prev = self.preview_h(mode)
        card = self.card_h(mode)
        self.buttons, self.rows, self.pills, self.hits = {}, [], [], []
        self.tip = self.card_span = None
        if mode == 'board':
            full_h = h
            text_alpha = clamp((w - 420) / 120) * clamp((h - 110) / 60)
            body = FOCUS_H if self.focused() else BOARD_H
            if text_alpha > 0:
                self.draw_board(cr, x0, w, body, text_alpha, now)
            head = TABS_H + body + BOARD_PAD
            listed = True
        else:
            full_h, head, text_alpha = self.draw_head(cr, x0, w, h, mode, bool(prev or card or pills), now)
            listed = self.list_layout and mode != 'ask'
        below = clamp((full_h - head) / 20) * text_alpha
        if prev and full_h > head:
            self.draw_preview(cr, x0, w, head, prev, below)
        if card and full_h > head:
            self.draw_card(cr, x0, w, head, card, below)
        head += prev + card             # la lista va debajo de la vista previa o de la ficha
        rows = self.rows_for(mode)
        if listed and rows and full_h > head:
            self.draw_rows(cr, x0, w, head, below, rows, ALERT_ROWS if mode == 'board' else MAX_ROWS)
        if pills and full_h > head:
            self.draw_pills(cr, x0, w, full_h, below)
        cr.restore()
        if edge:
            # El filo claro es lo que hace que el fondo translúcido se lea como vidrio.
            cr.append_path(edge)
            cr.set_source_rgba(1, 1, 1, GLASS_EDGE)
            cr.set_line_width(1)
            cr.stroke()
        if self.tip:
            self.draw_tip(cr, width, full_h, now)
        else:
            self.tip_key = None

    def draw_head(self, cr, x0, w, h, mode, below, now):
        """La cabecera de siempre: la mascota, «agente | proyecto», lo que
        pasa y, si pide permiso, sus botones. Devuelve el alto de la isla,
        dónde termina la cabecera y la opacidad del texto."""
        # Con lista o con el detalle entero, la cabecera (mascota y texto) se
        # queda arriba y lo demás va debajo. El diseño dura hasta que la isla
        # vuelve a su alto normal, para que la cabecera no brinque al cerrarse.
        extra = self.extra(mode)
        head = OPEN_H + extra           # dónde termina la cabecera
        if mode == 'list' or (mode == 'open' and extra) or below:
            self.list_layout = True
        elif mode == 'ask' or h <= OPEN_H + 0.5:
            self.list_layout = False
        full_h, h = h, (min(h, OPEN_H) if self.list_layout else h)

        # La mascota crece con la isla: en miniatura en la pastilla compacta,
        # completa desde que la isla está asomada.
        pet_size = clamp((h - 6) / (SIZES['peek'][1] - 6))
        pet_alpha = clamp((h - 10) / 16)
        if pet_alpha > 0 and pet_size > 0.1:
            state, age = self.pet(now)
            # Asomada va al centro; con las caritas de los demás, a la izquierda.
            cx = x0 + min(w / 2, 12 + PET / 2) if w > SIZES['peek'][0] + 4 else x0 + w / 2
            # La capa intermedia solo hace falta mientras aparece o desaparece.
            fading = pet_alpha < 1
            if fading:
                cr.push_group()
            else:
                cr.save()
            cr.translate(cx, h / 2 + 5 * pet_size)
            cr.scale(PET_SCALE * pet_size, PET_SCALE * pet_size)
            mascot.draw(cr, state, age, now, tuple(self.look), now < self.blink_until,
                        role=self.view.role)
            if fading:
                cr.pop_group_to_source()
                cr.paint_with_alpha(pet_alpha)
            else:
                cr.restore()
            if mode == 'peek':
                self.draw_minis(cr, x0, w, h, pet_alpha * clamp((w - SIZES['peek'][0]) / 20))

        # Con botones, el texto sube y deja la fila de abajo para ellos.
        ask_alpha = clamp((full_h - SIZES['open'][1]) / 16) if self.view.ask else 0.0
        mid = h / 2 - (h / 2 - 37) * ask_alpha
        text_alpha = clamp((w - 220) / 160) * clamp((h - 50) / 30)
        if text_alpha > 0 and self.title:
            tx = x0 + 12 + PET + 10
            right = x0 + w - 18
            title_right = right
            for text, color in self.head_notes():
                badge = self._layout(cr, text, FONT_DETAIL)
                title_right -= badge.get_pixel_size()[0]
                cr.move_to(title_right, mid - 17)
                cr.set_source_rgba(*color, text_alpha)
                PangoCairo.show_layout(cr, badge)
                title_right -= 12
            # Una sesión se nombra «agente | proyecto»; una alerta, con su título.
            text, markup = (self.who(self.agent_name, self.title, mascot.accent(self.role))
                            if self.agent_name else (self.title, None))
            title = self._layout(cr, text, FONT_TITLE, title_right - tx, markup=markup)
            cr.move_to(tx, mid - 21)
            # Opaco: la transparencia la pone `_show` sobre el texto entero.
            cr.set_source_rgba(*TITLE_COLOR[:3], 1)
            self._show(cr, title, text_alpha)
            detail = self._layout(cr, self.detail, FONT_DETAIL, right - tx,
                                  DETAIL_LINES if extra else 1, self.markup(self.detail))
            cr.move_to(tx, mid + 3)
            self._show(cr, detail, text_alpha)
        if ask_alpha > 0 and text_alpha > 0:
            self.draw_buttons(cr, x0 + w - 18, full_h - 14, ask_alpha * text_alpha)
        return full_h, head, text_alpha

    def draw_minis(self, cr, x0, w, h, alpha):
        """Las caritas de los demás que trabajan, a la derecha de la mascota."""
        minis = self.minis()
        if alpha <= 0 or not minis:
            return
        left = x0 + SIZES['peek'][0] - 4
        for i, (role, pet) in enumerate(minis):
            col, row = divmod(i, 2)
            rows = 2 if len(minis) - col * 2 > 1 else 1
            y = h / 2 + 2 + (row - (rows - 1) / 2) * (MINI + 3)
            self.face(cr, role, pet, left + col * (MINI + 4) + MINI / 2, y, MINI, alpha)

    # ── el tablero ───────────────────────────────────────────────────────────

    def face(self, cr, role, pet, x, y, size, alpha, now=None, age=0.0):
        """Uno de la familia, de `size` de alto y centrado en (x, y). Con
        `now` se mueve y mira al cursor; sin él, quieto."""
        cr.push_group()
        cr.translate(x, y + size * .015)
        cr.scale(size / 253, size / 253)
        if now is None:
            mascot.draw(cr, pet, 0, 0, motion=0, role=role)
        else:
            mascot.draw(cr, pet, age, now, tuple(self.look), now < self.blink_until, role=role)
        cr.pop_group_to_source()
        cr.paint_with_alpha(alpha)

    def put(self, cr, text, font, x, y, color, alpha, width=None, align=0.0, markup=None, lines=1):
        """Pinta un texto con (x, y) arriba a la izquierda y devuelve su
        ancho. `align` lo corre: .5 lo centra en x y 1 lo pega a x por la
        derecha."""
        layout = self._layout(cr, text, font, width, lines, markup)
        tw = layout.get_pixel_size()[0]
        cr.move_to(x - tw * align, y)
        if markup:
            cr.set_source_rgba(*color[:3], 1)
            self._show(cr, layout, alpha)
        else:
            cr.set_source_rgba(*color[:3], alpha)
            PangoCairo.show_layout(cr, layout)
        return tw

    def over(self, x, y, w, h):
        px, py = self.pointer or (-1, -1)
        return x <= px <= x + w and y <= py <= y + h

    @staticmethod
    def panel(cr, x, y, w, h, alpha, tint=None, over=False):
        """Una tarjeta del tablero. Con `tint`, un velo de ese color que sube
        desde abajo: de qué color es dice cómo está quien va dentro."""
        mascot.rrect(cr, x, y, w, h, 16)
        cr.set_source_rgba(1, 1, 1, (.085 if over else .05) * alpha)
        cr.fill_preserve()
        if tint:
            r, g, b, _ = mascot.rgba(tint)
            veil = cairo.RadialGradient(x + w / 2, y + h * 1.25, 4, x + w / 2, y + h * 1.25, h * 1.05)
            veil.add_color_stop_rgba(0, r, g, b, .42 * alpha)
            veil.add_color_stop_rgba(1, r, g, b, 0)
            cr.set_source(veil)
            cr.fill_preserve()
        cr.new_path()

    @staticmethod
    def tab_dot(s):
        """El color del punto de una pestaña: rojo si piden permiso, el del
        que trabaja, amarillo si espera, verde si terminó; None en reposo."""
        states = {m.state for m in s.team()}
        if 'permission' in states:
            return 'red'
        if 'working' in states:
            return mascot.accent(s.role)
        return 'yellow' if 'waiting' in states else 'green' if 'done' in states else None

    @staticmethod
    def tab_label(s):
        """El nombre de una sesión en su pestaña: el de su carpeta y, si lo
        tiene, el que le puso Claude Code."""
        return f'{s.proj} · {s.label or BG_TAG}' if s.label or s.kind == 'bg' else s.proj

    def tab_labels(self):
        """El nombre de cada pestaña. Dos sesiones que se llamarían igual (la
        misma carpeta, sin nombre propio) se numeran desde la segunda."""
        labels, seen = {}, {}
        for s in self.tabs():
            label = self.tab_label(s)
            seen[label] = seen.get(label, 0) + 1
            labels[s.sid] = label if seen[label] == 1 else f'{label} {seen[label]}'
        return labels

    def draw_board(self, cr, x0, w, body, alpha, now):
        """El tablero: las pestañas y, de la sesión elegida, sus cuatro. Los
        que trabajan van al frente y los libres a la banca; con los cuatro
        trabajando son cuatro cuadros, y con ninguno, los cuatro en fila."""
        s = self.tab_session()
        self.draw_tabs(cr, x0, w, s, alpha)
        left, top, width = x0 + BOARD_PAD, TABS_H, w - 2 * BOARD_PAD
        focus = self.focused()
        if focus:
            self.draw_focus(cr, left, top, width, body, focus[1], s, alpha, now)
            return
        team = s.team()
        front = [m for m in team if m.busy]
        if not front or len(front) == len(team):
            # Todos igual: en fila si están libres, en cuatro cuadros si trabajan.
            cols = 2 if front else len(team)
            cw = (width - (cols - 1) * BOARD_GAP) / cols
            ch = (body - BOARD_GAP) / 2 if front else body
            for i, member in enumerate(team):
                self.draw_member(cr, s, member, left + (i % cols) * (cw + BOARD_GAP),
                                 top + (i // cols) * (ch + BOARD_GAP), cw, ch, alpha, now)
            return
        stage = width - BENCH_W - BOARD_GAP
        cw = (stage - (len(front) - 1) * BOARD_GAP) / len(front)
        for i, member in enumerate(front):
            self.draw_member(cr, s, member, left + i * (cw + BOARD_GAP), top, cw, body, alpha, now)
        self.draw_bench(cr, s, [m for m in team if not m.busy], left + stage + BOARD_GAP, top,
                        BENCH_W, body, alpha)

    def draw_tabs(self, cr, x0, w, current, alpha):
        """Una pestaña por sesión, y a la derecha las notas de la elegida."""
        right = x0 + w - 18
        notes = [('fijada', rgb('accent'))] if self.settings['pinned'] else []
        if current.context >= CONTEXT_SHOW:
            notes.append((f'{current.context:.0f}%',
                          rgb(self.colors[paint.context_role(current.context)])))
        for text, color in notes:
            right -= self.put(cr, text, FONT_DETAIL, right, 10, color, alpha, align=1) + 12
        tabs, labels = self.tabs(), self.tab_labels()
        x, y, th = x0 + 12, 6, 24
        # Si no caben, se reparten el sitio y el nombre se corta.
        room = max(40, (right - x) / len(tabs) - 4)
        for s in tabs:
            label = self._layout(cr, labels[s.sid], FONT_ROW, room - 28)
            lw, lh = label.get_pixel_size()
            tw = lw + 28
            chosen = s is current
            if chosen or self.over(x, y, tw, th):
                mascot.rrect(cr, x, y, tw, th, th / 2)
                cr.set_source_rgba(1, 1, 1, (.13 if chosen else .06) * alpha)
                cr.fill()
            color = self.tab_dot(s)
            cr.new_sub_path()
            cr.arc(x + 12, y + th / 2, 3.5 if color else 3, 0, 2 * math.pi)
            if color:
                cr.set_source_rgba(*mascot.rgba(color, alpha))
                cr.fill()
            else:
                cr.set_source_rgba(*mascot.rgba('metal', .7 * alpha))
                cr.set_line_width(1.5)
                cr.stroke()
            cr.move_to(x + 21, y + (th - lh) / 2)
            cr.set_source_rgba(*(TITLE_COLOR if chosen else MUTED_COLOR)[:3], alpha)
            PangoCairo.show_layout(cr, label)
            self.hits.append(('tab', s.sid, x, y, tw, th))
            x += tw + 4

    def draw_member(self, cr, s, member, x, y, cw, ch, alpha, now):
        """Uno de los cuatro en su tarjeta: su cara con el gesto de cómo está,
        su nombre y sus últimos pasos. Si pide permiso, lo que quiere hacer
        entero y los botones. Libre va apagado."""
        busy, role = member.busy, member.role
        tint = MEMBER_TINT.get(member.state) or mascot.accent(role)
        self.panel(cr, x, y, cw, ch, alpha, tint if busy else None, busy and self.over(x, y, cw, ch))
        if busy:
            self.hits.append(('member', (s.sid, role), x, y, cw, ch))
        # Cuatro acomodos según el sitio: en columna (tres al frente, o los
        # cuatro libres), en cuadro (los cuatro trabajando), a medias (dos) y a
        # lo ancho (uno). `sx` y `sw` son dónde van sus pasos.
        quad, column = ch < 100, cw < 200 and ch >= 100
        wide = cw >= 300 and not quad
        if column:
            size, fx, fy = 56, x + cw / 2, y + 42
            tx, ty, tw = x + 12, y + 78, cw - 24
            sx, sw = tx, tw
        elif quad:
            size, fx, fy = 54, x + 38, y + ch / 2 + 2
            tx, ty, tw = x + 74, y + 9, cw - 86
            sx, sw = tx, tw
        elif wide:
            size, fx, fy = 84, x + 56, y + ch / 2 + 4
            tx, ty = x + 112, y + 16
            tw = x + cw - 14 - tx
            sx, sw = tx, tw
        else:
            # A medias: la cara arriba con el nombre al lado, y los pasos a todo lo ancho.
            size, fx, fy = 56, x + 38, y + 40
            tx, ty = x + 72, y + 18
            tw = x + cw - 12 - tx
            sx, sw = x + 14, cw - 28
        asleep = role == MAIN_ROLE and not busy and not s.delegating
        pet = MEMBER_PET.get(member.state, 'sleep' if asleep else 'idle')
        self.face(cr, role, pet, fx, fy, size, alpha * (1 if busy else .35), now if busy else None,
                  now - s.changed)
        name_color = rgb(mascot.accent(role)) if busy else MUTED_COLOR
        if column:
            self.put(cr, member.name, FONT_ROW, x + cw / 2, ty, name_color, alpha, tw, .5)
        else:
            cr.new_sub_path()
            cr.arc(tx + 4, ty + 8, 3.5, 0, 2 * math.pi)
            cr.set_source_rgba(*mascot.rgba(tint if busy else 'metal', alpha * (1 if busy else .6)))
            cr.fill()
            took = elapsed(now - member.since) if member.state == 'working' and member.since else ''
            if wide or quad:
                # Cuánto lleva, a la derecha del nombre; a medias no cabe y va debajo.
                took_w = self.put(cr, took, FONT_DETAIL, tx + tw, ty + 1, MUTED_COLOR, alpha, align=1) \
                    if took else 0
                self.put(cr, member.name, FONT_ROW, tx + 14, ty, name_color, alpha, tw - 22 - took_w)
            else:
                self.put(cr, member.name, FONT_ROW, tx + 14, ty, name_color, alpha, tw - 14)
                if took:
                    self.put(cr, took, FONT_DETAIL, tx + 14, ty + 19, MUTED_COLOR, alpha, tw - 14)
        if not busy:
            note = ('esperando' if s.delegating else 'en reposo') if role == MAIN_ROLE else 'libre'
            self.put(cr, note, FONT_DETAIL, x + cw / 2 if column else tx + 14, ty + 20, MUTED_COLOR,
                     alpha * .8, tw, .5 if column else 0)
            return
        if member.state == 'permission':
            # Lo que quiere hacer, entero: hay que leerlo antes de contestar.
            asks = s.ask is not None
            top = ty + 24 if wide or quad else y + 76 if not column else ty + 22
            room = y + ch - top - (BUTTON_H + 14 if asks else 8)
            self.put(cr, member.detail, FONT_DETAIL, sx, top, rgb(self.colors['arg']), alpha, sw,
                     markup=self.markup(member.detail), lines=max(1, int(room // 15)))
            if asks:
                bw = min(BUTTON_W, (cw - 24 - BUTTON_GAP) / 2)
                self.draw_buttons(cr, x + cw - 12, y + ch - 10, alpha, bw)
            return
        self.draw_steps(cr, member, sx, y + ch - 12, sw, 2 if quad else 4 if wide else 3,
                        19 if quad or column else 24, alpha)

    def draw_steps(self, cr, member, x, bottom, width, count, gap, alpha):
        """Los últimos pasos de uno, hacia arriba desde `bottom`: los de antes
        apagados y con palomita, el de ahora resaltado."""
        steps = [text for text, _at in member.steps[-count:]] or ['Arrancando…']
        marks = {'done': ('✓', 'green'), 'waiting': ('?', 'yellow')}
        for i, text in enumerate(steps):
            y = bottom - (len(steps) - i) * gap
            last = i == len(steps) - 1
            mark, color = marks.get(member.state, ('›', None)) if last else ('✓', None)
            ink = mascot.rgba(color)[:3] if color else (TITLE_COLOR if last else MUTED_COLOR)
            self.put(cr, mark, FONT_DETAIL, x, y, ink, alpha * (1 if last else .7))
            if last:
                self.put(cr, text, FONT_DETAIL, x + 16, y, TITLE_COLOR, alpha, width - 16,
                         markup=self.markup(text))
            else:
                self.put(cr, text, FONT_DETAIL, x + 16, y, MUTED_COLOR, alpha * .8, width - 16)

    def draw_bench(self, cr, s, members, x, y, w, h, alpha):
        """La banca: los que no trabajan, en chiquito."""
        self.panel(cr, x, y, w, h, alpha)
        step = h / len(members)
        for i, member in enumerate(members):
            cy = y + step * i + step / 2
            self.face(cr, member.role, 'idle', x + 26, cy + 1, 34, alpha * .4)
            self.put(cr, member.role, FONT_ROW, x + 48, cy - 15, MUTED_COLOR, alpha, w - 54)
            waits = member.role == MAIN_ROLE and s.delegating
            self.put(cr, 'esperando' if waits else 'libre', FONT_DETAIL, x + 48, cy + 1, MUTED_COLOR,
                     alpha * .7, w - 54)

    def draw_focus(self, cr, x, y, width, h, member, s, alpha, now):
        """El desglose de uno: a la izquierda quién es y cuánto lleva; en
        medio todos sus pasos y lo que tardó cada uno; a la derecha, los
        demás en miniatura. Un clic a la izquierda vuelve al tablero."""
        cw = width - FOCUS_MINIS
        role = member.role
        tint = MEMBER_TINT.get(member.state) or mascot.accent(role)
        self.panel(cr, x, y, cw, h, alpha, tint if member.busy else None)
        cx = x + FOCUS_SIDE / 2
        pet = MEMBER_PET.get(member.state, 'idle')
        self.face(cr, role, pet, cx, y + 64, 84, alpha, now, now - s.changed)
        self.put(cr, member.name, FONT_ROW, cx, y + 116, rgb(mascot.accent(role)), alpha,
                 FOCUS_SIDE - 12, .5)
        self.put(cr, self.tab_labels()[s.sid], FONT_DETAIL, cx, y + 134, MUTED_COLOR, alpha,
                 FOCUS_SIDE - 12, .5)
        n = len(member.steps)
        took = f' · {elapsed(now - member.since)}' if member.busy and member.since else ''
        self.put(cr, f'{n} paso{"" if n == 1 else "s"}{took}', FONT_DETAIL, cx, y + 156,
                 rgb(self.colors['arg']), alpha, FOCUS_SIDE - 12, .5)
        # Al pie, dos enlaces: al pane de la sesión y de vuelta al tablero.
        links = ([('jump', s.sid, 'ir al pane ›')] if s.pane else []) + [('back', None, '‹ volver')]
        for i, (kind, key, label) in enumerate(reversed(links)):
            ly = y + h - 32 - i * 24
            over = self.over(x + 8, ly, FOCUS_SIDE - 16, 22)
            self.put(cr, label, FONT_DETAIL, cx, ly + 4, TITLE_COLOR if over else MUTED_COLOR, alpha,
                     FOCUS_SIDE - 16, .5)
            self.hits.append((kind, key, x + 8, ly, FOCUS_SIDE - 16, 22))
        self.hits.append(('back', None, x, y, FOCUS_SIDE, h))
        # Los pasos: los últimos que caben, y arriba cuántos hubo antes.
        shown = member.steps[-FOCUS_STEPS:]
        hidden = n - len(shown)
        if hidden:
            shown = member.steps[-(FOCUS_STEPS - 1):]
            hidden = n - len(shown)
        left, right = x + FOCUS_SIDE + 8, x + cw - 14
        ty = y + 14
        if hidden:
            self.put(cr, f'⋯ {hidden} paso{"" if hidden == 1 else "s"} antes', FONT_DETAIL, left + 20, ty,
                     MUTED_COLOR, alpha * .8)
            ty += 26
        marks = {'done': ('✓', 'green'), 'waiting': ('?', 'yellow'), 'permission': ('›', 'red')}
        for i, (text, at) in enumerate(shown):
            last = i == len(shown) - 1
            if last:
                mascot.rrect(cr, left - 4, ty - 5, right - left + 8, 24, 8)
                cr.set_source_rgba(1, 1, 1, .07 * alpha)
                cr.fill()
                mark, color = marks.get(member.state, ('›', None))
                spent = 'ahora' if member.busy else ''
            else:
                mark, color = '✓', 'green'
                spent = elapsed(shown[i + 1][1] - at)
            ink = mascot.rgba(color)[:3] if color else TITLE_COLOR
            self.put(cr, mark, FONT_DETAIL, left + 2, ty, ink, alpha * (1 if last else .8))
            sw = self.put(cr, spent, FONT_DETAIL, right, ty, MUTED_COLOR, alpha, align=1) if spent else 0
            self.put(cr, text, FONT_DETAIL, left + 20, ty, TITLE_COLOR, alpha * (1 if last else .85),
                     right - sw - 12 - (left + 20), markup=self.markup(text))
            ty += 26
        # Los demás siguen a la vista; un clic en uno abre el suyo.
        others = [m for m in s.team() if m.role != role]
        mx = x + cw + FOCUS_MINIS / 2 + 2
        for i, other in enumerate(others):
            my = y + 30 + i * 40
            self.face(cr, other.role, MEMBER_PET.get(other.state, 'idle'), mx, my, 28,
                      alpha * (1 if other.busy else .35))
            if other.steps:
                self.hits.append(('member', (s.sid, other.role), mx - 16, my - 18, 32, 36))

    def draw_rows(self, cr, x0, w, top, alpha, rows, limit):
        """Una fila por alerta: su punto, de quién es y qué pasa."""
        left, right = x0 + 14, x0 + w - 14
        cr.set_source_rgba(1, 1, 1, .08 * alpha)
        cr.rectangle(left + 4, top - 1, right - left - 8, 1)
        cr.fill()
        # Si no caben todas, la última fila dice cuántas faltan.
        shown = rows if len(rows) <= limit else rows[:limit - 1]
        if len(rows) > len(shown):
            more = self._layout(cr, f'y {len(rows) - len(shown)} más', FONT_DETAIL)
            y = top + 3 + len(shown) * ROW_H
            cr.move_to(left + 28, y + (ROW_H - more.get_pixel_size()[1]) / 2)
            cr.set_source_rgba(*MUTED_COLOR[:3], alpha)
            PangoCairo.show_layout(cr, more)
        for i, s in enumerate(shown):
            y = top + 3 + i * ROW_H
            self.rows.append((s, y, ROW_H))
            # La que tiene la ficha abierta se queda marcada.
            if self.over(left, y, right - left, ROW_H - 1) or (s.card and s is self.view.session):
                mascot.rrect(cr, left, y + 1, right - left, ROW_H - 2, 8)
                cr.set_source_rgba(1, 1, 1, .07 * alpha)
                cr.fill()
            cr.new_sub_path()
            color = dot_color(s)
            if color:
                cr.arc(left + 14, y + ROW_H / 2, 3.5, 0, 2 * math.pi)
                cr.set_source_rgba(*mascot.rgba(color, alpha))
                cr.fill()
            else:
                # En reposo va hueco: con un acento apagado, un punto gris
                # relleno se confundiría con el de "trabajando".
                cr.arc(left + 14, y + ROW_H / 2, 3, 0, 2 * math.pi)
                cr.set_source_rgba(*mascot.rgba('metal', .7 * alpha))
                cr.set_line_width(1.5)
                cr.stroke()
            name = self._layout(cr, s.proj, FONT_ROW, ROW_NAME_W)
            cr.move_to(left + 28, y + (ROW_H - name.get_pixel_size()[1]) / 2)
            cr.set_source_rgba(*TITLE_COLOR[:3], alpha)
            PangoCairo.show_layout(cr, name)
            dx = left + 28 + ROW_NAME_W + 10
            end = right - 10
            if s.detail:
                detail = self._layout(cr, s.detail, FONT_DETAIL, end - dx, markup=self.markup(s.detail))
            else:
                detail = self._layout(cr, f'En reposo {ago(time.monotonic() - s.updated)}',
                                      FONT_DETAIL, end - dx)
            cr.move_to(dx, y + (ROW_H - detail.get_pixel_size()[1]) / 2)
            # "En reposo…" va con el color claro del tema: con un gris se
            # perdía, sobre todo en modo vidrio sobre una ventana clara.
            cr.set_source_rgba(*rgb(self.colors['arg']), alpha)
            self._show(cr, detail, alpha)

    def draw_preview(self, cr, x0, w, top, height, alpha):
        """El fragmento que se está editando, como un diff de pocas líneas."""
        p = self.preview()
        left, right = x0 + 14, x0 + w - 14
        mascot.rrect(cr, left, top + 2, right - left, height - 6, 10)
        cr.set_source_rgba(1, 1, 1, .05 * alpha)
        cr.fill()
        tx, y = left + 12, top + PREVIEW_PAD
        # Arriba: el archivo y la línea a la izquierda, lo que cambia a la derecha.
        end = right - 12
        for text, color in ((f'−{p.removed}', paint.RED), (f'+{p.added}', self.colors['ok'])):
            note = self._layout(cr, text, FONT_CODE)
            end -= note.get_pixel_size()[0]
            cr.move_to(end, y + 2)
            cr.set_source_rgba(*rgb(color), alpha)
            PangoCairo.show_layout(cr, note)
            end -= 8
        where = p.name + (f':{p.line}' if p.line else '')
        if p.edits > 1:
            where += f'  ·  1 de {p.edits} cambios'
        name = self._layout(cr, where, FONT_CODE, end - tx)
        cr.move_to(tx, y + 2)
        cr.set_source_rgba(*rgb(self.colors['path']), alpha)
        PangoCairo.show_layout(cr, name)
        y = top + PREVIEW_PAD + PREVIEW_HEAD
        tint = {'+': self.colors['ok'], '-': paint.RED}
        ink = {'+': self.colors['arg'], '-': self.colors['text'], ' ': self.colors['dim']}
        lines = p.lines + ([(' ', f'⋯ {p.more} líneas más')] if p.more else [])
        for mark, text in lines:
            if mark in tint:
                cr.rectangle(left + 4, y, right - left - 8, CODE_LINE_H)
                cr.set_source_rgba(*rgb(tint[mark]), .14 * alpha)
                cr.fill()
                sign = self._layout(cr, mark, FONT_CODE)
                cr.move_to(tx, y + 1)
                cr.set_source_rgba(*rgb(tint[mark]), alpha)
                PangoCairo.show_layout(cr, sign)
            code = self._layout(cr, text, FONT_CODE, right - 12 - (tx + 14))
            cr.move_to(tx + 14, y + 1)
            cr.set_source_rgba(*rgb(ink[mark]), alpha)
            PangoCairo.show_layout(cr, code)
            y += CODE_LINE_H

    def draw_card(self, cr, x0, w, top, height, alpha):
        """La ficha de una alerta: su detalle y, debajo, sus botones."""
        s = self.view.session
        self.card_span = (top, top + height)
        left, right = x0 + 14, x0 + w - 14
        body = height - CARD_BUTTONS
        if body:
            mascot.rrect(cr, left, top + 2, right - left, body - 6, 10)
            cr.set_source_rgba(1, 1, 1, .05 * alpha)
            cr.fill()
            tx, y = left + 12, top + PREVIEW_PAD
            if s.where or s.note:
                # Arriba: de dónde sale a la izquierda, la nota a la derecha.
                end = right - 12
                if s.note:
                    note = self._layout(cr, s.note, FONT_CODE)
                    end -= note.get_pixel_size()[0]
                    cr.move_to(end, y + 2)
                    cr.set_source_rgba(*rgb(self.colors['dim']), alpha)
                    PangoCairo.show_layout(cr, note)
                    end -= 12
                where = self._layout(cr, s.where, FONT_CODE, end - tx)
                cr.move_to(tx, y + 2)
                cr.set_source_rgba(*rgb(self.colors['path']), alpha)
                PangoCairo.show_layout(cr, where)
                y += PREVIEW_HEAD
            for text in s.lines:
                mark, role, lx = MARK_COLORS.get(text[:1]) if text[1:2] == ' ' else None, 'text', tx
                if mark:
                    # La marca de una prueba, en su color; el nombre, a su lado.
                    sign = self._layout(cr, text[0], FONT_CODE)
                    cr.move_to(tx, y + 1)
                    cr.set_source_rgba(*mascot.rgba(mark[0], alpha))
                    PangoCairo.show_layout(cr, sign)
                    text, role, lx = text[2:], mark[1], tx + 14
                line = self._layout(cr, text, FONT_CODE, right - 12 - lx)
                cr.move_to(lx, y + 1)
                cr.set_source_rgba(*rgb(self.colors[role]), alpha)
                PangoCairo.show_layout(cr, line)
                y += CODE_LINE_H
        # Los botones, de derecha a izquierda: el último de la alerta es el
        # principal y Descartar queda al otro extremo.
        x = x0 + w - 18
        y = top + body + (CARD_BUTTONS - BUTTON_H) / 2 - 2
        buttons = [('dismiss', 'Descartar')] + [(i, a['label']) for i, a in enumerate(s.actions)]
        for n, (key, label) in enumerate(reversed(buttons)):
            x -= BUTTON_W
            self.draw_button(cr, key, label, x, y, n == 0 and key != 'dismiss', alpha)
            x -= BUTTON_GAP

    def draw_pills(self, cr, x0, w, bottom, alpha):
        """Una pastilla por fuente, pegadas al borde de abajo, y al final la
        de los atajos de elyares-engineer."""
        left, right = x0 + 18, x0 + w - 18
        top = bottom - PILLS_H
        cr.set_source_rgba(1, 1, 1, .08 * alpha)
        cr.rectangle(left, top, right - left, 1)
        cr.fill()
        px, py = self.pointer or (-1, -1)
        x, y = left, top + (PILLS_H - PILL_H) / 2 + 1
        for key, label in sources.SOURCES:
            state = self.source_state(key)
            layout = self._layout(cr, label, FONT_PILL)
            lw, lh = layout.get_pixel_size()
            pw = lw + PILL_PAD
            over = x <= px <= x + pw and y <= py <= y + PILL_H
            mascot.rrect(cr, x, y, pw, PILL_H, PILL_H / 2)
            cr.set_source_rgba(1, 1, 1, (.13 if over else .07) * alpha)
            cr.fill()
            cr.new_sub_path()
            if state == 'off':
                # Apagada va hueca, como una sesión en reposo.
                cr.arc(x + 10, y + PILL_H / 2, 2.5, 0, 2 * math.pi)
                cr.set_source_rgba(*mascot.rgba('metal', .6 * alpha))
                cr.set_line_width(1.3)
                cr.stroke()
            else:
                color = {'on': 'green', 'bad': 'red'}.get(state, 'metal')
                cr.arc(x + 10, y + PILL_H / 2, 3, 0, 2 * math.pi)
                cr.set_source_rgba(*mascot.rgba(color, alpha))
                cr.fill()
            cr.move_to(x + 17, y + (PILL_H - lh) / 2)
            cr.set_source_rgba(*(MUTED_COLOR if state == 'off' else TITLE_COLOR)[:3], alpha)
            PangoCairo.show_layout(cr, layout)
            self.pills.append((key, x, y, pw, PILL_H))
            if over:
                self.tip = (key, x + pw / 2, alpha)
            x += pw + PILL_GAP
        # La de los atajos no es una fuente: va sin punto, al otro extremo.
        layout = self._layout(cr, '?', FONT_PILL)
        lw, lh = layout.get_pixel_size()
        pw = lw + 16
        x = right - pw
        over = x <= px <= x + pw and y <= py <= y + PILL_H
        mascot.rrect(cr, x, y, pw, PILL_H, PILL_H / 2)
        cr.set_source_rgba(1, 1, 1, (.13 if over else .07) * alpha)
        cr.fill()
        cr.move_to(x + (pw - lw) / 2, y + (PILL_H - lh) / 2)
        cr.set_source_rgba(*TITLE_COLOR[:3], alpha)
        PangoCairo.show_layout(cr, layout)
        self.pills.append((commands.HELP, x, y, pw, PILL_H))
        if over:
            self.tip = (commands.HELP, x + pw / 2, alpha)

    def draw_tip(self, cr, width, top, now):
        """La burbuja de una pastilla: sale debajo de la isla mientras el
        cursor está sobre ella, sin clic. Arriba, cómo está la fuente; debajo,
        sus comandos en dos columnas."""
        key, cx, alpha = self.tip
        if key != self.tip_key:
            self.tip_key, self.tip_since = key, now
            # Los comandos se leen al salir la burbuja: un cambio en el archivo
            # o en los atajos de Hyprland se ve sin reiniciar nada.
            self.tip_ref = commands.reference(
                key, commands.load(), hypr.binds() if key == commands.HELP else None)
        alpha *= clamp((now - self.tip_since) / TIP_FADE)
        title, rows = self.source_tip(key)
        room = width - 8 - 2 * TIP_PAD          # lo más ancha que puede ser por dentro
        inner = TIP_W - 2 * TIP_PAD
        cmds = [self._layout(cr, row[1], FONT_DETAIL) for row in rows if row[0] == 'cmd']
        col = max((layout.get_pixel_size()[0] for layout in cmds), default=0) + TIP_COL_GAP
        # Cada fila: (lo que se pinta a la izquierda, color, lo de la derecha, aire arriba).
        drawn = [(self._layout(cr, title, FONT_ROW, inner), TITLE_COLOR[:3], None, 0)]
        cmds = iter(cmds)
        for row in rows:
            if row[0] == 'text':
                # Una causa o un resumen largo se parte en dos líneas antes que cortarse.
                drawn.append((self._layout(cr, row[1], FONT_DETAIL, inner, 2), row[2], None, 0))
            elif row[0] == 'head':
                drawn.append((self._layout(cr, row[1].upper(), FONT_PILL), MUTED_COLOR[:3], None,
                              TIP_HEAD_GAP))
            else:
                what = self._layout(cr, row[2], FONT_DETAIL, room - col)
                drawn.append((next(cmds), rgb(self.colors['cmd']), what, 0))
        # Lo que ocupa cada fila hacia abajo: los comandos van más juntos.
        steps = [gap + layout.get_pixel_size()[1] + (1 if what else 3)
                 for layout, _, what, gap in drawn]
        while sum(steps) + 2 * TIP_PAD > TIP_ROOM - TIP_GAP and len(drawn) > 2:
            # Más comandos de los que caben en la ventana: se dice que hay más.
            drawn[-2:] = [(self._layout(cr, '…', FONT_DETAIL), MUTED_COLOR[:3], None, 0)]
            steps[-2:] = [drawn[-1][0].get_pixel_size()[1] + 3]
        w = max([layout.get_pixel_size()[0] for layout, *_ in drawn]
                + [col + what.get_pixel_size()[0] for _, _, what, _ in drawn if what]) + 2 * TIP_PAD
        h = sum(steps) - 3 + 2 * TIP_PAD
        x, y = clamp(cx - w / 2, 4, width - w - 4), top + TIP_GAP
        self.tip_size = (w, h)
        glass = self.settings['glass']
        mascot.rrect(cr, x, y, w, h, 12)
        # Con comandos se lee más rato: en vidrio va más opaca que la isla.
        cr.set_source_rgba(*ISLAND_BG[:3], (TIP_GLASS_ALPHA if glass else ISLAND_BG[3]) * alpha)
        if glass:
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, GLASS_EDGE * alpha)
            cr.set_line_width(1)
            cr.stroke()
        else:
            cr.fill()
        ty = y + TIP_PAD
        for (layout, color, what, gap), step in zip(drawn, steps):
            cr.move_to(x + TIP_PAD, ty + gap)
            cr.set_source_rgba(*color, alpha)
            PangoCairo.show_layout(cr, layout)
            if what:
                cr.move_to(x + TIP_PAD + col, ty + gap)
                cr.set_source_rgba(*rgb(self.colors['text']), alpha)
                PangoCairo.show_layout(cr, what)
            ty += step

    def draw_buttons(self, cr, right, bottom, alpha, bw=BUTTON_W):
        y = bottom - BUTTON_H
        self.draw_button(cr, 'allow', 'Permitir', right - bw, y, True, alpha, bw)
        self.draw_button(cr, 'deny', 'Denegar', right - 2 * bw - BUTTON_GAP, y, False, alpha, bw)

    def draw_button(self, cr, key, label, x, y, primary, alpha, bw=BUTTON_W):
        """Un botón de la isla. El principal va relleno; los demás, apenas marcados."""
        bg, fg, fill = (ALLOW_BG, ALLOW_FG, .92) if primary else (DENY_BG, DENY_FG, .10)
        self.buttons[key] = (x, y, bw, BUTTON_H)
        over = self.over(x, y, bw, BUTTON_H)
        r = BUTTON_H / 2
        cr.new_sub_path()
        cr.arc(x + r, y + r, r, math.pi / 2, 3 * math.pi / 2)
        cr.arc(x + bw - r, y + r, r, -math.pi / 2, math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(*bg, min(1, fill + (.08 if over else 0)) * alpha)
        cr.fill()
        layout = self._layout(cr, label, FONT_BUTTON, bw - 12)
        lw, lh = layout.get_pixel_size()
        cr.move_to(x + (bw - lw) / 2, y + (BUTTON_H - lh) / 2)
        cr.set_source_rgba(*fg, alpha)
        PangoCairo.show_layout(cr, layout)

    @staticmethod
    def _shape(layout, font, width=None, lines=1):
        """Fuente, ancho y corte de un texto. Con lines > 1 se parte en líneas y
        solo lleva "…" si ni así cabe."""
        layout.set_font_description(Pango.FontDescription.from_string(font))
        if width:
            layout.set_width(int(max(10, width) * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            if lines > 1:
                layout.set_wrap(Pango.WrapMode.WORD_CHAR)
                layout.set_height(-lines)
        return layout

    @classmethod
    def _layout(cls, cr, text, font, width=None, lines=1, markup=None):
        layout = PangoCairo.create_layout(cr)
        if markup:
            layout.set_markup(markup, -1)
        else:
            layout.set_text(text or '', -1)
        return cls._shape(layout, font, width, lines)

    @staticmethod
    def _show(cr, layout, alpha):
        """Pinta un texto con colores propios. Pango ignora la transparencia del
        pincel para un trozo que trae su color, así que mientras la isla se
        abre o se cierra el texto pasa por una capa intermedia."""
        if alpha >= 1:
            PangoCairo.show_layout(cr, layout)
            return
        x, y = cr.get_current_point()
        cr.push_group()
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)
        cr.pop_group_to_source()
        cr.paint_with_alpha(alpha)

    # ── clics ────────────────────────────────────────────────────────────────

    def on_click(self, _gesture, _n, x, y):
        x0, w, h = self.island_rect(self.da.get_width())
        if not (x0 <= x <= x0 + w and y <= max(h, HOVER_STRIP)):
            return
        if self.settings['compact'] and self.target() == 'petit':
            self.expand()
            return
        for key, (bx, by, bw, bh) in self.buttons.items():
            if not (bx <= x <= bx + bw and by <= y <= by + bh):
                continue
            if key in ('allow', 'deny'):
                asking = self.asking()
                if asking is None:
                    continue
                self.model.decide(asking, key == 'allow')
                self.refresh()
            else:
                self.act(self.view.session, key)
            return
        if self.card_span and self.card_span[0] <= y < self.card_span[1]:
            # En la ficha solo cuentan sus botones: un clic que falla uno no
            # debe abrir el navegador y descartar la alerta.
            return
        for key, bx, by, bw, bh in self.pills:
            if bx <= x <= bx + bw and by <= y <= by + bh:
                # Claude no se apaga desde aquí: sin sus hooks no hay nada que mostrar.
                # Y la de los atajos no es una fuente.
                if key in sources.PREFIXES:
                    self.toggle_source(key)
                return
        for s, ry, rh in self.rows:
            if ry <= y < ry + rh:
                if s.card:
                    # Una alerta con ficha no se va con el clic: sube a la
                    # cabecera, donde se leen su detalle y sus botones.
                    self.pin = s.sid
                    self.refresh()
                    self.ensure_tick()
                else:
                    self.go(s)
                return
        for kind, key, hx, hy, hw, hh in self.hits:
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                self.on_hit(kind, key)
                return
        if self.target() == 'board' or (self.rows and y > self.rows[0][1]):
            return
        if x < x0 + 12 + PET + 4:
            self.poke()
        elif self.view.session:
            self.go(self.view.session)

    def on_hit(self, kind, key):
        """Un clic en el tablero: en una pestaña, en uno de los cuatro o en
        los enlaces de un desglose."""
        if kind == 'tab':
            if key == self.tab:
                # La elegida ya se ve: el clic lleva a su pane, como antes el de la cabecera.
                s = self.tab_session()
                if s is not None:
                    self.go(s)
                return
            self.tab, self.focus = key, None
        elif kind == 'member':
            self.focus = key
        elif kind == 'back':
            self.focus = None
        elif kind == 'jump':
            s = self.model.sessions.get(key)
            if s is not None:
                self.go(s)
            return
        self.ensure_tick()

    def go(self, s):
        """Clic en una sesión: salta a su pane. En una alerta abre su URL y la descarta."""
        self.collapse()
        if s.state == 'alert':
            self.model.dismiss(s)
            self.refresh()
        threading.Thread(target=actions.jump, args=(s,), daemon=True).start()

    def act(self, s, key):
        """Un botón de la ficha de una alerta: Descartar, o uno de los suyos."""
        if s is None or not s.card:
            return
        if key == 'dismiss':
            self.model.dismiss(s)
        elif isinstance(key, int) and key < len(s.actions):
            action = s.actions[key]
            if action.get('jump'):
                self.collapse()
                threading.Thread(target=actions.jump, args=(s,), daemon=True).start()
            else:
                threading.Thread(target=actions.run, args=(action,), daemon=True).start()
            if action.get('after'):
                self.model.dismiss(s, cooldown=action['after'] == 'dismiss')
        self.refresh()
        self.ensure_tick()

    def on_middle_click(self, _gesture, _n, x, y):
        x0, w, h = self.island_rect(self.da.get_width())
        if x0 <= x <= x0 + w and y <= max(h, HOVER_STRIP):
            self.toggle_pinned()

    def on_right_click(self, _gesture, _n, x, y):
        x0, w, h = self.island_rect(self.da.get_width())
        if not (x0 <= x <= x0 + w and y <= max(h, HOVER_STRIP)):
            return
        self.toggle_compact()


def main(argv):
    # gtk4-layer-shell ya está cargada (la precarga bin/elyares-engineer): que
    # no la hereden los programas que lanza elyares-engineer. Firefox es GTK 3 y
    # aborta al arrancar con una biblioteca de GTK 4 dentro.
    preload = [lib for lib in os.environ.get('LD_PRELOAD', '').split(':')
               if lib and 'gtk4-layer-shell' not in lib]
    if preload:
        os.environ['LD_PRELOAD'] = ':'.join(preload)
    else:
        os.environ.pop('LD_PRELOAD', None)
    app = Gtk.Application(application_id='dev.elyares.Engineer')

    def activate(app):
        if not getattr(app, 'island', None):
            app.island = Island(app)

    app.connect('activate', activate)
    return app.run(argv[:1])
