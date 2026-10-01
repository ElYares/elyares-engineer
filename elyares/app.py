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
vidrio (fondo translúcido; el desenfoque lo pone una regla de Hyprland).

Además de las sesiones de Claude muestra alertas de DevHerd Observe (ver
`devherd.py`): se ven como una sesión más y el clic abre su URL.

Abierta a mano y con varias sesiones, debajo de la más urgente sale una fila
por cada una de las demás, también las que están en reposo; un clic en la fila
lleva a su pane de tmux.
"""

import math
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

from . import actions, devherd, hypr, ipc, mascot, settings, store, theme  # noqa: E402
from .state import Model  # noqa: E402

MAX_ROWS = 4          # filas de la lista: las demás sesiones, sin la principal
ROW_H, LIST_PAD = 28, 10
OPEN_H = 88
DETAIL_LINES = 4      # líneas del detalle cuando se muestra entero
MAX_EXTRA = 54        # alto de más que puede pedir el detalle entero
# 8: margen del rebote
WIN_W, WIN_H = 480, OPEN_H + MAX_EXTRA + MAX_ROWS * ROW_H + LIST_PAD + 8
SIZES = {'off': (120, 0), 'hidden': (120, 6), 'petit': (56, 34), 'peek': (92, 80),
         'open': (440, OPEN_H), 'ask': (440, 108)}
HOVER_STRIP = 10     # alto de la franja que detecta el ratón cuando está escondida
PET = 72             # lado del cuadro de la mascota
PET_SCALE = PET / 260
TEXT_INSET = 12 + PET + 10 + 18   # lo que le quitan al texto la mascota y los márgenes
ISLAND_BG = (5 / 255, 6 / 255, 8 / 255, .97)
GLASS_ALPHA, GLASS_EDGE = .5, .16    # modo vidrio: fondo translúcido y filo claro
TITLE_COLOR = (.95, .96, 1, 1)
DETAIL_COLOR = (.66, .71, .84, 1)
MUTED_COLOR = (.44, .49, .63, 1)
FONT_TITLE = 'Sans Semi-Bold 11'
FONT_DETAIL = 'JetBrainsMono Nerd Font 9'
FONT_BUTTON = 'Sans Semi-Bold 10'
FONT_ROW = 'Sans Semi-Bold 10'
ROW_NAME_W = 130     # ancho de la columna del proyecto en la lista
STATE_COLORS = {'permission': 'red', 'alert': 'red', 'waiting': 'yellow', 'done': 'green',
                'working': 'accent'}
BUTTON_H, BUTTON_W, BUTTON_GAP = 26, 84, 8
ALLOW_BG, ALLOW_FG = (.95, .96, 1), (5 / 255, 6 / 255, 8 / 255)
DENY_BG, DENY_FG = (1, 1, 1), (.95, .96, 1)
SPRING_K, SPRING_C = 220.0, 22.0   # rigidez y amortiguación: rebota un poquito
LOOK_EVERY = 1 / 15                # frecuencia con la que se pregunta el cursor
IDLE_FPS = 12                      # asomada y quieta: ~3% de CPU en vez de ~8% a 30
KEY_OPEN_SECS = 6                  # abierta con el teclado: se cierra sola


def ago(secs):
    mins = int(secs // 60)
    if mins < 1:
        return 'hace un momento'
    return f'hace {mins} min' if mins < 60 else f'hace {mins // 60} h'


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class Island:
    def __init__(self, app):
        self.model = Model()
        self.model.restore(store.load())
        self.saved = self.model.dump()
        self.view = self.model.view()
        self.title, self.detail = '', ''
        self.dnd = False
        self.hover = False
        self.settings = settings.load()
        mascot.set_accent(theme.accent())
        self.expanded = False           # abierta a mano, con un clic o con elyares-ctl
        self.collapse_id = 0
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
        self.buttons = {}               # 'allow'/'deny' -> (x, y, w, h), del último dibujo
        self.rows = []                  # (sesión, y, alto) de la lista, del último dibujo
        self.list_layout = False        # la cabecera se queda arriba mientras hay lista
        self.wrap = (None, 0)           # (detalle, alto de más que pide entero)
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
        win.set_child(da)
        self.da = da

        css = Gtk.CssProvider()
        css.load_from_string('window, window.background { background: transparent; }')
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        win.present()
        self.update_region()

        ipc.serve(lambda msg, req: GLib.idle_add(self.on_message, msg, req),
                  lambda req: GLib.idle_add(self.on_gone, req))
        hypr.listen(lambda name: GLib.idle_add(self.on_focused_monitor, name))
        if self.settings['devherd']:
            devherd.watch(lambda msg: GLib.idle_add(self.on_message, msg, None))
        GLib.timeout_add_seconds(3, self.poll_dnd)
        # "Terminó" y "esperando" caducan solos aunque no lleguen más eventos.
        GLib.timeout_add_seconds(1, self.on_second)
        if self.model.sessions:
            # Sesiones del daemon anterior: algún pane pudo cerrarse entre tanto.
            self.refresh()
            self.check_panes()

    # ── estado ───────────────────────────────────────────────────────────────

    def on_message(self, msg, req):
        if 'control' in msg:
            self.on_control(msg['control'])
            return GLib.SOURCE_REMOVE
        self.model.handle(msg, req)
        self.refresh()
        return GLib.SOURCE_REMOVE

    def on_gone(self, req):
        self.model.gone(req)
        self.refresh()
        return GLib.SOURCE_REMOVE

    def on_second(self):
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
        v = self.model.view()
        if self.dnd and v.mode != 'hidden' and v.pet != 'permission':
            v.mode, v.pet = 'peek', 'sleep'
        if v.pet != self.pet_state:
            self.pet_state, self.pet_since = v.pet, time.monotonic()
        if v.title:
            self.title, self.detail = v.title, v.detail
        elif self.expanded and v.others:
            # Abierta a mano sin nada corriendo: la cabecera lo dice y la lista
            # trae las sesiones en reposo.
            self.title, self.detail = 'Sin sesiones activas', f'{len(v.others)} en reposo'
        changed = v.mode != self.view.mode or v.key != self.view.key
        self.view = v
        if changed or v.mode != 'hidden':
            self.ensure_tick()
        data = self.model.dump()
        if data != self.saved:
            self.saved = data
            store.save(data)

    def on_control(self, order):
        if order == 'hide':
            self.off = not self.off
            self.collapse()
        elif order == 'compact':
            self.toggle_compact()
        elif order == 'theme':
            mascot.set_accent(theme.accent())
            self.ensure_tick()
        elif order == 'glass':
            self.settings['glass'] = not self.settings['glass']
            settings.save(self.settings)
            self.ensure_tick()
        elif order == 'open':
            if self.expanded and not self.off:
                self.collapse()
            else:
                self.off = False
                self.expand(KEY_OPEN_SECS)

    def expand(self, secs=None):
        """Abre la isla a mano. Con secs se cierra sola si el ratón no está encima."""
        if self.collapse_id:
            GLib.source_remove(self.collapse_id)
            self.collapse_id = 0
        self.expanded = True
        if secs:
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
        self.expanded = False
        self.ensure_tick()

    def on_collapse(self):
        self.collapse_id = 0
        # Con el ratón encima se queda abierta; la cierra el 'leave'.
        if not self.hover:
            self.collapse()
        return GLib.SOURCE_REMOVE

    def toggle_compact(self):
        self.settings['compact'] = not self.settings['compact']
        settings.save(self.settings)
        self.collapse()

    def target(self):
        if self.off:
            return 'off'
        mode = self.view.mode
        if mode == 'open' and self.view.ask:
            return 'ask'
        if self.expanded:
            if self.view.others:
                return 'list'
            return 'open' if self.view.session else 'peek'
        # Un permiso se abre solo aunque esté compacta: hay que contestarlo.
        if self.settings['compact'] and self.view.pet != 'permission':
            return 'petit' if mode != 'hidden' or self.hover else 'hidden'
        if self.hover:
            if mode == 'hidden':
                mode = 'peek'
            elif mode == 'peek' and self.view.session:
                mode = 'open'
            if mode == 'open' and self.view.others:
                mode = 'list'
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
        if self.wrap[0] != self.detail:
            width = SIZES['open'][0] - TEXT_INSET
            one = self._shape(self.da.create_pango_layout('X'), FONT_DETAIL)
            full = self._shape(self.da.create_pango_layout(self.detail or ''), FONT_DETAIL,
                               width, DETAIL_LINES)
            more = full.get_pixel_size()[1] - one.get_pixel_size()[1]
            self.wrap = (self.detail, int(clamp(more, 0, MAX_EXTRA)))
        return self.wrap[1]

    def goal(self):
        """Tamaño al que va la isla: el del modo, más el detalle entero y las filas."""
        mode = self.target()
        if mode == 'list':
            w, h = SIZES['open']
            return w, (h + self.extra(mode) + LIST_PAD
                       + ROW_H * min(MAX_ROWS, len(self.view.others)))
        w, h = SIZES[mode]
        return w, h + self.extra(mode)

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
        # Con lista o con el detalle entero, la cabecera (mascota y texto) se
        # queda arriba y lo demás va debajo. El diseño dura hasta que la isla
        # vuelve a su alto normal, para que la cabecera no brinque al cerrarse.
        mode = self.target()
        extra = self.extra(mode)
        head = OPEN_H + extra           # dónde termina la cabecera
        if mode == 'list' or (mode == 'open' and extra):
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
            cx = x0 + min(w / 2, 12 + PET / 2)
            # La capa intermedia solo hace falta mientras aparece o desaparece.
            fading = pet_alpha < 1
            if fading:
                cr.push_group()
            else:
                cr.save()
            cr.translate(cx, h / 2 + 5 * pet_size)
            cr.scale(PET_SCALE * pet_size, PET_SCALE * pet_size)
            mascot.draw(cr, state, age, now, tuple(self.look), now < self.blink_until)
            if fading:
                cr.pop_group_to_source()
                cr.paint_with_alpha(pet_alpha)
            else:
                cr.restore()

        # Con botones, el texto sube y deja la fila de abajo para ellos.
        ask_alpha = clamp((h - SIZES['open'][1]) / 16) if self.view.ask else 0.0
        mid = h / 2 - (h / 2 - 37) * ask_alpha
        text_alpha = clamp((w - 220) / 160) * clamp((h - 50) / 30)
        if text_alpha > 0 and self.title:
            tx = x0 + 12 + PET + 10
            right = x0 + w - 18
            if self.view.count > 1:
                badge = self._layout(cr, f'{self.view.count} sesiones', FONT_DETAIL)
                bw = badge.get_pixel_size()[0]
                cr.move_to(right - bw, mid - 17)
                cr.set_source_rgba(*MUTED_COLOR[:3], text_alpha)
                PangoCairo.show_layout(cr, badge)
                title_right = right - bw - 12
            else:
                title_right = right
            title = self._layout(cr, self.title, FONT_TITLE, title_right - tx)
            cr.move_to(tx, mid - 21)
            cr.set_source_rgba(*TITLE_COLOR[:3], text_alpha)
            PangoCairo.show_layout(cr, title)
            detail = self._layout(cr, self.detail, FONT_DETAIL, right - tx,
                                  DETAIL_LINES if extra else 1)
            cr.move_to(tx, mid + 3)
            cr.set_source_rgba(*DETAIL_COLOR[:3], text_alpha)
            PangoCairo.show_layout(cr, detail)
        self.buttons = {}
        if ask_alpha > 0 and text_alpha > 0:
            self.draw_buttons(cr, x0 + w - 18, h - 14, ask_alpha * text_alpha)
        self.rows = []
        if self.list_layout and self.view.others and full_h > head:
            self.draw_rows(cr, x0, w, head, clamp((full_h - head) / 20) * text_alpha)
        cr.restore()
        if edge:
            # El filo claro es lo que hace que el fondo translúcido se lea como vidrio.
            cr.append_path(edge)
            cr.set_source_rgba(1, 1, 1, GLASS_EDGE)
            cr.set_line_width(1)
            cr.stroke()

    def draw_rows(self, cr, x0, w, top, alpha):
        left, right = x0 + 14, x0 + w - 14
        cr.set_source_rgba(1, 1, 1, .08 * alpha)
        cr.rectangle(left + 4, top - 1, right - left - 8, 1)
        cr.fill()
        px, py = self.pointer or (-1, -1)
        others = self.view.others
        # Si no caben todas, la última fila dice cuántas faltan.
        shown = others if len(others) <= MAX_ROWS else others[:MAX_ROWS - 1]
        if len(others) > len(shown):
            more = self._layout(cr, f'y {len(others) - len(shown)} más', FONT_DETAIL)
            y = top + 3 + len(shown) * ROW_H
            cr.move_to(left + 28, y + (ROW_H - more.get_pixel_size()[1]) / 2)
            cr.set_source_rgba(*MUTED_COLOR[:3], alpha)
            PangoCairo.show_layout(cr, more)
        for i, s in enumerate(shown):
            y = top + 3 + i * ROW_H
            self.rows.append((s, y, ROW_H))
            if left <= px <= right and y <= py < y + ROW_H:
                mascot.rrect(cr, left, y + 1, right - left, ROW_H - 2, 8)
                cr.set_source_rgba(1, 1, 1, .07 * alpha)
                cr.fill()
            cr.new_sub_path()
            if s.state in STATE_COLORS:
                cr.arc(left + 14, y + ROW_H / 2, 3.5, 0, 2 * math.pi)
                cr.set_source_rgba(*mascot.rgba(STATE_COLORS[s.state], alpha))
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
            text = s.detail or f'En reposo {ago(time.monotonic() - s.updated)}'
            detail = self._layout(cr, text, FONT_DETAIL, right - 10 - dx)
            cr.move_to(dx, y + (ROW_H - detail.get_pixel_size()[1]) / 2)
            cr.set_source_rgba(*DETAIL_COLOR[:3], alpha)
            PangoCairo.show_layout(cr, detail)

    def draw_buttons(self, cr, right, bottom, alpha):
        y = bottom - BUTTON_H
        for key, label, x, bg, fg, fill in (
                ('allow', 'Permitir', right - BUTTON_W, ALLOW_BG, ALLOW_FG, .92),
                ('deny', 'Denegar', right - 2 * BUTTON_W - BUTTON_GAP, DENY_BG, DENY_FG, .10)):
            rect = (x, y, BUTTON_W, BUTTON_H)
            self.buttons[key] = rect
            px, py = self.pointer or (-1, -1)
            over = x <= px <= x + BUTTON_W and y <= py <= y + BUTTON_H
            r = BUTTON_H / 2
            cr.new_sub_path()
            cr.arc(x + r, y + r, r, math.pi / 2, 3 * math.pi / 2)
            cr.arc(x + BUTTON_W - r, y + r, r, -math.pi / 2, math.pi / 2)
            cr.close_path()
            cr.set_source_rgba(*bg, min(1, fill + (.08 if over else 0)) * alpha)
            cr.fill()
            layout = self._layout(cr, label, FONT_BUTTON)
            lw, lh = layout.get_pixel_size()
            cr.move_to(x + (BUTTON_W - lw) / 2, y + (BUTTON_H - lh) / 2)
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
    def _layout(cls, cr, text, font, width=None, lines=1):
        layout = PangoCairo.create_layout(cr)
        layout.set_text(text or '', -1)
        return cls._shape(layout, font, width, lines)

    # ── clics ────────────────────────────────────────────────────────────────

    def on_click(self, _gesture, _n, x, y):
        x0, w, h = self.island_rect(self.da.get_width())
        if not (x0 <= x <= x0 + w and y <= max(h, HOVER_STRIP)):
            return
        if self.settings['compact'] and self.target() == 'petit':
            self.expand()
            return
        for key, (bx, by, bw, bh) in self.buttons.items():
            if self.view.ask and bx <= x <= bx + bw and by <= y <= by + bh:
                self.model.decide(self.view.session, key == 'allow')
                self.refresh()
                return
        for s, ry, rh in self.rows:
            if ry <= y < ry + rh:
                self.go(s)
                return
        if self.rows and y > self.rows[0][1]:
            return
        if x < x0 + 12 + PET + 4:
            self.poke()
        elif self.view.session:
            self.go(self.view.session)

    def go(self, s):
        """Clic en una sesión: salta a su pane. En una alerta abre su URL y la descarta."""
        self.collapse()
        if s.state == 'alert':
            self.model.dismiss(s)
            self.refresh()
        threading.Thread(target=actions.jump, args=(s,), daemon=True).start()

    def on_right_click(self, _gesture, _n, x, y):
        x0, w, h = self.island_rect(self.da.get_width())
        if not (x0 <= x <= x0 + w and y <= max(h, HOVER_STRIP)):
            return
        self.toggle_compact()


def main(argv):
    app = Gtk.Application(application_id='dev.elyares.Mascota')

    def activate(app):
        if not getattr(app, 'island', None):
            app.island = Island(app)

    app.connect('activate', activate)
    return app.run(argv[:1])
