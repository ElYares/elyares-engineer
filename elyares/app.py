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
pastilla sale debajo de la isla una burbuja (un popover, con la flecha hacia
la pastilla) con lo que se sabe de esa fuente y, para consultar, sus
comandos (`commands.py`). Al final de la franja, la
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
según cuántos trabajen, y con todos son dos filas de cuadros. Un clic en uno
abre su desglose: todos sus pasos y lo que tardó cada uno. El de cualquiera
menos el engineer trae un mini chat para encargarle algo, y lo que hace se ve
en su tarjeta de esa misma pestaña (`team`, `chatview`). Un clic en la
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
import subprocess
import sys
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

from . import (actions, chatview, coffe, commands, devherd, fonts, github, hypr, ipc, mascot, paint,  # noqa: E402
               preview, projectview, settings, sources, state, store, testrun, theme, themes, windowframe, windowview, workflowview)
from .state import MAIN_ROLE, Member, Model, elapsed  # noqa: E402

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
REPLY_CHIPS_H = 24    # la fila con las respuestas de los agentes, cuando hay más de una
REPLY_LINES = 8       # líneas de una respuesta que caben en su ficha
TIP_W, TIP_PAD, TIP_GAP = 400, 14, 14  # la burbuja de una fuente, debajo de la isla; en el hueco va su flecha
TIP_ROOM = 440        # el alto que se le reserva en la ventana
TIP_COL_GAP = 16      # entre un comando y lo que hace
TIP_HEAD_GAP = 15     # aire sobre el título de un bloque de comandos, con una raya en medio
TIP_LINES = 3         # líneas propias que puede traer una fuente
CHAT_PILL = 'chat'    # la pastilla del pie que abre el chat
# `elyares-ctl move`: la isla se corre a lo ancho de la pantalla, pegada arriba.
# Su sitio de siempre es el centro; `left` y `right` la llevan al siguiente de
# estos sitios, en % del ancho.
CENTER = 50
SLOTS = (0, 25, CENTER, 75, 100)
STEP_Y = 80           # `move up` y `move down`: lo que sube o baja, en px
DRAG_MASK = Gdk.ModifierType.ALT_MASK    # arrastrar la isla con Alt (SUPER lo usa Hyprland para mover ventanas)
DRAG_SLOP = 6                            # lo que hay que mover el botón del medio para que sea arrastre y no clic
# `elyares-ctl reload`: la isla se vuelve a arrancar con el código de su carpeta.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, 'bin', 'elyares-engineer')
UNIT = 'elyares-engineer.service'
MONITORS_SETTLE_MS = 600    # tras conectar o desconectar una pantalla: lo que tarda Hyprland en acomodarlas
RELOAD_MS = 1200      # lo que espera tras el último turno: que llegue su aviso y su cuenta de contexto
# `elyares-ctl chat <quién>`: el chat de ese de la familia.
AGENT_NAMES = {role: ('' if role == 'engineer' else name) for role, name in state.ROLE_AGENTS.items()}
TIP_ITEMS = 5         # cosas que nombra una por una (los PRs de GitHub); de las demás dice cuántas
TIP_ITEM_DOT = 14     # sitio para el punto de cada una
TIP_ITEM_GAP = 7      # entre una y otra
# El color del punto y de la nota de cada una, por su tono.
TIP_ITEM_ROLES = {'ok': 'pass', 'bad': 'bad', 'run': 'pct2', 'info': 'head'}
TIP_R = 14            # lo redondo de sus esquinas: un popover de macOS
TIP_TAIL = 13         # medio ancho de la flecha, donde nace de la burbuja
TIP_TAIL_GAP = 2      # entre la punta de la flecha y el borde de la isla
TIP_IN, TIP_OUT = .2, .14     # segundos que tarda en salir y en irse
TIP_SWAP = .55        # de una pastilla a la de al lado no vuelve a salir de cero
TIP_GLIDE = 16        # qué tan rápido se desliza hasta la otra pastilla (1/s)
TIP_SMALL = .92       # el tamaño con el que nace, desde la punta de la flecha
TIP_BACK = 1.1        # cuánto se pasa de su tamaño antes de asentarse: apenas
TIP_EDGE = (.26, .07) # su filo: claro arriba, donde le da la luz, y casi nada abajo
TIP_SHEEN = .07       # en vidrio, el brillo que baja desde arriba hasta la mitad
# Sus colores son los del tema, avivados: sobre vidrio, tal cual se pierden.
# Cuánto más saturados, y lo claro que va lo principal y lo secundario.
TIP_VIVID, TIP_LIGHT, TIP_SOFT = 2.2, .76, .68
TIP_FIXED = ('pass', 'bad', 'pct2', 'pct3')   # los de aviso no son del tema: van como son
TIP_INK_SHADOW = .6   # en vidrio, la sombra de cada texto: lo despega de lo que haya detrás
# Las etiquetas de la burbuja (cómo está la fuente y lo que se sabe de ella):
# cápsulas teñidas de su color. Relleno a los lados y arriba, hueco entre
# ellas, sitio para el punto de la primera, y lo que tiñen el fondo y el filo.
TIP_CHIP_PAD, TIP_CHIP_PAD_Y, TIP_CHIP_GAP, TIP_CHIP_DOT = 8, 3, 6, 10
TIP_CHIP_FILL, TIP_CHIP_EDGE = .16, .38
# Las fichas de sus cifras: cuántas por fila, relleno, hueco, lo redondo de
# sus esquinas y lo que tiñen. Cada una va en un color de la paleta, por turno.
TIP_STATS_ROW, TIP_STAT_PAD, TIP_STAT_GAP, TIP_STAT_R = 3, 9, 7, 10
TIP_STAT_FILL, TIP_STAT_EDGE = .11, .26
TIP_STAT_ROLES = ('cmd', 'path', 'flag', 'num')
TIP_TEXT_LINES = 3    # líneas en las que se parte una frase larga antes de cortarse
# Los bloques de la burbuja de los atajos que no son comandos: van de un solo color.
TIP_PLAIN = {'Teclado': 'var', 'Ratón': 'str'}
TIP_RULE = .09        # la raya que separa un bloque de comandos de lo de arriba
# La sombra: cuánto se abre, cuánto cae y lo que oscurece cada capa. Entre
# todas no pasan de .20: es el `ignore_alpha` de la regla de Hyprland, y por
# debajo de él la sombra no desenfoca lo que tiene detrás.
TIP_SHADOW, TIP_SHADOW_DROP, TIP_SHADOW_ALPHA = 14, 5, .013
# 8: margen del rebote
# El tablero: una pestaña por sesión y, dentro, sus cuatro.
BOARD_W = PREVIEW_W
TABS_H = 34
BOARD_H = 172         # el frente (los que trabajan) y la banca (los libres)
BOARD_PAD, BOARD_GAP = 10, 8
BENCH_W = 132
ROW_MOST = 6          # los que caben libres en una sola fila, con su nombre entero
BENCH_ROWS = 5        # los que caben en la banca uno debajo de otro; más, van en cuadrícula
FOCUS_H = 236         # el desglose de uno, con sus pasos
FOCUS_STEPS = 8
FOCUS_SIDE, FOCUS_MINIS = 150, 34   # a la izquierda, quién es; a la derecha, los demás
ALERT_ROWS = 3        # filas de alertas que caben debajo del tablero
MINI, MAX_MINIS = 24, 4             # las caritas de los demás, con la isla asomada
WIN_W = PREVIEW_W + 40
# Lo más alto que se puede dibujar, con la cabecera de siempre o con el tablero.
HEAD_MAX = OPEN_H + MAX_EXTRA + PREVIEW_MAX + ASK_TALL + MAX_ROWS * ROW_H + LIST_PAD
BOARD_MAX = (TABS_H + max(BOARD_H + PREVIEW_MAX, FOCUS_H + chatview.MINI_H) + BOARD_PAD
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
WIN_GLASS_ALPHA = .5                 # la ventana de la app, en vidrio (igual que la isla suelta)
TIP_GLASS_ALPHA = .7                 # la burbuja, en vidrio: más opaca que la isla, que se lee más rato
TITLE_COLOR = (.95, .96, 1, 1)
MUTED_NORMAL = (.44, .49, .63, 1)
MUTED_TIRED = (.78, .82, .92, 1)         # vista cansada: el gris apagado, mucho más claro
MUTED_COLOR = MUTED_NORMAL
# La barra entre el agente y el proyecto, en el mismo gris.
SEP_COLOR = '#%02x%02x%02x' % tuple(round(c * 255) for c in MUTED_NORMAL[:3])
FONT_TITLE = 'Sans Semi-Bold 11'
FONT_DETAIL = 'JetBrainsMono Nerd Font 9'
FONT_BUTTON = 'Sans Semi-Bold 10'
FONT_ROW = 'Sans Semi-Bold 10'
FONT_PILL = 'Sans Semi-Bold 8'
FONT_CODE = 'JetBrainsMono Nerd Font 8'
FONT_TIP = 'JetBrainsMono Nerd Font Medium 9'    # la burbuja: un punto más gruesa, que va sobre vidrio
FONT_STAT = 'Sans Bold 15'         # la cifra de una ficha de la burbuja
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


class Island(chatview.ChatView, projectview.ProjectView, workflowview.WorkflowView, windowview.WindowView):
    def __init__(self, app):
        self.gtk_app = app              # la ventana de los flujos se crea con ella, la primera vez que se abre
        self.model = Model()
        self.model.restore(store.load())
        store.forget_usage()
        self.saved = self.model.dump()
        self.view = self.model.view()
        self.key_since = time.monotonic()   # desde cuándo la cabecera muestra lo que muestra
        self.title, self.detail = '', ''
        self.agent_name, self.role = '', MAIN_ROLE   # de quién es la cabecera
        self.tab = ''                   # la sesión de la pestaña elegida en el tablero
        self.tab_manual = False         # esa pestaña la elegiste tú: no se mueve sola, salvo por un permiso
        self.focus = None               # (sesión, personaje) del desglose abierto
        self.hits = []                  # (qué, cuál, x, y, ancho, alto) del tablero, del último dibujo
        self.dnd = False
        self.hover = False
        self.settings = settings.load()
        fonts.use(self.settings['font'])
        themes.use(self.settings['theme'])
        self.set_tired(self.settings['tired_eyes'])
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
        self.monitors_id = 0            # el reloj que la devuelve a su pantalla tras conectar o desconectar una
        self.screen_h = 0               # el alto de la pantalla en la que está
        self.screen_w = 0               # el ancho de la pantalla en la que está
        # 'allow'/'deny' del permiso, o 'dismiss' y el índice de cada botón de
        # la ficha de una alerta -> (x, y, w, h), del último dibujo
        self.buttons = {}
        self.card_span = None           # (arriba, abajo) de la ficha, del último dibujo
        self.pin = ''                   # la alerta que se eligió en la lista para leerla
        self.reply_pick = ''            # la respuesta de un agente que se está leyendo en el tablero
        self.rows = []                  # (sesión, y, alto) de la lista, del último dibujo
        self.list_layout = False        # la cabecera se queda arriba mientras hay lista
        self.wrap = (None, 0)           # (detalle, alto de más que pide entero)
        self.pills = []                 # (fuente, x, y, ancho, alto), del último dibujo
        self.projects_init()
        self.chat_init()
        self.chat_restore(store.load_chats())
        self.workflows_init()
        self.window_init()
        self.island_w, self.island_h = WIN_W, WIN_H     # lo que mide la capa, para devolvérselo al cerrar la ventana
        self.reloading = False          # se pidió volver a arrancar: en cuanto no haya turnos en curso
        self.tip = None                 # (fuente, centro, opacidad) de la pastilla bajo el cursor
        self.tip_key = None
        self.tip_ref = []               # los comandos de la burbuja que se está viendo
        self.tip_last = None            # la última burbuja a la vista: con ella se va
        self.tip_pop, self.tip_at = 0.0, 0.0   # cuánto ha salido (0 a 1) y cuándo se dibujó
        self.tip_cx = None              # dónde va su flecha: se desliza de una pastilla a otra
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
        self.monitor = self.start_monitor()
        if self.settings['pinned'] and self.monitor and not self.settings['pinned_monitor']:
            # Fijada de antes de que se guardara el monitor: se queda en este.
            self.settings['pinned_monitor'] = self.monitor['name']
            settings.save(self.settings)

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
        win.connect('notify::is-active', self.on_focus_change)
        if self.monitor:
            self._set_monitor(self.monitor['name'])
        if not self.screen_w:
            # Sin Hyprland que diga cuál es: el ancho de la primera pantalla.
            first = Gdk.Display.get_default().get_monitors().get_item(0)
            self.screen_w = first.get_geometry().width if first is not None else 0
            self.screen_h = first.get_geometry().height if first is not None else 0
        self.place()

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
        middle.connect('released', self.on_middle_click)       # al soltar: si se arrastró, no es un clic
        da.add_controller(middle)
        for button in (Gdk.BUTTON_PRIMARY, Gdk.BUTTON_MIDDLE):
            drag = Gtk.GestureDrag(button=button)
            drag.connect('drag-begin', self.on_drag_begin)
            drag.connect('drag-update', self.on_drag_update)
            drag.connect('drag-end', self.on_drag_end)
            da.add_controller(drag)
        # La caja de texto del chat va encima del dibujo.
        overlay = Gtk.Overlay()
        overlay.set_child(da)
        win.set_child(overlay)
        self.overlay = overlay
        self.da = da
        self.chat_widgets(overlay)

        css = Gtk.CssProvider()
        css.load_from_string('window, window.background { background: transparent; }')
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        win.present()
        self.update_region()
        if self.settings.get('window'):
            # Estaba en ventana al recargarse (o al apagarse): vuelve a estarlo.
            GLib.idle_add(lambda: self.open_window() or GLib.SOURCE_REMOVE)

        ipc.serve(lambda msg, req: GLib.idle_add(self.on_socket, msg, req),
                  lambda req: GLib.idle_add(self.on_gone, req))
        hypr.listen(lambda name: GLib.idle_add(self.on_focused_monitor, name))
        Gdk.Display.get_default().get_monitors().connect('items-changed', self.on_monitors_changed)
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
        (unas líneas con cómo están las cosas), `items` (las cosas que nombra
        una por una: {where, number, title, who, note, tone}) y, si no
        responde, `why` y `fix`. Con `polled` avisa de que acaba de consultar.
        """
        name, now = msg.get('name'), time.monotonic()
        if name not in sources.LABELS:
            return False
        old = self.sources.get(name) or {}
        ok = msg.get('ok')
        tip = msg.get('tip') if isinstance(msg.get('tip'), list) else []
        items = msg.get('items') if isinstance(msg.get('items'), list) else []
        self.sources[name] = {
            'items': [it for it in items if isinstance(it, dict) and isinstance(it.get('where'), str)],
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
        self.chat_tick(time.monotonic())
        self.projects_tick(self.seconds)
        self.workflows_tick()
        if self.seconds % REAP_SECS == 0:
            # Las sesiones sin pane (las de segundo plano) no tienen otra
            # forma de irse si se cierran sin avisar. Las de un chat se quedan:
            # su proceso duerme o se cierra con la isla, pero la conversación sigue.
            self.model.reap(actions.proc_alive, keep={c.session for c in self.all_chats() if c.session})
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
            # Sin nada: si estás en un proyecto en tmux, se ofrece empezar ahí.
            self.title, self.agent_name = 'Sin sesiones', ''
            self.detail = self.start_text() or 'Nada corriendo ahora'
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

    @staticmethod
    def set_tired(on):
        """Vista cansada: letra más grande y grises más claros, en la isla y la ventana."""
        global MUTED_COLOR, PILL_PAD, PILL_GAP
        on = fonts.use_tired(on)
        MUTED_COLOR = MUTED_TIRED if on else MUTED_NORMAL
        PILL_PAD, PILL_GAP = (18, 3) if on else (22, 5)

    def load_theme(self):
        """Fondo, grises, acento de la mascota y colores del texto, del tema elegido."""
        global ISLAND_BG, TITLE_COLOR, MUTED_NORMAL, MUTED_TIRED, MUTED_COLOR, SEP_COLOR
        look = themes.get()
        ISLAND_BG = (*themes.tuple_of(look['island']), ISLAND_BG[3])
        TITLE_COLOR = (*themes.tuple_of(look['ink']), 1)
        MUTED_NORMAL, MUTED_TIRED = look['island_muted'], look['island_tired']
        MUTED_COLOR = MUTED_TIRED if fonts.tired else MUTED_NORMAL
        SEP_COLOR = '#%02x%02x%02x' % tuple(round(c * 255) for c in MUTED_NORMAL[:3])
        paint.ISLAND = look['island']
        fonts.TIRED_MUTED = look['tired']
        windowframe.use_theme()
        palette = themes.palette()
        mascot.set_accent(palette.get('accent'))
        self.colors = paint.colors(palette)
        self.markups = {}
        if getattr(self, 'chat_cache', None) is not None:
            getattr(self, 'chat_cache', {}).clear()     # los textos ya medidos llevan los colores del tema anterior
        self.chat_theme()

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

            ('status', cómo está, papel)   la etiqueta que va junto al título
            ('text', texto, color)         una frase; puede traer su marcado
            ('chips', [(texto, papel)])    lo que se sabe de ella, en etiquetas
            ('stats', [(cifra, nombre)])   sus cifras, en fichas
            ('items', [cosa], cuántas más) lo que nombra una por una (`on_source`)
            ('head', título de un bloque) y ('cmd', comando, qué hace)

        Los colores salen de la paleta del tema, cada uno con su papel. Cómo
        está va en el color de su punto: verde, rojo o ámbar. Lo que trae
        ahora la fuente son cifras con su nombre (fichas) o frases, con las
        cifras resaltadas (`paint.stats`, `paint.note`)."""
        text, soft = rgb(self.ink('arg')), rgb(self.ink('text', TIP_SOFT))
        if key == commands.HELP:
            return 'Atajos de elyares-engineer', [('text', 'Para consultar: nada de aquí se ejecuta', soft)
                                            ] + self.tip_ref
        state, now = self.source_state(key), time.monotonic()
        src = self.sources.get(key) or {}
        tone = {'on': 'pass', 'bad': 'bad', 'unknown': 'pct2'}.get(state, 'dim')
        status = sources.STATE_TEXT[state].capitalize()
        # En rojo, la nota es la de la avería, no el número de sesiones.
        note = src.get('note', '') if state == 'bad' else self.source_note(key)
        chips = []
        if state == 'bad' and src.get('why') and key not in sources.MISSING:
            # Lo que falta instalar falta desde siempre; lo que dejó de
            # responder, desde un momento que vale la pena saber.
            status += f' desde {ago(now - src["since"])}'
        elif note and state != 'off':
            chips.append((note, 'cmd'))
        if key == 'usage' and state == 'on' and self.model.limit:
            chips.append((f'límite de 5 h al {self.model.limit:.0f}%', paint.context_role(self.model.limit)))
        if key != 'claude' and state == 'on':
            n = sum(1 for sid in self.model.sessions if sid.startswith(sources.PREFIXES[key]))
            # Las alertas que tenga, en ámbar; sin ninguna, más suave.
            chips.append(('sin alertas', 'text') if not n
                         else ('1 alerta' if n == 1 else f'{n} alertas', 'pct2'))
        rows = [('status', status, tone), ('text', sources.ABOUT[key], text)]
        if chips:
            rows.append(('chips', chips))

        def phrase(line):
            return ('text', line, text, self.tip_markup(paint.note(line)))

        if state == 'bad':
            # Por qué está en rojo y qué hacer.
            if src.get('why') or note:
                rows.append(phrase(src.get('why') or note))
            if src.get('fix'):
                rows.append(('text', src['fix'], rgb(self.ink('var'))))
        elif state == 'on':
            items = src.get('items') or []
            for i, line in enumerate(src.get('tip') or []):
                stats = paint.stats(line)
                rows.append(('stats', stats) if stats else phrase(line))
                if i == 0 and items:
                    # Debajo de la línea que las cuenta, cuáles son.
                    rows.append(('items', items[:TIP_ITEMS], len(items) - TIP_ITEMS))
            if key == 'coffe' and self.model.focus:
                held = sum(1 for s in self.model.sessions.values() if s.state in ('waiting', 'alert'))
                if held:
                    rows.append(('text', '1 aviso espera al descanso' if held == 1
                                 else f'{held} avisos esperan al descanso', rgb(self.ink('pct2'))))
            if src.get('polled'):
                rows.append(('text', f'Consultado {ago(now - src["polled"])}', soft))
        if key != 'claude':
            # Claude no se apaga desde aquí: sin sus hooks no hay nada que mostrar.
            rows.append(('text', 'Clic para prenderla' if state == 'off' else 'Clic para apagarla',
                         rgb(self.ink('flag'))))
        return sources.LABELS[key], rows + self.tip_ref

    def ink(self, role, light=TIP_LIGHT):
        """El color de un papel (`paint.colors`) para la burbuja: avivado."""
        color = self.colors[role]
        return color if role in TIP_FIXED else self.vivid(color, light)

    @staticmethod
    def vivid(color, light=TIP_LIGHT):
        """Un #rrggbb avivado como el de la burbuja, para leerse sobre el vidrio."""
        return paint.vivid(color, TIP_VIVID, light)

    def tip_markup(self, parts):
        """[(texto, papel)] como marcado de Pango, con los colores de la burbuja."""
        return ''.join(f'<span foreground="{self.ink(role)}">{html.escape(text, quote=False)}</span>'
                       for text, role in parts)

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
        elif order == 'sessions':
            if req:
                req.reply({'sessions': self.tmux_sessions(fresh=True) or []})
        elif order in ('allow', 'deny'):
            why = self.answer(order == 'allow', (msg or {}).get('peer'))
            if req:
                req.reply({'ok': not why, 'why': why})
        elif order == 'toggle':
            if (msg or {}).get('source') in sources.PREFIXES:
                self.toggle_source(msg['source'])
        elif order == 'window':
            if (msg or {}).get('how') == 'toggle':
                self.toggle_window()
            else:
                self.open_window()
        elif order == 'hide':
            if self.windowed:
                return GLib.SOURCE_REMOVE
            self.off = not self.off
            self.collapse()
        elif order == 'compact':
            self.toggle_compact()
        elif order == 'pin':
            self.toggle_pinned()
        elif order == 'theme':
            name = (msg or {}).get('name')
            if name in themes.THEMES:
                self.pick_theme(name)
            else:
                self.load_theme()
                self.ensure_tick()
        elif order == 'glass':
            self.settings['glass'] = not self.settings['glass']
            settings.save(self.settings)
            self.ensure_tick()
        elif order == 'reload':
            answer = self.reload()
            if req:
                req.reply(answer)
        elif order == 'projects':
            self.toggle_projects()
        elif order == 'workflows':
            self.toggle_workflows()
        elif order == 'move':
            self.move((msg or {}).get('where'))
        elif order == 'chat':
            agent, cwd = (msg or {}).get('agent'), (msg or {}).get('cwd')
            cwd = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else None
            if agent in AGENT_NAMES or cwd:
                # Con quién o dónde: se abre ahí, no se alterna.
                self.open_chat(typing=True, agent=AGENT_NAMES.get(agent), cwd=cwd)
            else:
                self.toggle_chat()
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

    # ── volver a arrancar con el código de la carpeta ───────────────────────

    def reload(self):
        """`elyares-ctl reload`: la isla se vuelve a arrancar para tomar los
        cambios de su carpeta, sin perder las sesiones ni las conversaciones
        del chat. Con un turno en curso en algún chat, espera a que acabe:
        quien lo pide suele ser ese mismo Claude. Si el código no arranca, no
        lo hace y dice por qué. Devuelve lo que se le contesta a elyares-ctl."""
        why = self.reload_check()
        if why:
            return {'ok': False, 'why': f'no se recarga, el código no arranca: {why}'}
        self.reloading = True
        if self.chat_busy():
            return {'ok': True, 'note': 'la isla se recarga al acabar el turno en curso'}
        self.reload_soon()
        return {'ok': True, 'note': 'la isla se recarga ya'}

    @staticmethod
    def reload_check():
        """¿Arranca el código que hay en la carpeta? '' si sí; si no, la
        última línea del error. Una isla rota no se levanta sola."""
        try:
            run = subprocess.run([sys.executable, '-c', 'import elyares.app'], cwd=ROOT,
                                 capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as e:
            return str(e)
        lines = run.stderr.strip().splitlines()
        return '' if run.returncode == 0 else (lines[-1] if lines else f'código {run.returncode}')

    def reload_soon(self):
        if self.reloading and not self.chat_busy():
            GLib.timeout_add(RELOAD_MS, self.reload_now)

    def reload_now(self):
        if not self.reloading or self.chat_busy():
            return GLib.SOURCE_REMOVE   # empezó otro turno: al acabar ese
        self.reloading = False
        store.save(self.model.dump())
        self.chat_shutdown()
        try:
            if self.is_service():
                # systemd la vuelve a arrancar limpia, sin hijos sueltos.
                subprocess.Popen(['systemctl', '--user', '--no-block', 'restart', UNIT])
            else:
                # A mano: el mismo proceso, desde su lanzador (que precarga layer-shell).
                os.execv(LAUNCHER, [LAUNCHER])
        except OSError:
            pass
        return GLib.SOURCE_REMOVE

    @staticmethod
    def is_service():
        """¿Es esta la isla que lleva systemd?"""
        try:
            pid = subprocess.run(['systemctl', '--user', 'show', '-p', 'MainPID', '--value', UNIT],
                                 capture_output=True, text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return False
        return pid == str(os.getpid())

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
        notes = [('fijada', rgb('accent'))] if self.settings['pinned'] and not self.windowed else []
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
        """Las pestañas del tablero: las sesiones, por nombre para que no
        cambien de sitio. La de un encargo no tiene la suya: va en la pestaña
        desde la que se hizo."""
        return sorted((s for s in self.claude() if self.host(s) is s), key=lambda s: (s.proj.lower(), s.sid))

    def tab_session(self):
        """La sesión de la pestaña elegida. Si no hay ninguna elegida, o se
        fue, se queda con la más urgente."""
        sessions = self.claude()
        chosen = next((s for s in sessions if s.sid == self.tab), None)
        if chosen is None and sessions:
            chosen = sessions[0]
        if chosen is not None:
            chosen = self.host(chosen)
            self.tab = chosen.sid
        return chosen

    def seat(self, s, role):
        """La sesión en la que trabaja ese personaje en la pestaña de `s`: la
        de su encargo, si lo tiene y no anda ya de subagente en la propia."""
        c = self.crew(s).get(role)
        other = self.model.sessions.get(c.session) if c is not None else None
        if other is None or next(m for m in s.team() if m.role == role).busy:
            return s
        return other

    def team(self, s):
        """Los cuatro de la pestaña de `s`: los de su sesión y, en su sitio,
        los de la familia a los que se les encargó algo desde ella, que
        trabajan cada uno en su conversación."""
        team = s.team()
        for role, c in self.crew(s).items():
            i = next(i for i, m in enumerate(team) if m.role == role)
            if team[i].busy:
                continue
            other = self.seat(s, role)
            mine = team[i] if other is s else next(m for m in other.team() if m.role == role)
            if c.busy and not mine.busy:
                # Recién encargado: Claude todavía no dice qué hace.
                mine = Member(role, c.name, 'working', mine.steps, mine.since)
            team[i] = mine
        return team

    def follow(self, v):
        """La pestaña se va sola a la sesión que pide permiso o acaba de
        terminar: es lo que no debe quedarse tapado en otra carpeta. Y si la
        elegida se quedó en reposo, a la más urgente de las que trabajan: con
        los cuatro libres a la vista mientras otra sesión trabaja, la isla
        parece desconectada. Solo con una novedad: sin ella, la pestaña que
        se eligió a mano se queda."""
        if v.key == self.view.key:
            return
        if self.chat_typing and not self.chat_open:
            return                      # escribiéndole a uno en su desglose: no se mueve
        s = v.session
        if self.tab_manual and (s is None or s.state != 'permission'):
            return                      # elegiste tú esta pestaña: solo un permiso te la quita
        if s is None or s.state not in ('permission', 'done'):
            sessions = [o for o in ([s] if s else []) + v.others if o.state != 'alert']
            chosen = next((o for o in sessions if o.sid == self.tab), None)
            if chosen is None or self.busy(chosen):
                return
            s = next((o for o in sessions if self.busy(o)), None)
            if s is None:
                return
        s = self.host(s)
        if self.tab != s.sid:
            self.focus = None
        self.tab = s.sid
        self.tab_manual = False

    def busy(self, s):
        """¿Alguno de los cuatro de la sesión hace algo? Es lo que dice su tablero."""
        return any(m.busy for m in self.team(s))

    def focused(self):
        """(sesión, miembro) del desglose abierto, o None. Se cierra solo si
        se cambió de pestaña o ya no quedan pasos que leer; el de uno de los
        tres no, que tiene su mini chat."""
        s = self.tab_session()
        if not self.focus or s is None or s.sid != self.focus[0]:
            return None
        member = next((m for m in self.team(s) if m.role == self.focus[1]), None)
        if member is None or not (member.steps or member.role != MAIN_ROLE):
            return None
        return s, member

    def body_h(self):
        """Alto del tablero bajo las pestañas: el de los cuatro o el de un
        desglose, que con su mini chat mide un poco más."""
        if not self.focused():
            return max(BOARD_H, self.window_body) if self.windowed else BOARD_H
        return FOCUS_H + (chatview.MINI_H if self.briefing() else 0)

    def next_tab(self):
        """Pasa a la pestaña que sigue, y de la última a la primera."""
        tabs = [s.sid for s in self.tabs()]
        if tabs:
            here = self.tab_session().sid
            self.tab, self.focus = tabs[(tabs.index(here) + 1) % len(tabs)], None
            self.tab_manual = True

    def next_focus(self):
        """Abre el desglose del primero que tenga pasos, luego el del que
        sigue, y después del último vuelve al tablero."""
        s = self.tab_session()
        if s is None:
            return
        roles = [m.role for m in self.team(s) if m.steps]
        now = self.focus[1] if self.focused() else None
        after = roles[roles.index(now) + 1:] if now in roles else roles
        self.focus = (s.sid, after[0]) if after else None

    def asking(self):
        """La sesión cuyo permiso se puede contestar desde la isla: la de la
        cabecera o, en el tablero, la de la pestaña elegida o la de uno de
        sus encargos."""
        s = self.tab_session() if self.target() == 'board' else self.view.session
        group = [s]
        if s is not None and self.target() == 'board':
            group += [self.model.sessions.get(c.session) for c in self.crew(s).values()]
        return next((o for o in group if o is not None and o.state == 'permission' and o.ask is not None),
                    None)

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
        if mode != 'board':
            return self.view.others
        shown = self.board_card()
        # Las respuestas de los agentes van en su ficha, con su fila de nombres: no se repiten aquí.
        return [s for s in self.alerts() if not (shown is not None and shown.reply and s.reply)]

    def replies(self):
        """Las respuestas de los agentes que esperan, la última primero."""
        return sorted((s for s in self.alerts() if s.reply), key=lambda s: -s.changed)

    def board_card(self):
        """La alerta cuya ficha va en el tablero: la que se eligió en una fila
        o, si no hay, la respuesta de un agente que se está leyendo (la última,
        si no se eligió otra). None si no hay ninguna de las dos."""
        pinned = self.model.sessions.get(self.pin)
        if pinned is not None and pinned.card and not pinned.reply:
            return pinned
        replies = self.replies()
        if not replies or self.focused():
            return None
        return next((s for s in replies if s.sid == self.reply_pick), replies[0])

    def reply_chips(self, mode):
        """Alto de la fila de respuestas: solo con más de una, y en el tablero."""
        shown = self.board_card() if mode == 'board' else None
        return REPLY_CHIPS_H if shown is not None and shown.reply and len(self.replies()) > 1 else 0

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
        if self.chat_typing and not self.off and self.briefing() is not None:
            return                      # escribiéndole a uno en su desglose: no se cierra debajo de las manos
        if self.collapse_id:
            GLib.source_remove(self.collapse_id)
            self.collapse_id = 0
        # Fijada no se cierra: solo suelta la alerta que se había elegido en la
        # lista, para que no tape algo más urgente.
        self.expanded = self.settings['pinned'] or self.windowed
        if not self.expanded:
            self.tab_manual = False     # al cerrarse, la próxima vez vuelve a seguir lo que pasa
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
        """Fija la isla abierta, o la suelta para que vuelva a cerrarse sola.
        Fijada se queda además en el monitor donde se fijó; suelta vuelve a
        seguir al enfocado, que puede ser otro."""
        if self.windowed:
            return                      # la ventana ya es la isla abierta del todo
        pinned = self.settings['pinned'] = not self.settings['pinned']
        self.settings['pinned_monitor'] = (self.monitor or {}).get('name', '') if pinned else ''
        settings.save(self.settings)
        if pinned:
            self.off = False
            self.expand()
        else:
            self.collapse()
            focused = hypr.focused_monitor()
            if focused:
                self.on_focused_monitor(focused['name'])

    def toggle_compact(self):
        if self.windowed:
            return
        if self.chat_open:
            self.close_chat()           # el chat manda sobre la isla mientras está abierto: sin cerrarlo no se achica
        self.settings['compact'] = not self.settings['compact']
        settings.save(self.settings)
        self.collapse()

    def target(self):
        if self.off and not self.windowed:
            return 'off'
        if self.chat_open:
            # El chat ocupa la isla mientras está abierto, fijada o no.
            return 'chat'
        if self.projects_open:
            return 'projects'
        mode = self.view.mode
        if self.expanded or self.windowed:
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
        if mode == 'board':
            s = self.board_card() or s
        if not s or not s.card or mode not in ('open', 'list', 'board'):
            return 0
        if mode == 'board' and self.focused():
            return 0
        # La de unas pruebas se ve sin pedirla mientras la isla está abierta
        # por ellas: para eso se abrió. La respuesta de un agente se ve siempre
        # que el tablero esté a la vista, hasta que se atienda.
        if not (self.hover or self.expanded or (s.tests and self.view.mode == 'open')
                or (mode == 'board' and s.reply)):
            return 0
        lines = len(s.lines) if not s.reply else min(len(s.lines), REPLY_LINES)
        body = (PREVIEW_HEAD if s.where or s.note else 0) + lines * CODE_LINE_H
        return (body + 2 * PREVIEW_PAD if body else 0) + CARD_BUTTONS + self.reply_chips(mode)

    def pills_h(self, mode):
        """Alto de la franja de fuentes: solo cuando alguien abrió la isla a mano."""
        if self.windowed and self.frame is not None:
            return 0                    # en la ventana, Fuentes y la ayuda están en la barra de título
        by_hand = self.expanded or self.hover
        return PILLS_H if by_hand and mode in ('open', 'list', 'board') else 0

    def goal(self):
        """Tamaño al que va la isla: el del modo, más el detalle entero, las
        filas y las fuentes."""
        if self.windowed and self.wf_open:
            return BOARD_W, self.workflows_goal()[1]    # el panel de flujos cubre la ventana, sea lo que sea lo de abajo
        mode = self.target()
        if mode == 'chat':
            return chatview.CHAT_W, chatview.CHAT_H
        if mode == 'projects':
            return self.projects_goal()
        prev = self.preview_h(mode)
        card = self.card_h(mode)
        more = self.extra(mode) + prev + card + self.pills_h(mode)
        rows = len(self.rows_for(mode))
        if mode == 'board':
            # Mide lo mismo trabajen uno, dos o los cuatro: solo crece el desglose.
            h = TABS_H + self.body_h() + BOARD_PAD
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
            if not self.windowed:
                self.collapse()         # la ventana ya es la isla abierta: salir con el ratón no suelta nada
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
                if not self.windowed:
                    LayerShell.set_monitor(self.win, mon)
                self.screen_w = mon.get_geometry().width
                self.screen_h = mon.get_geometry().height
                self.place()
                self.flows_monitor()
                return True
        return False

    # ── dónde va, a lo ancho de la pantalla ─────────────────────────────────

    def position(self):
        """Dónde va la isla, de 0 (izquierda) a 100 (derecha); 50 es el centro."""
        try:
            return clamp(float(self.settings.get('position', CENTER)), 0, 100)
        except (TypeError, ValueError):
            return CENTER

    def offset(self):
        """Cuánto se corre la ventana desde el borde izquierdo de su pantalla."""
        return round(max(0, self.screen_w - WIN_W) * self.position() / 100)

    def place(self):
        """Pone la ventana en su sitio. En el centro va anclada solo arriba,
        como siempre, y el compositor la centra; en otro sitio, anclada
        también a la izquierda, con el margen que le toca en esa pantalla."""
        win = getattr(self, 'win', None)
        if win is None or self.windowed:
            return
        moved = self.moved()
        LayerShell.set_anchor(win, LayerShell.Edge.LEFT, moved)
        LayerShell.set_margin(win, LayerShell.Edge.TOP, self.top())
        LayerShell.set_margin(win, LayerShell.Edge.LEFT, self.offset() if moved else 0)
        self.flows_follow()

    def top(self):
        """Cuánto baja la isla desde el borde de arriba, en px; 0 es su sitio de siempre."""
        try:
            screen_h = getattr(self, 'screen_h', 0)
            low = max(0, screen_h - WIN_H) if screen_h else 4000
            return round(clamp(float(self.settings.get('position_y', 0)), 0, low))
        except (TypeError, ValueError):
            return 0

    def moved(self):
        """¿Está fuera de su sitio de siempre?"""
        return self.position() != CENTER and self.screen_w > 0

    def move(self, where):
        """`elyares-ctl move`: `left` y `right` la llevan al siguiente sitio de
        ese lado, `up` y `down` la suben y la bajan, `center` la centra, `reset`
        la devuelve a arriba al centro, y un número del 0 al 100 la pone ahí.
        Se guarda: al volver a arrancar sigue donde la dejaste."""
        now = self.position()
        if where == 'reset':
            self.settings['position'], self.settings['position_y'] = CENTER, 0
        elif where in ('up', 'down'):
            self.settings['position_y'] = self.top() + (STEP_Y if where == 'down' else -STEP_Y)
            self.settings['position_y'] = self.top()
        if where in ('reset', 'up', 'down'):
            settings.save(self.settings)
            self.place()
            self.ensure_tick()
            return
        if where == 'left':
            pos = max((s for s in SLOTS if s < now), default=SLOTS[0])
        elif where == 'right':
            pos = min((s for s in SLOTS if s > now), default=SLOTS[-1])
        elif where == 'center':
            pos = CENTER
        else:
            try:
                pos = clamp(float(where), 0, 100)
            except (TypeError, ValueError):
                return
        self.settings['position'] = int(pos) if float(pos).is_integer() else pos
        settings.save(self.settings)
        self.place()
        self.ensure_tick()

    def on_drag_begin(self, gesture, _x, _y):
        """Mover la isla, como una isla flotante: con Alt + arrastrar o, sin
        teclado, arrastrando con el botón del medio. Alt solo se ve si la isla
        tiene el teclado (Wayland no manda los modificadores a quien no lo
        tiene), así que el botón del medio es el que siempre vale."""
        self.drag_wait = gesture.get_current_button() == Gdk.BUTTON_MIDDLE
        self.dragging = bool(gesture.get_current_event_state() & DRAG_MASK)
        # De dónde parte: el ratón en la pantalla (no en la ventana, que se mueve
        # con él) y el sitio de la isla.
        self.drag_start = hypr.cursor_pos()
        self.drag_from = (self.offset(), self.top())
        self.drag_last = (0.0, 0.0)
        if self.dragging:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        elif not self.drag_wait:
            gesture.set_state(Gtk.EventSequenceState.DENIED)

    def on_drag_update(self, gesture, dx, dy):
        if not getattr(self, 'dragging', False):
            # El del medio espera a moverse: sin moverse es un clic (fijar la isla).
            if not getattr(self, 'drag_wait', False) or math.hypot(dx, dy) < DRAG_SLOP:
                return
            self.dragging = True
            if gesture is not None:
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        room = max(0, self.screen_w - WIN_W)
        pos, start = hypr.cursor_pos(), getattr(self, 'drag_start', None)
        if pos and start:
            # Lo que se movió el ratón en la pantalla, sobre el sitio de donde se
            # partió: no depende de si el compositor ya movió la ventana.
            mx, my = pos[0] - start[0], pos[1] - start[1]
            if room:
                self.settings['position'] = clamp((self.drag_from[0] + mx) * 100 / room, 0, 100)
            self.settings['position_y'] = self.drag_from[1] + my
        else:
            # Sin la posición del ratón en la pantalla, el gesto mide desde la
            # ventana, que se mueve con la isla: lo que cuenta es lo que falta.
            if room:
                self.settings['position'] = clamp((self.offset() + dx) * 100 / room, 0, 100)
            self.settings['position_y'] = self.top() + dy
        self.settings['position_y'] = self.top()      # dentro de la pantalla: sin esto crecería sin límite
        self.place()
        self.ensure_tick()

    def on_drag_end(self, _gesture, _dx, _dy):
        if getattr(self, 'dragging', False):
            self.dragging = False
            settings.save(self.settings)

    def on_monitors_changed(self, *_):
        """Conectaron o desconectaron una pantalla: se espera a que Hyprland
        termine de acomodarlas, y la isla vuelve a la suya."""
        if not getattr(self, 'monitors_id', 0):
            self.monitors_id = GLib.timeout_add(MONITORS_SETTLE_MS, self.settle_monitor)

    def settle_monitor(self):
        """Al apagarse y volver a prenderse su pantalla, el compositor deja la
        isla en otra, con el margen de la que tenía: cae fuera y no se ve. Se
        vuelve a poner en la suya; si ya no está, se va a la enfocada."""
        self.monitors_id = 0
        name = (self.monitor or {}).get('name')
        if name and self._set_monitor(name):
            self.monitor = next((m for m in hypr.monitors() if m.get('name') == name), self.monitor)
            self.region = None
            self.update_region()
            return GLib.SOURCE_REMOVE
        focused = hypr.focused_monitor()
        if focused:
            self.monitor = None         # la suya ya no está: no hay de dónde no moverse
            self.on_focused_monitor(focused['name'])
        return GLib.SOURCE_REMOVE

    def start_monitor(self):
        """El monitor donde arranca la isla: el enfocado o, si quedó fijada,
        aquel en el que se fijó, mientras siga conectado."""
        monitors = hypr.monitors()
        name = self.settings['pinned'] and self.settings['pinned_monitor']
        return (next((m for m in monitors if name and m.get('name') == name), None)
                or next((m for m in monitors if m.get('focused')), None))

    def on_focused_monitor(self, name):
        """La isla se va al monitor enfocado. Fijada no se mueve del suyo,
        salvo que lo desconecten: entonces se va al enfocado y se queda ahí."""
        if self.monitor and self.monitor.get('name') == name:
            return GLib.SOURCE_REMOVE
        monitors = hypr.monitors()
        here = (self.monitor or {}).get('name')
        if self.settings['pinned'] and any(m.get('name') == here for m in monitors):
            return GLib.SOURCE_REMOVE
        if self._set_monitor(name):
            self.monitor = next((m for m in monitors if m.get('name') == name), None)
            if self.settings['pinned']:
                self.settings['pinned_monitor'] = name
                settings.save(self.settings)
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
        if self.windowed:
            self.w, self.h, self.vw, self.vh = tw, th, 0.0, 0.0     # sin rebote: la ventana no es una isla que se asoma
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
        if settled and self.windowed:
            # La burbuja de una pastilla pide sitio debajo: solo mientras se ve.
            self.window_fit(self.h, TIP_ROOM if self.tip else 0)
        self.flows_follow()             # la isla de los flujos va pegada a ésta

        widget.queue_draw()
        # Una burbuja a medio irse sigue pidiendo cuadros hasta que termina.
        if settled and not self.hover and not self.override and not self.tip_pop:
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

    cursor_seen = None
    cursor_thread = None

    def watch_cursor(self):
        """El cursor se pregunta a Hyprland en un hilo: si Hyprland tarda, la
        interfaz no se congela esperándolo (el socket espera hasta 0.5 s)."""
        if self.cursor_thread is not None:
            return

        def loop():
            while True:
                time.sleep(LOOK_EVERY)
                if self.ticking or self.slow_id:
                    try:
                        self.cursor_seen = hypr.cursor_pos()
                    except OSError:
                        self.cursor_seen = None

        self.cursor_thread = threading.Thread(target=loop, daemon=True, name='cursor')
        self.cursor_thread.start()

    def update_look(self, now):
        if now - self.last_look >= LOOK_EVERY and self.monitor:
            self.last_look = now
            self.watch_cursor()
            pos = self.cursor_seen
            if pos:
                m = self.monitor
                top = m['y'] + (m.get('reserved') or [0, 0])[1]
                # Mira desde donde está: corrida, su centro ya no es el de la pantalla.
                middle = self.offset() + WIN_W / 2 if self.moved() else m['width'] / 2
                dx = pos[0] - (m['x'] + middle)
                dy = pos[1] - (top + min(self.h, SIZES['ask'][1]) / 2)
                d = math.hypot(dx, dy) or 1
                k = min(1.0, d / 400)
                self.look_target = (dx / d * k, dy / d * k)
        self.look[0] += (self.look_target[0] - self.look[0]) * 0.15
        self.look[1] += (self.look_target[1] - self.look[1]) * 0.15

    def update_region(self):
        if self.windowed:
            return                      # la ventana de la app recibe en todo su área
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
        h = clamp(self.h, 0, WIN_H)
        if self.windowed:
            # En la ventana, a todo lo ancho y lo alto: no es una isla suelta, y lo
            # que no ocupa el contenido es el mismo fondo, no un hueco sin pintar.
            room = self.da.get_height()
            return 0, width, max(h, room) if isinstance(room, (int, float)) else h
        w = clamp(self.w, 0, width)
        return (width - w) / 2, w, h

    def island_fill(self, cr, x0, w, h):
        """El cuerpo de una isla: colgada del borde de arriba, con las esquinas
        de abajo redondas, y su fondo (translúcido en modo vidrio). Deja el
        contorno como camino, para recortar con él, y devuelve el filo claro
        del vidrio (un camino) o None."""
        r = min(26, h / 2, w / 2) if h > 12 else min(8, h)
        if self.windowed:
            r = 0                       # sin esquinas ni filo: el cuerpo de una ventana
        cr.move_to(x0, 0)
        cr.line_to(x0 + w, 0)
        cr.line_to(x0 + w, h - r)
        cr.arc(x0 + w - r, h - r, r, 0, math.pi / 2)
        cr.line_to(x0 + r, h)
        cr.arc(x0 + r, h - r, r, math.pi / 2, math.pi)
        cr.close_path()
        glass = self.settings['glass']
        cr.set_source_rgba(*ISLAND_BG[:3], (WIN_GLASS_ALPHA if self.windowed else GLASS_ALPHA) if glass else ISLAND_BG[3])
        cr.fill_preserve()
        # Una ventana no lleva el filo claro: ya tiene su borde de Hyprland.
        return cr.copy_path() if glass and not self.windowed else None

    def draw(self, _da, cr, width, _height):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        # En la ventana sin vidrio no hay nada detrás que se vea: el fondo es el
        # de la isla, entero. Con vidrio, transparente, y es Hyprland quien
        # desenfoca lo de atrás (la ventana no es una capa: sin la regla de capa).
        opaque = self.windowed and not self.settings['glass']
        cr.set_source_rgba(*ISLAND_BG[:3], 1) if opaque else cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if self.window_covered():
            self.buttons, self.rows, self.pills, self.hits = {}, [], [], []
            self.tip = self.card_span = self.chat_box = None
            return                      # lo tapa un panel de widgets: nada de lo de debajo se ve

        x0, w, h = self.island_rect(width)
        if h < 0.5 or w < 1:
            self.tip_pop = 0.0
            return
        edge = self.island_fill(cr, x0, w, h)
        cr.save()
        cr.clip()

        now = time.monotonic()
        mode = self.target()
        pills = self.pills_h(mode)
        prev = self.preview_h(mode)
        card = self.card_h(mode)
        self.buttons, self.rows, self.pills, self.hits = {}, [], [], []
        self.tip = self.card_span = self.chat_box = None
        if mode == 'chat':
            self.draw_chat(cr, x0, w, h, clamp((w - 420) / 120) * clamp((h - 300) / 200), now)
            cr.restore()
            if edge:
                cr.append_path(edge)
                cr.set_source_rgba(*themes.glow(), GLASS_EDGE)
                cr.set_line_width(1)
                cr.stroke()
            self.chat_place(h)
            return
        if mode == 'projects':
            self.draw_projects(cr, x0, w, h, clamp((w - 420) / 120) * clamp((h - 90) / 60))
            cr.restore()
            if edge:
                cr.append_path(edge)
                cr.set_source_rgba(*themes.glow(), GLASS_EDGE)
                cr.set_line_width(1)
                cr.stroke()
            self.chat_place(h)
            return
        if mode == 'board':
            full_h = h
            text_alpha = clamp((w - 420) / 120) * clamp((h - 110) / 60)
            body = self.body_h()
            if text_alpha > 0 and not (self.board_widgets() or self.focus_widgets()):     # en la ventana lo llevan los widgets
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
            chips = self.reply_chips(mode)
            if chips:
                self.draw_reply_chips(cr, x0, w, head, below)
            self.draw_card(cr, x0, w, head + chips, card - chips, below,
                           self.board_card() if mode == 'board' else None)
        head += prev + card             # la lista va debajo de la vista previa o de la ficha
        rows = self.rows_for(mode)
        if listed and rows and full_h > head:
            self.draw_rows(cr, x0, w, head, below, rows, ALERT_ROWS if mode == 'board' else MAX_ROWS)
        if pills and full_h > head:
            self.draw_pills(cr, x0, w, full_h, below)
        cr.restore()
        self.chat_place(h)              # la caja del mini chat, si un desglose dejó su sitio
        if edge:
            # El filo claro es lo que hace que el fondo translúcido se lea como vidrio.
            cr.append_path(edge)
            cr.set_source_rgba(*themes.glow(), GLASS_EDGE)
            cr.set_line_width(1)
            cr.stroke()
        if self.tip or self.tip_pop:
            self.draw_tip(cr, width, full_h, now)

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
            if mode in ('petit', 'peek'):
                self.draw_reply_count(cr, x0, w, pet_alpha)
        elif mode == 'hidden':
            self.draw_reply_count(cr, x0, w, 1.0, h)

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
            start = self.project_start() if self.detail == self.start_text() else None
            if start is not None:
                self.hits.append(('start', start.path, tx, mid - 21, right - tx, 44))
        if ask_alpha > 0 and text_alpha > 0:
            self.draw_buttons(cr, x0 + w - 18, full_h - 14, ask_alpha * text_alpha)
        return full_h, head, text_alpha

    def draw_reply_count(self, cr, x0, w, alpha, strip=0):
        """Cuántas respuestas de agentes esperan, para cuando el tablero no se
        ve: un número en la esquina de la pastilla o de la isla asomada, con el
        color de la última; escondida (`strip` es su alto), una marca en su
        franja. Nada si no hay ninguna."""
        waiting = self.replies()
        if not waiting or alpha <= 0:
            return
        tint = waiting[0].tint
        color = mascot.rgba(mascot.accent(tint))[:3] if tint else rgb(self.colors['ok'])
        if strip:
            cr.rectangle(x0 + w / 2 - 20, 0, 40, strip)
            cr.set_source_rgba(*color, alpha)
            cr.fill()
            return
        r = 8
        cx, cy = x0 + w - r - 4, r + 3
        cr.new_sub_path()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(*color, alpha)
        cr.fill()
        label = self._layout(cr, str(len(waiting)) if len(waiting) < 10 else '9+', FONT_DETAIL)
        lw, lh = label.get_pixel_size()
        cr.move_to(cx - lw / 2, cy - lh / 2)
        cr.set_source_rgba(.04, .04, .06, alpha)
        PangoCairo.show_layout(cr, label)

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
        if now is None:
            mascot.paint_static(cr, role, pet, x, y, size, alpha)    # quieta: ya dibujada una vez
            return
        cr.push_group()
        cr.translate(x, y + size * .015)
        cr.scale(size / 253, size / 253)
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
        cr.set_source_rgba(*themes.glow(), (.085 if over else .05) * alpha)
        cr.fill_preserve()
        if tint:
            r, g, b, _ = mascot.rgba(tint)
            veil = cairo.RadialGradient(x + w / 2, y + h * 1.25, 4, x + w / 2, y + h * 1.25, h * 1.05)
            veil.add_color_stop_rgba(0, r, g, b, .42 * alpha)
            veil.add_color_stop_rgba(1, r, g, b, 0)
            cr.set_source(veil)
            cr.fill_preserve()
        cr.new_path()

    def tab_dot(self, s):
        """El color del punto de una pestaña: rojo si piden permiso, el del
        que trabaja, amarillo si espera, verde si terminó; None en reposo."""
        team = self.team(s)
        states = {m.state for m in team}
        if 'permission' in states:
            return 'red'
        if 'working' in states:
            # El de la sesión; si ella descansa, el del encargo que trabaja.
            working = [m.role for m in team if m.state == 'working']
            return mascot.accent(s.role if s.role in working else working[0])
        return 'yellow' if 'waiting' in states else 'green' if 'done' in states else None

    def tab_label(self, s):
        """El nombre de una sesión en su pestaña: el de su carpeta y, si lo
        tiene, el que le puso Claude Code. La del chat de la isla lo dice."""
        if s.sid in self.chat_sessions:
            # El proyecto en el que se empezó la conversación, no la carpeta
            # por la que ande Claude ahora.
            c = self.chat_of(s, s.main_agent if s.owner != MAIN_ROLE else '')
            place = self.project_of(c.cwd) if c is not None else None
            name = place.name if place is not None else c.project if c is not None else s.proj
            return f'{name} · chat' + (f' {s.owner}' if s.owner != MAIN_ROLE else '')
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
        """El tablero: las pestañas y, de la sesión elegida, su familia. Los
        que trabajan van al frente y los libres a la banca; con todos
        trabajando son dos filas de cuadros, y con ninguno, todos en fila."""
        s = self.tab_session()
        self.draw_tabs(cr, x0, w, s, alpha)
        left, top, width = x0 + BOARD_PAD, TABS_H, w - 2 * BOARD_PAD
        focus = self.focused()
        if focus:
            self.draw_focus(cr, left, top, width, body, focus[1], s, alpha, now)
            return
        team = self.team(s)
        front = [m for m in team if m.busy]
        if not front or len(front) == len(team):
            # Todos igual: en dos filas de cuadros si trabajan; libres, en una
            # fila mientras quepan (hasta ROW_MOST) y en dos si son más.
            rows = 2 if front or len(team) > ROW_MOST else 1
            cols = math.ceil(len(team) / rows)
            cw = (width - (cols - 1) * BOARD_GAP) / cols
            ch = (body - BOARD_GAP) / 2 if rows == 2 else body
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
        notes = [('fijada', rgb('accent'))] if self.settings['pinned'] and not self.windowed else []
        if current.context >= CONTEXT_SHOW:
            notes.append((f'contexto {current.context:.0f}%',
                          rgb(self.colors[paint.context_role(current.context)])))
        for text, color in notes:
            right -= self.put(cr, text, FONT_DETAIL, right, 10, color, alpha, align=1) + 12
        tabs, labels = self.tabs(), self.tab_labels()
        x, y, th = x0 + 12, 6, 24
        # Si estás en tmux en un proyecto sin ningún Claude, al final va su
        # pestaña fantasma: un clic empieza ahí.
        start = self.project_start()
        # Si no caben, se reparten el sitio y el nombre se corta.
        room = max(40, (right - x) / (len(tabs) + (start is not None)) - 4)
        for s in tabs:
            label = self._layout(cr, labels[s.sid], FONT_ROW, room - 28)
            lw, lh = label.get_pixel_size()
            tw = lw + 28
            chosen = s is current
            if chosen or self.over(x, y, tw, th):
                mascot.rrect(cr, x, y, tw, th, th / 2)
                cr.set_source_rgba(*themes.glow(), (.13 if chosen else .06) * alpha)
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
        if start is not None:
            label = self._layout(cr, f'+ {start.name}', FONT_ROW, room - 20)
            lw, lh = label.get_pixel_size()
            tw = lw + 20
            over = self.over(x, y, tw, th)
            mascot.rrect(cr, x + .5, y + .5, tw - 1, th - 1, th / 2)
            cr.set_source_rgba(*themes.glow(), (.10 if over else 0) * alpha)
            cr.fill_preserve()
            cr.set_dash([3, 3])
            cr.set_line_width(1)
            cr.set_source_rgba(*themes.glow(), (.45 if over else .22) * alpha)
            cr.stroke()
            cr.set_dash([])
            cr.move_to(x + 10, y + (th - lh) / 2)
            cr.set_source_rgba(*(TITLE_COLOR if over else MUTED_COLOR)[:3], alpha)
            PangoCairo.show_layout(cr, label)
            self.hits.append(('start', start.path, x, y, tw, th))

    def draw_member(self, cr, s, member, x, y, cw, ch, alpha, now):
        """Uno de los cuatro en su tarjeta: su cara con el gesto de cómo está,
        su nombre y sus últimos pasos. Si pide permiso, lo que quiere hacer
        entero y los botones. Libre va apagado; a uno de los tres, un clic le
        abre el mini chat para encargarle algo."""
        busy, role = member.busy, member.role
        tint = MEMBER_TINT.get(member.state) or mascot.accent(role)
        over = (busy or role != MAIN_ROLE) and self.over(x, y, cw, ch)
        self.panel(cr, x, y, cw, ch, alpha, tint if busy else None, over)
        if busy:
            self.hits.append(('member', (s.sid, role), x, y, cw, ch))
        elif role != MAIN_ROLE:
            self.hits.append(('brief', (s.sid, role), x, y, cw, ch))
        # Cuatro acomodos según el sitio: en columna (tres al frente, o todos
        # libres en una fila), en cuadro (todos trabajando, o libres en dos
        # filas), a medias (dos) y a lo ancho (uno). `sx` y `sw` son dónde van
        # sus pasos.
        quad, column = ch < 100, cw < 200 and ch >= 100
        wide = cw >= 300 and not quad
        if column:
            size, fx, fy = 56, x + cw / 2, y + 42
            tx, ty, tw = x + 12, y + 78, cw - 24
            sx, sw = tx, tw
        elif quad and cw < 180:
            # En cuadro y estrecho (toda la familia a la vez): la cara más
            # chica, para que quepa el nombre del personaje.
            size, fx, fy = 42, x + 27, y + ch / 2 + 2
            tx, ty, tw = x + 46, y + 9, cw - 52
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
        # Si el nombre entero no cabe (y todos empiezan igual), va el del personaje.
        fits = self._layout(cr, member.name, FONT_ROW).get_pixel_size()[0] <= (tw if column else tw - 22)
        name = member.name if fits else role
        if column:
            self.put(cr, name, FONT_ROW, x + cw / 2, ty, name_color, alpha, tw, .5)
        else:
            cr.new_sub_path()
            cr.arc(tx + 4, ty + 8, 3.5, 0, 2 * math.pi)
            cr.set_source_rgba(*mascot.rgba(tint if busy else 'metal', alpha * (1 if busy else .6)))
            cr.fill()
            took = elapsed(now - member.since) if member.state == 'working' and member.since else ''
            if wide or quad:
                # Cuánto lleva, a la derecha del nombre; a medias no cabe y va
                # debajo. En un cuadro estrecho, si se comería el nombre, no va.
                room = tw - 22 - (self._layout(cr, took, FONT_DETAIL).get_pixel_size()[0] if took else 0)
                if took and room < self._layout(cr, name, FONT_ROW).get_pixel_size()[0]:
                    took = ''
                took_w = self.put(cr, took, FONT_DETAIL, tx + tw, ty + 1, MUTED_COLOR, alpha, align=1) \
                    if took else 0
                self.put(cr, name, FONT_ROW, tx + 14, ty, name_color, alpha, tw - 22 - took_w)
            else:
                self.put(cr, name, FONT_ROW, tx + 14, ty, name_color, alpha, tw - 14)
                if took:
                    self.put(cr, took, FONT_DETAIL, tx + 14, ty + 19, MUTED_COLOR, alpha, tw - 14)
        if not busy:
            note = (('esperando' if s.delegating else 'en reposo') if role == MAIN_ROLE
                    else 'encargar ›' if over else 'libre')
            self.put(cr, note, FONT_DETAIL, x + cw / 2 if column else tx + 14, ty + 20, MUTED_COLOR,
                     alpha * .8, tw, .5 if column else 0)
            return
        if member.state == 'permission':
            # Lo que quiere hacer, entero: hay que leerlo antes de contestar.
            asks = self.seat(s, role) is self.asking()
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
        """La banca: los que no trabajan, en chiquito. Un clic en uno de los
        tres abre su mini chat para encargarle algo."""
        self.panel(cr, x, y, w, h, alpha)
        if len(members) > BENCH_ROWS:
            self.draw_bench_grid(cr, s, members, x, y, w, h, alpha)
            return
        step = h / len(members)
        # Con casi toda la familia en la banca, la cara se achica y las dos
        # líneas van más juntas.
        tight = step < 40
        size = min(34, step - 6)
        for i, member in enumerate(members):
            cy = y + step * i + step / 2
            over = member.role != MAIN_ROLE and self.over(x, cy - step / 2, w, step)
            if over:
                mascot.rrect(cr, x + 4, cy - step / 2 + 3, w - 8, step - 6, 10)
                cr.set_source_rgba(*themes.glow(), .06 * alpha)
                cr.fill()
            if member.role != MAIN_ROLE:
                self.hits.append(('brief', (s.sid, member.role), x, cy - step / 2, w, step))
            self.face(cr, member.role, 'idle', x + 26, cy + 1, size, alpha * (.8 if over else .4))
            self.put(cr, member.role, FONT_ROW, x + 48, cy - (14 if tight else 15),
                     TITLE_COLOR if over else MUTED_COLOR, alpha, w - 54)
            waits = member.role == MAIN_ROLE and s.delegating
            self.put(cr, 'esperando' if waits else 'encargar ›' if over else 'libre', FONT_DETAIL,
                     x + 48, cy + (0 if tight else 1), MUTED_COLOR, alpha * .7, w - 54)

    def draw_bench_grid(self, cr, s, members, x, y, w, h, alpha):
        """La banca cuando no caben uno debajo de otro: las caras en dos
        columnas y, al pie, el nombre del que tiene el cursor encima."""
        foot = 20
        rows = math.ceil(len(members) / 2)
        cw, ch = w / 2, (h - foot - 4) / rows
        size = min(34, ch - 4)
        hovered = None
        for i, member in enumerate(members):
            cx, cy = x + (i % 2) * cw, y + 4 + (i // 2) * ch
            over = member.role != MAIN_ROLE and self.over(cx, cy, cw, ch)
            if over:
                hovered = member
                mascot.rrect(cr, cx + 4, cy + 1, cw - 8, ch - 2, 9)
                cr.set_source_rgba(*themes.glow(), .08 * alpha)
                cr.fill()
            if member.role != MAIN_ROLE:
                self.hits.append(('brief', (s.sid, member.role), cx, cy, cw, ch))
            self.face(cr, member.role, 'idle', cx + cw / 2, cy + ch / 2 + 1, size, alpha * (.9 if over else .45))
        if hovered is not None:
            note, color = f'{hovered.role} ›', rgb(mascot.accent(hovered.role))
        elif s.delegating and any(m.role == MAIN_ROLE for m in members):
            note, color = 'engineer esperando', MUTED_COLOR
        else:
            note, color = f'{len(members)} libres', MUTED_COLOR
        self.put(cr, note, FONT_DETAIL, x + w / 2, y + h - foot + 1, color, alpha * (1 if hovered else .7), w - 10, .5)

    def draw_focus(self, cr, x, y, width, h, member, s, alpha, now):
        """El desglose de uno: a la izquierda quién es y cuánto lleva; en
        medio todos sus pasos y lo que tardó cada uno y, si es uno de los
        tres, el mini chat para encargarle algo; a la derecha, los demás en
        miniatura. Un clic a la izquierda vuelve al tablero."""
        cw = width - FOCUS_MINIS
        role = member.role
        tint = MEMBER_TINT.get(member.state) or mascot.accent(role)
        self.panel(cr, x, y, cw, h, alpha, tint if member.busy else None)
        cx = x + FOCUS_SIDE / 2
        pet = MEMBER_PET.get(member.state, 'idle')
        # Arriba, quién es; abajo, sus enlaces. Con tres enlaces lo de arriba
        # se junta un poco, para que no se monten.
        self.face(cr, role, pet, cx, y + 58, 78, alpha, now, now - s.changed)
        self.put(cr, member.name, FONT_ROW, cx, y + 104, rgb(mascot.accent(role)), alpha,
                 FOCUS_SIDE - 12, .5)
        self.put(cr, self.tab_labels()[s.sid], FONT_DETAIL, cx, y + 121, MUTED_COLOR, alpha,
                 FOCUS_SIDE - 12, .5)
        n = len(member.steps)
        took = f' · {elapsed(now - member.since)}' if member.busy and member.since else ''
        self.put(cr, f'{n} paso{"" if n == 1 else "s"}{took}' if n or member.busy else 'libre', FONT_DETAIL,
                 cx, y + 140, rgb(self.colors['arg']), alpha, FOCUS_SIDE - 12, .5)
        # Al pie, dos enlaces: al pane de la sesión y de vuelta al tablero.
        # Y su chat: con el engineer, para hablarle; con uno de los tres, que
        # ya tiene aquí su mini chat, para leer lo que contestó.
        agent = '' if role == MAIN_ROLE else state.ROLE_AGENTS[role]
        talk = 'ver su chat ›' if agent else 'hablarle ›'
        # Una sesión del chat no tiene pane: va a la sesión de tmux de su proyecto.
        jump = 'ir al pane ›' if s.pane else 'ir a su tmux ›' if s.sid in self.chat_sessions else ''
        links = ([('jump', s.sid, jump)] if jump else []) + [('talk', agent, talk), ('back', None, '‹ volver')]
        step = 24 if len(links) < 3 else 20
        for i, (kind, key, label) in enumerate(reversed(links)):
            ly = y + h - 32 - i * step
            over = self.over(x + 8, ly, FOCUS_SIDE - 16, 22)
            self.put(cr, label, FONT_DETAIL, cx, ly + 4, TITLE_COLOR if over else MUTED_COLOR, alpha,
                     FOCUS_SIDE - 16, .5)
            self.hits.append((kind, key, x + 8, ly, FOCUS_SIDE - 16, 22))
        self.hits.append(('back', None, x, y, FOCUS_SIDE, h))
        left, right = x + FOCUS_SIDE + 8, x + cw - 14
        ty, floor = y + 14, y + h - 14
        if agent:
            floor = self.draw_brief(cr, s, agent, role, left - 4, y + h - 10, right - left + 8, alpha) - 8
            if not n:
                self.put(cr, f'{agent} está libre', FONT_ROW, left, ty + 2, MUTED_COLOR, alpha, right - left)
                self.put(cr, 'Escríbele abajo qué quieres que haga: trabajará en esta carpeta, al lado '
                         'de los demás.', FONT_DETAIL, left, ty + 24, MUTED_COLOR, alpha * .8, right - left,
                         lines=3)
        # Los pasos: los últimos que caben, y arriba cuántos hubo antes.
        fit = max(2, min(FOCUS_STEPS, int((floor - ty) // 26)))
        shown = member.steps[-fit:]
        hidden = n - len(shown)
        if hidden:
            shown = member.steps[-(fit - 1):]
            hidden = n - len(shown)
        if hidden:
            self.put(cr, f'⋯ {hidden} paso{"" if hidden == 1 else "s"} antes', FONT_DETAIL, left + 20, ty,
                     MUTED_COLOR, alpha * .8)
            ty += 26
        marks = {'done': ('✓', 'green'), 'waiting': ('?', 'yellow'), 'permission': ('›', 'red')}
        for i, (text, at) in enumerate(shown):
            last = i == len(shown) - 1
            if last:
                mascot.rrect(cr, left - 4, ty - 5, right - left + 8, 24, 8)
                cr.set_source_rgba(*themes.glow(), .07 * alpha)
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
        others = [m for m in self.team(s) if m.role != role]
        mx = x + cw + FOCUS_MINIS / 2 + 2
        # Se reparten el alto del desglose: con toda la familia no caben a 40
        # cada uno, y los últimos se salían por abajo.
        gap = min(40, (h - 12) / max(1, len(others)))
        size = min(28, gap - 4)
        for i, other in enumerate(others):
            my = y + 6 + gap * (i + .5)
            self.face(cr, other.role, MEMBER_PET.get(other.state, 'idle'), mx, my, size,
                      alpha * (1 if other.busy else .35))
            if other.steps:
                self.hits.append(('member', (s.sid, other.role), mx - 16, my - gap / 2, 32, gap))
            elif other.role != MAIN_ROLE:
                self.hits.append(('brief', (s.sid, other.role), mx - 16, my - gap / 2, 32, gap))

    def draw_rows(self, cr, x0, w, top, alpha, rows, limit):
        """Una fila por alerta: su punto, de quién es y qué pasa."""
        left, right = x0 + 14, x0 + w - 14
        cr.set_source_rgba(*themes.glow(), .08 * alpha)
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
                cr.set_source_rgba(*themes.glow(), .07 * alpha)
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
        cr.set_source_rgba(*themes.glow(), .05 * alpha)
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

    def draw_reply_chips(self, cr, x0, w, top, alpha):
        """Una pastilla por respuesta de un agente que espera, con su color: un
        clic pasa a leer esa."""
        replies = self.replies()
        shown = self.board_card()
        x, right = x0 + 14, x0 + w - 14
        room = (right - x - 6 * (len(replies) - 1)) / len(replies)
        for i, s in enumerate(replies):
            color = mascot.rgba(mascot.accent(s.tint))[:3]
            label = f'{s.where.replace("elyares-", "")} · {s.proj}'
            layout = self._layout(cr, label, FONT_CODE, room - 26)
            lw, lh = layout.get_pixel_size()
            cw = min(room, lw + 26)
            key = f'rp:{i}'
            self.buttons[key] = (x, top, cw, REPLY_CHIPS_H - 4)
            now = s is shown
            over = self.over(x, top, cw, REPLY_CHIPS_H - 4)
            mascot.rrect(cr, x, top, cw, REPLY_CHIPS_H - 4, 8)
            cr.set_source_rgba(*(color if now else (1, 1, 1)), (.28 if now else .12 if over else .05) * alpha)
            cr.fill()
            cr.arc(x + 11, top + (REPLY_CHIPS_H - 4) / 2, 3.5, 0, 2 * math.pi)
            cr.set_source_rgba(*color, alpha)
            cr.fill()
            cr.move_to(x + 20, top + (REPLY_CHIPS_H - 4 - lh) / 2)
            cr.set_source_rgba(*((1, 1, 1) if now or over else rgb(self.colors['dim'])), alpha)
            PangoCairo.show_layout(cr, layout)
            x += cw + 6

    def draw_card(self, cr, x0, w, top, height, alpha, s=None):
        """La ficha de una alerta: su detalle y, debajo, sus botones."""
        s = s or self.view.session
        self.card_span = (top, top + height)
        left, right = x0 + 14, x0 + w - 14
        body = height - CARD_BUTTONS
        if body:
            if s.tint:
                # La respuesta de un agente: con su color, como sus bloques de código.
                self.draw_tinted(cr, left, top + 2, right - left, body - 6, mascot.rgba(mascot.accent(s.tint))[:3],
                                 alpha, 10)
            else:
                mascot.rrect(cr, left, top + 2, right - left, body - 6, 10)
                cr.set_source_rgba(*themes.glow(), .05 * alpha)
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
                cr.set_source_rgba(*(mascot.rgba(mascot.accent(s.tint))[:3] if s.tint else rgb(self.colors['path'])), alpha)
                PangoCairo.show_layout(cr, where)
                y += PREVIEW_HEAD
            for text in (s.lines[:REPLY_LINES] if s.reply else s.lines):
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
            # Tan ancho como pida su texto: «Ver respuesta» no cabe en el de siempre.
            bw = max(BUTTON_W, self._layout(cr, label, FONT_BUTTON).get_pixel_size()[0] + 24)
            x -= bw
            self.draw_button(cr, key, label, x, y, n == 0 and key != 'dismiss', alpha, bw)
            x -= BUTTON_GAP

    def draw_pills(self, cr, x0, w, bottom, alpha):
        """Una pastilla por fuente, pegadas al borde de abajo, y al final la
        de los atajos de elyares-engineer."""
        left, right = x0 + 18, x0 + w - 18
        top = bottom - PILLS_H
        cr.set_source_rgba(*themes.glow(), .08 * alpha)
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
            cr.set_source_rgba(*themes.glow(), (.13 if over else .07) * alpha)
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
        # La de los atajos no es una fuente: va sin punto, al otro extremo, y
        # a su lado la del chat.
        layout = self._layout(cr, '?', FONT_PILL)
        lw, lh = layout.get_pixel_size()
        pw = lw + 16
        x = right - pw
        if not (self.frame is not None and self.windowed):     # en la ventana son las vistas de la barra de título
            chat = self._layout(cr, 'Chat', FONT_PILL)
            cw, ch = chat.get_pixel_size()
            cpw = cw + 20
            cx = x - PILL_GAP - cpw
            over_chat = cx <= px <= cx + cpw and y <= py <= y + PILL_H
            mascot.rrect(cr, cx, y, cpw, PILL_H, PILL_H / 2)
            accent = mascot.rgba(mascot.accent('engineer'))[:3]
            cr.set_source_rgba(*accent, (.30 if over_chat else .18) * alpha)
            cr.fill()
            cr.move_to(cx + (cpw - cw) / 2, y + (PILL_H - ch) / 2)
            cr.set_source_rgba(*TITLE_COLOR[:3], alpha)
            PangoCairo.show_layout(cr, chat)
            # Y, antes, la de los proyectos, para empezar en cualquiera.
            plus = self._layout(cr, '+', FONT_PILL)
            qw, qh = plus.get_pixel_size()
            qpw = qw + 16
            qx = cx - PILL_GAP - qpw
            over_plus = qx <= px <= qx + qpw and y <= py <= y + PILL_H
            mascot.rrect(cr, qx, y, qpw, PILL_H, PILL_H / 2)
            cr.set_source_rgba(*themes.glow(), (.13 if over_plus else .07) * alpha)
            cr.fill()
            cr.move_to(qx + (qpw - qw) / 2, y + (PILL_H - qh) / 2)
            cr.set_source_rgba(*TITLE_COLOR[:3], alpha)
            PangoCairo.show_layout(cr, plus)
            self.pills.append((projectview.PROJECTS_PILL, qx, y, qpw, PILL_H))
            # Y la de los workflows: sus cadenas de agentes.
            flows = self._layout(cr, 'Flujos', FONT_PILL)
            fw, fh = flows.get_pixel_size()
            fpw = fw + 16
            fx = qx - PILL_GAP - fpw
            over_flows = fx <= px <= fx + fpw and y <= py <= y + PILL_H
            mascot.rrect(cr, fx, y, fpw, PILL_H, PILL_H / 2)
            cr.set_source_rgba(*themes.glow(), (.13 if over_flows else .07) * alpha)
            cr.fill()
            cr.move_to(fx + (fpw - fw) / 2, y + (PILL_H - fh) / 2)
            cr.set_source_rgba(*TITLE_COLOR[:3], alpha)
            PangoCairo.show_layout(cr, flows)
            self.pills.insert(len(self.pills) - 1, (workflowview.WF_PILL, fx, y, fpw, PILL_H))    # en su orden, de izquierda a derecha
            self.pills.append((CHAT_PILL, cx, y, cpw, PILL_H))
        over = x <= px <= x + pw and y <= py <= y + PILL_H
        mascot.rrect(cr, x, y, pw, PILL_H, PILL_H / 2)
        cr.set_source_rgba(*themes.glow(), (.13 if over else .07) * alpha)
        cr.fill()
        cr.move_to(x + (pw - lw) / 2, y + (PILL_H - lh) / 2)
        cr.set_source_rgba(*TITLE_COLOR[:3], alpha)
        PangoCairo.show_layout(cr, layout)
        self.pills.append((commands.HELP, x, y, pw, PILL_H))
        if over:
            self.tip = (commands.HELP, x + pw / 2, alpha)

    def draw_tip(self, cr, width, top, now):
        """La burbuja de una pastilla: un popover como los de macOS, que sale
        debajo de la isla mientras el cursor está sobre ella, sin clic, con
        la flecha hacia la pastilla. Arriba, cómo está la fuente; debajo, sus
        comandos en dos columnas. Lleva sombra y un filo claro arriba; en
        modo vidrio es translúcida, con un brillo que baja desde arriba.

        No sale ni se va de golpe: nace un poco más chica en la punta de la
        flecha y crece hasta asentarse, y al quitar el cursor se encoge con
        lo último que decía. De una pastilla a la de al lado se desliza."""
        showing = self.tip is not None
        if showing:
            self.tip_last = self.tip
        key, cx, alpha = self.tip_last
        if key != self.tip_key:
            self.tip_key = key
            self.tip_pop = min(self.tip_pop, TIP_SWAP)
            # Los comandos se leen al salir la burbuja: un cambio en el archivo
            # o en los atajos de Hyprland se ve sin reiniciar nada.
            self.tip_ref = commands.reference(
                key, commands.load(), hypr.binds() if key == commands.HELP else None)
        # El primer cuadro no sabe cuánto pasó desde el anterior: avanza uno.
        dt = clamp(now - self.tip_at, 0, .05) if self.tip_pop else 1 / 60
        self.tip_at = now
        self.tip_pop = clamp(self.tip_pop + (dt / TIP_IN if showing else -dt / TIP_OUT))
        if not self.tip_pop:
            self.tip_key = self.tip_cx = None
            return
        if self.tip_cx is None:
            self.tip_cx = cx
        self.tip_cx += (cx - self.tip_cx) * (1 - math.exp(-TIP_GLIDE * dt))
        cx = self.tip_cx
        pop = self.tip_pop
        alpha *= clamp(pop * 1.6)
        back = 1 + (TIP_BACK + 1) * (pop - 1) ** 3 + TIP_BACK * (pop - 1) ** 2
        scale = TIP_SMALL + (1 - TIP_SMALL) * back
        title, rows = self.source_tip(key)
        room = width - 8 - 2 * TIP_PAD          # lo más ancha que puede ser por dentro
        inner = TIP_W - 2 * TIP_PAD
        blocks = self.tip_blocks(cr, title, rows, inner, room)
        # Lo que ocupa cada bloque hacia abajo, con su aire.
        steps = [gap + bh + after for _, bh, gap, after, _ in blocks]
        while sum(steps) + 2 * TIP_PAD > TIP_ROOM - TIP_GAP and len(blocks) > 2:
            # Más comandos de los que caben en la ventana: se dice que hay más.
            more = self._layout(cr, '…', FONT_TIP)
            blocks[-2:] = [self.tip_line(cr, more, rgb(self.ink('text', TIP_SOFT)))]
            steps[-2:] = [blocks[-1][1] + 3]
        w = max(bw for bw, *_ in blocks) + 2 * TIP_PAD
        h = sum(steps) - blocks[-1][3] + 2 * TIP_PAD
        x, y = clamp(cx - w / 2, 4, width - w - 4), top + TIP_GAP
        self.tip_size = (w, h)
        glass = self.settings['glass']
        # La flecha apunta a la pastilla aunque la burbuja no quepa centrada en ella.
        tx, tip_y = clamp(cx, 12, width - 12), top + TIP_TAIL_GAP
        base = clamp(tx, x + TIP_R + TIP_TAIL, x + w - TIP_R - TIP_TAIL)
        cr.save()
        cr.translate(tx, tip_y)
        cr.scale(scale, scale)
        cr.translate(-tx, -tip_y)
        mascot.balloon(cr, x, y, w, h, TIP_R, base, TIP_TAIL, tx, tip_y)
        shape = cr.copy_path()
        cr.new_path()
        self.tip_shadow(cr, shape, top, width, alpha)
        cr.append_path(shape)
        # Con comandos se lee más rato: en vidrio va más opaca que la isla.
        cr.set_source_rgba(*ISLAND_BG[:3], (TIP_GLASS_ALPHA if glass else ISLAND_BG[3]) * alpha)
        cr.fill_preserve()
        if glass:
            sheen = cairo.LinearGradient(0, y, 0, y + h / 2)
            sheen.add_color_stop_rgba(0, *themes.glow(), TIP_SHEEN * alpha)
            sheen.add_color_stop_rgba(1, *themes.glow(), 0)
            cr.set_source(sheen)
            cr.fill_preserve()
        edge = cairo.LinearGradient(0, tip_y, 0, y + h)
        for stop, light in enumerate(TIP_EDGE):
            edge.add_color_stop_rgba(stop, *themes.glow(), light * alpha)
        cr.set_source(edge)
        cr.set_line_width(1)
        cr.stroke()
        ty = y + TIP_PAD
        for (_, _, gap, _, draw), step in zip(blocks, steps):
            if gap >= TIP_HEAD_GAP:
                cr.set_source_rgba(*themes.glow(), TIP_RULE * alpha)
                cr.rectangle(x + TIP_PAD, ty + gap // 2 - 2, w - 2 * TIP_PAD, 1)
                cr.fill()
            draw(x + TIP_PAD, ty + gap, w - 2 * TIP_PAD, alpha, glass)
            ty += step
        cr.restore()

    def tip_blocks(self, cr, title, rows, inner, room):
        """Las filas de la burbuja, medidas y listas para pintar, de arriba
        abajo: [(ancho, alto, aire arriba, aire abajo, pinta)], donde
        `pinta(x, y, ancho, alpha, vidrio)` dibuja el bloque."""
        soft = rgb(self.ink('text', TIP_SOFT))
        # Un comando lleva cada parte en su color; un atajo o un clic, uno solo.
        cmds, plain = [], None
        for row in rows:
            if row[0] == 'head':
                plain = TIP_PLAIN.get(row[1])
            elif row[0] == 'cmd':
                parts = [(row[1], plain)] if plain else paint.command(row[1])
                cmds.append(self._layout(cr, row[1], FONT_TIP, markup=self.tip_markup(parts)))
        col = max((layout.get_pixel_size()[0] for layout in cmds), default=0) + TIP_COL_GAP
        cmds = iter(cmds)
        status = next((row for row in rows if row[0] == 'status'), None)
        blocks = [self.tip_title(cr, title, status, inner)]
        for row in rows:
            if row[0] == 'text':
                # Una causa o un resumen largo se parte en líneas antes que cortarse.
                markup = row[3] if len(row) > 3 else None
                layout = self._layout(cr, row[1], FONT_TIP, inner, TIP_TEXT_LINES, markup=markup)
                blocks.append(self.tip_line(cr, layout, None if markup else row[2]))
            elif row[0] == 'chips':
                blocks.append(self.tip_chips(cr, row[1], inner))
            elif row[0] == 'items':
                blocks.append(self.tip_items(cr, row[1], row[2], inner))
            elif row[0] == 'stats':
                blocks += [self.tip_stats(cr, row[1][i:i + TIP_STATS_ROW], i, inner)
                           for i in range(0, len(row[1]), TIP_STATS_ROW)]
            elif row[0] == 'head':
                layout = self._layout(cr, row[1].upper(), FONT_PILL)
                blocks.append(self.tip_line(cr, layout, rgb(self.ink('head')), gap=TIP_HEAD_GAP))
            elif row[0] == 'cmd':
                # Los comandos van más juntos.
                what = self._layout(cr, row[2], FONT_TIP, room - col)
                blocks.append(self.tip_line(cr, next(cmds), None, after=1, right=(what, col, soft)))
        return blocks

    def tip_line(self, cr, layout, color, gap=0, after=3, right=None):
        """Un texto de la burbuja como bloque. `right` es lo que va en la
        segunda columna: (texto, dónde empieza, color)."""
        w, h = layout.get_pixel_size()
        if right:
            w = right[1] + right[0].get_pixel_size()[0]

        def draw(x, y, _width, alpha, glass):
            self.tip_text(cr, layout, x, y, color, alpha, glass)
            if right:
                self.tip_text(cr, right[0], x + right[1], y, right[2], alpha, glass)
        return w, h, gap, after, draw

    def tip_title(self, cr, title, status, inner):
        """El título de la burbuja y, al otro lado, cómo está la fuente."""
        layout = self._layout(cr, title, FONT_TITLE, inner)
        tw, th = layout.get_pixel_size()
        if not status:
            return self.tip_line(cr, layout, TITLE_COLOR[:3], after=5)
        cw, ch, chip = self.tip_chip(cr, status[1], status[2], dot=True)
        h = max(th, ch)

        def draw(x, y, width, alpha, glass):
            self.tip_text(cr, layout, x, y + (h - th) / 2, TITLE_COLOR[:3], alpha, glass)
            chip(x + width - cw, y + (h - ch) / 2, alpha, glass)
        return tw + TIP_COL_GAP + cw, h, 0, 6, draw

    def tip_chip(self, cr, label, role, dot=False):
        """Una etiqueta de la burbuja, teñida de su color: (ancho, alto,
        pinta). Con `dot` lleva delante el punto de la fuente."""
        layout = self._layout(cr, label, FONT_PILL)
        lw, lh = layout.get_pixel_size()
        color = rgb(self.ink(role))
        lead = TIP_CHIP_DOT if dot else 0
        w, h = lw + 2 * TIP_CHIP_PAD + lead, lh + 2 * TIP_CHIP_PAD_Y

        def draw(x, y, alpha, glass):
            mascot.rrect(cr, x, y, w, h, h / 2)
            cr.set_source_rgba(*color, TIP_CHIP_FILL * alpha)
            cr.fill_preserve()
            cr.set_source_rgba(*color, TIP_CHIP_EDGE * alpha)
            cr.set_line_width(1)
            cr.stroke()
            if dot:
                cr.arc(x + TIP_CHIP_PAD + 3, y + h / 2, 3, 0, 2 * math.pi)
                cr.set_source_rgba(*color, alpha)
                cr.fill()
            self.tip_text(cr, layout, x + TIP_CHIP_PAD + lead, y + TIP_CHIP_PAD_Y, color, alpha, glass)
        return w, h, draw

    def tip_chips(self, cr, chips, inner):
        """Unas etiquetas en fila; las que no caben pasan a la fila de abajo."""
        placed, x, y, h, wide = [], 0, 0, 0, 0
        for label, role in chips:
            cw, h, chip = self.tip_chip(cr, label, role)
            if x and x + cw > inner:
                x, y = 0, y + h + TIP_CHIP_GAP
            placed.append((x, y, chip))
            wide = max(wide, x + cw)
            x += cw + TIP_CHIP_GAP

        def draw(x0, y0, _width, alpha, glass):
            for dx, dy, chip in placed:
                chip(x0 + dx, y0 + dy, alpha, glass)
        return wide, y + h, 1, 7, draw

    def tip_items(self, cr, items, more, inner):
        """Las cosas que una fuente nombra una por una (los PRs de GitHub):
        arriba, de qué proyecto es y su número, con su punto y su nota (cómo
        van sus checks) en el color de su tono; debajo, su título y de qué
        cuenta es. `more` es cuántas no caben: se dice."""
        soft, dim = rgb(self.ink('text', TIP_SOFT)), rgb(self.ink('dim', TIP_SOFT))
        rows, y = [], 0
        for it in items:
            role = TIP_ITEM_ROLES.get(it.get('tone'), 'dim')
            color = rgb(self.ink(role))
            note = self._layout(cr, str(it.get('note') or ''), FONT_PILL)
            nw, nh = note.get_pixel_size()
            number = f' #{it["number"]}' if it.get('number') else ''
            head = self._layout(cr, it['where'] + number, FONT_ROW, inner - TIP_ITEM_DOT - nw - TIP_COL_GAP,
                                markup=self.tip_markup([(it['where'], 'path'), (number, 'num')]))
            who = f' · {it["who"]}' if it.get('who') else ''
            title = str(it.get('title') or '')
            sub = self._layout(cr, title + who, FONT_TIP, inner - TIP_ITEM_DOT,
                               markup=self.tip_markup([(title, 'arg'), (who, 'dim')]))
            hh = max(head.get_pixel_size()[1], nh)
            rows.append((y, head, note, nw, nh, hh, sub, color))
            y += hh + sub.get_pixel_size()[1] + TIP_ITEM_GAP
        tail = (self._layout(cr, f'y {more} más' if more > 1 else 'y 1 más', FONT_TIP)
                if more > 0 else None)
        h = y - TIP_ITEM_GAP + (tail.get_pixel_size()[1] + 2 if tail else 0)

        def draw(x, y0, width, alpha, glass):
            for dy, head, note, nw, nh, hh, sub, color in rows:
                top = y0 + dy
                cr.arc(x + 4, top + hh / 2, 3.5, 0, 2 * math.pi)
                cr.set_source_rgba(*color, alpha)
                cr.fill()
                self.tip_text(cr, head, x + TIP_ITEM_DOT, top, None, alpha, glass)
                self.tip_text(cr, note, x + width - nw, top + (hh - nh) / 2, color, alpha, glass)
                self.tip_text(cr, sub, x + TIP_ITEM_DOT, top + hh, None, alpha, glass)
            if tail:
                self.tip_text(cr, tail, x + TIP_ITEM_DOT, y0 + y - TIP_ITEM_GAP + 2, soft, alpha, glass)
        return inner, h, 2, 7, draw

    def tip_stats(self, cr, stats, first, inner):
        """Una fila de fichas, cada una con su cifra en grande y debajo su
        nombre, todas del mismo ancho: se reparten el de la burbuja, y una
        sola se queda con la mitad. `first` es el turno de color de la primera."""
        cols = max(len(stats), 2)
        room = (inner - (cols - 1) * TIP_STAT_GAP) / cols - 2 * TIP_STAT_PAD
        tiles = [(self._layout(cr, value, FONT_STAT, room),
                  self._layout(cr, label, FONT_PILL, room, 2) if label else None,
                  rgb(self.ink(TIP_STAT_ROLES[(first + i) % len(TIP_STAT_ROLES)])))
                 for i, (value, label) in enumerate(stats)]
        big = max(value.get_pixel_size()[1] for value, _, _ in tiles)
        small = max((label.get_pixel_size()[1] for _, label, _ in tiles if label), default=0)
        h = 2 * TIP_STAT_PAD + big + small - 3
        name = rgb(self.ink('arg'))

        def draw(x, y, width, alpha, glass):
            tw = (width - (cols - 1) * TIP_STAT_GAP) / cols
            for i, (value, label, color) in enumerate(tiles):
                tx = x + i * (tw + TIP_STAT_GAP)
                mascot.rrect(cr, tx, y, tw, h, TIP_STAT_R)
                cr.set_source_rgba(*color, TIP_STAT_FILL * alpha)
                cr.fill_preserve()
                cr.set_source_rgba(*color, TIP_STAT_EDGE * alpha)
                cr.set_line_width(1)
                cr.stroke()
                self.tip_text(cr, value, tx + TIP_STAT_PAD, y + TIP_STAT_PAD - 3, color, alpha, glass)
                if label:
                    self.tip_text(cr, label, tx + TIP_STAT_PAD, y + TIP_STAT_PAD - 3 + big, name, alpha, glass)
        return inner, h, 2, 7, draw

    def tip_text(self, cr, layout, x, y, color, alpha, shadow):
        """Un texto de la burbuja; con `color` None, el que trae sus colores.
        Sobre vidrio lleva debajo su sombra: sin ella se pierde contra lo que
        haya detrás de la burbuja."""
        if shadow:
            under = layout.copy()
            under.set_attributes(None)
            cr.move_to(x, y + 1)
            cr.set_source_rgba(0, 0, 0, TIP_INK_SHADOW * alpha)
            PangoCairo.show_layout(cr, under)
        cr.move_to(x, y)
        if color is None:
            self._show(cr, layout, alpha)
        else:
            cr.set_source_rgba(*color, alpha)
            PangoCairo.show_layout(cr, layout)

    @staticmethod
    def tip_shadow(cr, shape, top, width, alpha):
        """La sombra de la burbuja: suave y caída hacia abajo. Solo por fuera
        de ella, para no oscurecer el vidrio, y de la isla para abajo."""
        cr.save()
        cr.rectangle(0, top, width, WIN_H)
        cr.append_path(shape)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.clip()
        cr.translate(0, TIP_SHADOW_DROP)
        cr.append_path(shape)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_source_rgba(0, 0, 0, TIP_SHADOW_ALPHA * alpha)
        for spread in range(TIP_SHADOW, 0, -1):
            cr.set_line_width(2 * spread)
            cr.stroke_preserve()
        cr.new_path()
        cr.restore()

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
        layout.set_font_description(Pango.FontDescription.from_string(fonts.pick(font)))
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
            # Los botones de una ficha van por su número: no son los del chat.
            if isinstance(key, str) and key.startswith('chat-'):
                self.on_chat_button(key)
                return
            if isinstance(key, str) and key.startswith('rp:'):
                # Otra de las respuestas de los agentes, para leerla en la ficha.
                replies = self.replies()
                if int(key[3:]) < len(replies):
                    self.reply_pick, self.pin = replies[int(key[3:])].sid, ''
                    self.refresh()
                    self.ensure_tick()
                return
            if key in ('allow', 'deny'):
                asking = self.asking()
                if asking is None:
                    continue
                self.model.decide(asking, key == 'allow')
                self.refresh()
            else:
                shown = self.board_card() if self.target() == 'board' else None
                self.act(shown or self.view.session, key)
            return
        if self.card_span and self.card_span[0] <= y < self.card_span[1]:
            # En la ficha solo cuentan sus botones: un clic que falla uno no
            # debe abrir el navegador y descartar la alerta.
            return
        for key, bx, by, bw, bh in self.pills:
            if bx <= x <= bx + bw and by <= y <= by + bh:
                # Claude no se apaga desde aquí: sin sus hooks no hay nada que mostrar.
                # Y la de los atajos no es una fuente, ni la del chat.
                if key in sources.PREFIXES:
                    self.toggle_source(key)
                elif key == CHAT_PILL:
                    self.open_chat(typing=True)
                elif key == projectview.PROJECTS_PILL:
                    self.toggle_projects()
                elif key == workflowview.WF_PILL:
                    self.toggle_workflows()
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
        if self.windowed or self.target() in ('board', 'chat', 'projects') or (self.rows and y > self.rows[0][1]):
            return                      # en la ventana, un clic en el vacío no hace nada
        if x < x0 + 12 + PET + 4:
            self.poke()
        elif self.view.session:
            self.go(self.view.session)

    def on_hit(self, kind, key):
        """Un clic en el tablero: en una pestaña, en uno de los cuatro, en los
        enlaces de un desglose o en su mini chat. O en el chat, o en el panel
        de proyectos y sus atajos para empezar en uno."""
        if kind in ('project', 'projects', 'start'):
            self.on_project_hit(kind, key)
            return
        if kind == 'chat':
            self.on_chat_hit(key)
            return
        if kind == 'tab':
            if key == self.tab:
                # La elegida ya se ve: el clic lleva a su pane, como antes el
                # de la cabecera. La de un chat no tiene pane: abre su conversación.
                s = self.tab_session()
                c = self.chat_of(s, s.main_agent if s.owner != MAIN_ROLE else '') if s is not None else None
                if c is not None:
                    self.show_chat(c, typing=True)
                elif s is not None:
                    self.go(s)
                return
            self.tab, self.focus = key, None
            self.tab_manual = True
        elif kind == 'member':
            self.focus = key
        elif kind == 'brief':
            # Uno de los tres, libre, o la caja de su desglose: a escribirle.
            if key is not None:
                self.focus = key
            self.brief()
            return
        elif kind == 'back':
            self.focus = None
        elif kind == 'jump':
            s = self.model.sessions.get(key)
            if s is not None:
                self.go(s)
            return
        elif kind == 'talk':
            # Desde un desglose: la conversación de esa sesión (o la del
            # encargo de ese agente) y, si no tiene, la del proyecto de la pestaña.
            s = self.tab_session()
            c = self.chat_of(s, key) if s is not None else None
            if c is not None:
                self.show_chat(c, typing=True)
            else:
                self.open_chat(typing=True, agent=key, cwd=self.tab_place(s) if s is not None else None)
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
            elif action.get('chat'):
                self.chat_show(action['chat'])
            elif action.get('workflows'):
                self.open_workflows('run')
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
