"""La isla: una capa layer-shell arriba del monitor enfocado, con ElYares dentro.

La ventana mide siempre WIN_W x WIN_H y es transparente. Lo que crece y se
encoge es la isla negra que se dibuja dentro, y la región de entrada la sigue:
fuera de la isla, los clics pasan a las ventanas de abajo.

En modo compacto (clic derecho en la isla lo prende y lo apaga) la isla se
queda en una pastilla con la mascota en miniatura, y solo se abre con un clic
o cuando hay que contestar un permiso.
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

from . import actions, hypr, ipc, mascot, settings  # noqa: E402
from .state import Model  # noqa: E402

WIN_W, WIN_H = 480, 112
SIZES = {'hidden': (120, 6), 'petit': (56, 34), 'peek': (92, 80), 'open': (440, 88),
         'ask': (440, 108)}
HOVER_STRIP = 10     # alto de la franja que detecta el ratón cuando está escondida
PET = 72             # lado del cuadro de la mascota
PET_SCALE = PET / 260
ISLAND_BG = (5 / 255, 6 / 255, 8 / 255, .97)
TITLE_COLOR = (.95, .96, 1, 1)
DETAIL_COLOR = (.66, .71, .84, 1)
MUTED_COLOR = (.44, .49, .63, 1)
FONT_TITLE = 'Sans Semi-Bold 11'
FONT_DETAIL = 'JetBrainsMono Nerd Font 9'
FONT_BUTTON = 'Sans Semi-Bold 10'
BUTTON_H, BUTTON_W, BUTTON_GAP = 26, 84, 8
ALLOW_BG, ALLOW_FG = (.95, .96, 1), (5 / 255, 6 / 255, 8 / 255)
DENY_BG, DENY_FG = (1, 1, 1), (.95, .96, 1)
SPRING_K, SPRING_C = 220.0, 22.0   # rigidez y amortiguación: rebota un poquito
LOOK_EVERY = 1 / 15                # frecuencia con la que se pregunta el cursor
IDLE_FPS = 12                      # asomada y quieta: ~3% de CPU en vez de ~8% a 30


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class Island:
    def __init__(self, app):
        self.model = Model()
        self.view = self.model.view()
        self.title, self.detail = '', ''
        self.dnd = False
        self.hover = False
        self.settings = settings.load()
        self.expanded = False           # modo compacto: abierta a mano con un clic
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
        GLib.timeout_add_seconds(3, self.poll_dnd)
        # "Terminó" y "esperando" caducan solos aunque no lleguen más eventos.
        GLib.timeout_add_seconds(1, self.on_second)

    # ── estado ───────────────────────────────────────────────────────────────

    def on_message(self, msg, req):
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
        changed = v.mode != self.view.mode or v.key != self.view.key
        self.view = v
        if changed or v.mode != 'hidden':
            self.ensure_tick()

    def target(self):
        mode = self.view.mode
        if mode == 'open' and self.view.ask:
            return 'ask'
        # Un permiso se abre solo aunque esté compacta: hay que contestarlo.
        if self.settings['compact'] and self.view.pet != 'permission':
            if self.expanded:
                return 'open' if self.view.session else 'peek'
            return 'petit' if mode != 'hidden' or self.hover else 'hidden'
        if self.hover:
            if mode == 'hidden':
                mode = 'peek'
            elif mode == 'peek' and self.view.session:
                mode = 'open'
        return mode

    def set_hover(self, value):
        self.hover = value
        if not value:
            self.pointer = None
            self.expanded = False
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

        tw, th = SIZES[self.target()]
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
            if self.target() != 'hidden':
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
                dy = pos[1] - (top + self.h / 2)
                d = math.hypot(dx, dy) or 1
                k = min(1.0, d / 400)
                self.look_target = (dx / d * k, dy / d * k)
        self.look[0] += (self.look_target[0] - self.look[0]) * 0.15
        self.look[1] += (self.look_target[1] - self.look[1]) * 0.15

    def update_region(self):
        w = int(max(self.w, SIZES['hidden'][0]))
        h = int(max(self.h, HOVER_STRIP))
        region = ((WIN_W - w) // 2, 0, w, h)
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
        cr.set_source_rgba(*ISLAND_BG)
        cr.fill_preserve()
        cr.save()
        cr.clip()

        now = time.monotonic()
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
            detail = self._layout(cr, self.detail, FONT_DETAIL, right - tx)
            cr.move_to(tx, mid + 3)
            cr.set_source_rgba(*DETAIL_COLOR[:3], text_alpha)
            PangoCairo.show_layout(cr, detail)
        self.buttons = {}
        if ask_alpha > 0 and text_alpha > 0:
            self.draw_buttons(cr, x0 + w - 18, h - 14, ask_alpha * text_alpha)
        cr.restore()

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
    def _layout(cr, text, font, width=None):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription.from_string(font))
        layout.set_text(text or '', -1)
        if width:
            layout.set_width(int(max(10, width) * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
        return layout

    # ── clics ────────────────────────────────────────────────────────────────

    def on_click(self, _gesture, _n, x, y):
        x0, w, h = self.island_rect(self.da.get_width())
        if not (x0 <= x <= x0 + w and y <= max(h, HOVER_STRIP)):
            return
        if self.settings['compact'] and self.target() == 'petit':
            self.expanded = True
            self.ensure_tick()
            return
        for key, (bx, by, bw, bh) in self.buttons.items():
            if self.view.ask and bx <= x <= bx + bw and by <= y <= by + bh:
                self.model.decide(self.view.session, key == 'allow')
                self.refresh()
                return
        if x < x0 + 12 + PET + 4:
            self.poke()
        elif self.view.session:
            self.expanded = False
            threading.Thread(target=actions.jump, args=(self.view.session,), daemon=True).start()

    def on_right_click(self, _gesture, _n, x, y):
        x0, w, h = self.island_rect(self.da.get_width())
        if not (x0 <= x <= x0 + w and y <= max(h, HOVER_STRIP)):
            return
        self.settings['compact'] = not self.settings['compact']
        self.expanded = False
        settings.save(self.settings)
        self.ensure_tick()


def main(argv):
    app = Gtk.Application(application_id='dev.elyares.Mascota')

    def activate(app):
        if not getattr(app, 'island', None):
            app.island = Island(app)

    app.connect('activate', activate)
    return app.run(argv[:1])
