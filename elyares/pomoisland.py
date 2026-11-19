"""La isla del Pomodoro: una segunda isla pegada a la de siempre, con la taza, el reloj y las tareas.

Va en su propia ventana de layer-shell (como la de los flujos, `workflowview.py`) y sale del lado
contrario al de ésta: si los flujos van a la izquierda, el pomodoro va a la derecha. Se abre o se
quita con «Más → Isla del Pomodoro» o `elyares-ctl pomoisland`; abierta, «Ocultar» la deja en una
pastilla con la tacita y el reloj, y un clic en la pastilla la despliega. Las dos cosas se acuerdan
(`pomo_island`, `pomo_collapsed`). El contenido es el del panel de `pomodoroview.py`. En la
ventana de la app no hay: ahí está la vista Pomodoro.
"""

import time

import cairo
import gi

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from . import cup, mascot, pomodoro, pomodoroview, settings, themes  # noqa: E402

PI_PILL_W, PI_PILL_H = 150, 36          # colapsada
PI_WIN_H = 420                          # alto de su ventana: lo más alto que llega el panel
PI_GAP = 6                              # entre ella y la isla de siempre
PI_SPRING_K, PI_SPRING_C = 220.0, 22.0  # los de la isla: rebota un poquito
PI_GLASS_EDGE = .16                     # el filo claro del vidrio (`app.GLASS_EDGE`)
PI_CUP_MINI = 26                        # la tacita de la pastilla
FONT_PI_PILL = 'Sans Semi-Bold 10'


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class PomoIslandView:
    """Lo que guarda: `pi_open` (está a la vista), `pi_collapsed` (está en su pastilla) y, de su
    ventana, `pi_win` y `pi_da`, con `pw`/`ph` (lo que mide ahora, que rebota hasta su tamaño) y
    `pi_hits` (lo que se puede pulsar, del último dibujo)."""

    pi_open = False
    pi_collapsed = False
    pi_win = pi_da = None
    pi_side = 'right'
    pw, ph, pvw, pvh = float(PI_PILL_W), 0.0, 0.0, 0.0      # (la isla se arma sin __init__ en las pruebas)
    pi_ticking, pi_last, pi_pointer, pi_region = False, None, None, None
    pi_hits = ()

    def pomoisland_init(self):
        self.pi_open = bool(self.settings.get('pomo_island'))
        self.pi_collapsed = bool(self.settings.get('pomo_collapsed'))
        self.pi_win = self.pi_da = None
        self.pw, self.ph, self.pvw, self.pvh = float(PI_PILL_W), 0.0, 0.0, 0.0
        self.pi_ticking, self.pi_last = False, None
        self.pi_hits, self.pi_pointer, self.pi_region = [], None, None

    # ── abrir, quitar y ocultar ─────────────────────────────────────────────

    def toggle_pomoisland(self):
        self.pi_open = not self.pi_open
        self.settings['pomo_island'] = self.pi_open
        settings.save(self.settings)
        if self.pi_open:
            self.pi_collapsed = False       # lo piden para verlo
            self.settings['pomo_collapsed'] = False
            self.pomo_watch.refresh()
            self.pi_show()
        self.pi_redraw()

    def pi_collapse(self, on):
        """La deja en su pastilla, o la despliega. Se acuerda."""
        self.pi_collapsed = bool(on)
        self.settings['pomo_collapsed'] = self.pi_collapsed
        settings.save(self.settings)
        self.pi_redraw()

    def pi_visible(self):
        return self.pi_open and not self.windowed

    def pi_show(self):
        win = self.pi_window()
        if win is not None:
            self.pi_monitor()
            win.set_visible(True)

    def pomoisland_tick(self):
        """Cada segundo: la crea si debe estar a la vista (al arrancar), y repinta el reloj."""
        if self.pi_visible():
            if self.pi_win is None or not self.pi_win.get_visible():
                self.pi_show()
            self.pi_redraw()
        elif self.ph > 0 and not self.pi_ticking:
            self.pi_redraw()                # se cerró o entró la ventana: que se encoja y se esconda

    # ── su ventana ──────────────────────────────────────────────────────────

    def pi_window(self):
        """Su ventana de layer-shell, de lado a lado y transparente. None sin aplicación (las pruebas)."""
        if self.pi_win is not None:
            return self.pi_win
        app = getattr(self, 'gtk_app', None)
        if app is None:
            return None
        win = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(win)
        LayerShell.set_namespace(win, 'elyares')        # el desenfoque de Hyprland es por nombre de capa
        LayerShell.set_layer(win, LayerShell.Layer.TOP)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(win, edge, True)
        LayerShell.set_exclusive_zone(win, 0)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
        LayerShell.set_margin(win, LayerShell.Edge.TOP, self.top())
        win.set_default_size(640, PI_WIN_H)
        da = Gtk.DrawingArea()
        da.set_content_height(PI_WIN_H)
        da.set_draw_func(self.pi_draw)
        motion = Gtk.EventControllerMotion()
        motion.connect('motion', self.on_pi_motion)
        motion.connect('leave', lambda *_: self.on_pi_motion(None, None, None))
        da.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect('pressed', self.on_pi_click)
        da.add_controller(click)
        win.set_child(da)
        self.pi_win, self.pi_da = win, da
        return win

    def pi_monitor(self):
        """Sale en la pantalla en la que está la isla."""
        name = (getattr(self, 'monitor', None) or {}).get('name')
        if self.pi_win is None or not name:
            return
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            if monitors.get_item(i).get_connector() == name:
                LayerShell.set_monitor(self.pi_win, monitors.get_item(i))

    # ── su tamaño y su sitio ────────────────────────────────────────────────

    def pi_goal(self):
        """Lo que mide ahora: su pastilla, su panel, o nada (sin alto) si no se ve."""
        if not self.pi_visible():
            return self.pw, 0
        if self.pi_collapsed:
            return PI_PILL_W, PI_PILL_H
        self.pm_root = self.pomodoro_root()
        w, h = self.pomodoro_goal()
        return w, h

    def pi_rect(self, width):
        """(x, ancho, alto) en su ventana: pegada a la de siempre, del lado contrario al de los flujos."""
        from . import app
        w, h = clamp(self.pw, 0, pomodoroview.PM_W), clamp(self.ph, 0, PI_WIN_H)
        win_left = self.offset() if self.moved() else (width - app.WIN_W) / 2
        ix0, iw, _ = self.island_rect(app.WIN_W)
        self.pi_side = 'left' if self.flows_side(width, win_left) == 'right' else 'right'
        if self.pi_side == 'left':
            x0 = win_left + ix0 - PI_GAP - w
        else:
            x0 = win_left + ix0 + iw + PI_GAP
        return clamp(x0, 0, max(0, width - w)), w, h

    def pi_redraw(self):
        """Pide un dibujo; la isla rebota hasta su tamaño mientras haga falta."""
        da = self.pi_da
        if da is None:
            return
        da.queue_draw()
        if not self.pi_ticking:
            self.pi_ticking, self.pi_last = True, None
            da.add_tick_callback(self.pi_on_tick)

    def pomoisland_follow(self):
        """La isla de siempre se movió o cambió de tamaño: ésta la sigue."""
        if self.pi_win is not None and not self.windowed:
            LayerShell.set_margin(self.pi_win, LayerShell.Edge.TOP, self.top())
        if self.pi_da is not None and self.pi_open:
            self.pi_da.queue_draw()
            self.pi_region_set()

    def pi_on_tick(self, widget, _clock):
        now = time.monotonic()
        dt = 1 / 60 if self.pi_last is None else min(0.05, now - self.pi_last)
        self.pi_last = now
        tw, th = self.pi_goal()
        for pos, vel, goal in (('pw', 'pvw', tw), ('ph', 'pvh', th)):
            x, v = getattr(self, pos), getattr(self, vel)
            v += (PI_SPRING_K * (goal - x) - PI_SPRING_C * v) * dt
            setattr(self, vel, v)
            setattr(self, pos, x + v * dt)
        settled = abs(tw - self.pw) < 0.5 and abs(th - self.ph) < 0.5 and abs(self.pvw) < 1 and abs(self.pvh) < 1
        if settled:
            self.pw, self.ph, self.pvw, self.pvh = tw, th, 0.0, 0.0
        self.pi_region_set()
        widget.queue_draw()
        steaming = self.pi_visible() and self.pomodoro_steams()
        if settled and not steaming:
            self.pi_ticking = False
            if not self.pi_visible() and self.pi_win is not None:
                self.pi_win.set_visible(False)          # ya se quitó: no deja nada que tapar
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def pi_region_set(self):
        """Solo la isla recibe clics; fuera de ella pasan a las ventanas de abajo."""
        surface = self.pi_win.get_surface() if self.pi_win is not None else None
        if surface is None or self.pi_da is None:
            return
        x0, w, h = self.pi_rect(self.pi_da.get_width())
        region = (int(x0), 0, int(w) + 1, int(h) + 1) if h >= 1 else (0, 0, 0, 0)
        if region != self.pi_region:
            surface.set_input_region(cairo.Region(cairo.RectangleInt(*region)))
            self.pi_region = region

    def pomodoro_steams(self):
        """¿Hay vapor que mover? Solo con el reloj corriendo y sin movimiento reducido."""
        return not self.motion_reduced() and cup.state_of(pomodoro.describe(self.pomo_watch.status)) in (
            'vaciando', 'repaso', 'llenando')

    # ── el dibujo ───────────────────────────────────────────────────────────

    def pi_draw(self, _da, cr, width, _height):
        """Su cuerpo, como el de la isla de siempre, y dentro la pastilla o el panel."""
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        x0, w, h = self.pi_rect(width)
        if h < 0.5 or w < 1:
            self.pi_hits = []
            return
        edge = self.island_fill(cr, x0, w, h)
        cr.save()
        cr.clip()
        island = (self.hits, self.buttons, self.pointer)
        self.hits, self.buttons, self.pointer = [], {}, self.pi_pointer
        self.pm_side = True
        try:
            if self.pi_collapsed:
                self.draw_pi_pill(cr, x0, w, h, clamp((h - 14) / 20))
            else:
                self.draw_pomodoro(cr, x0, w, h, clamp((w - 300) / 80) * clamp((h - 90) / 60))
        finally:
            self.pm_side = False
            self.pi_hits = self.hits
            self.hits, self.buttons, self.pointer = island
        cr.restore()
        if edge:
            cr.append_path(edge)
            cr.set_source_rgba(*themes.glow(), PI_GLASS_EDGE)
            cr.set_line_width(1)
            cr.stroke()

    def draw_pi_pill(self, cr, x0, w, h, alpha):
        """Colapsada: la tacita con su café y el reloj (o «Pomodoro» si está parado). Un clic la abre."""
        status = pomodoro.describe(self.pomo_watch.status)
        if self.over(x0, 0, w, h):
            cr.rectangle(x0, 0, w, h)
            cr.set_source_rgba(*themes.glow(), .06 * alpha)
            cr.fill()
        cup.draw(cr, x0 + 8, (PI_PILL_H - PI_CUP_MINI) / 2, PI_CUP_MINI, cup.state_of(status), cup.level_of(status),
                 time.monotonic(), alpha)
        text = status['clock'] if status and status['running'] else 'Pomodoro'
        self.put(cr, text, FONT_PI_PILL, x0 + 8 + PI_CUP_MINI + 8, PI_PILL_H / 2 - 8,
                      mascot.rgba(self.ink('head'))[:3], alpha, width=w - 70)
        opens = '‹' if self.pi_side == 'left' else '›'
        self.put(cr, opens, 'Sans Semi-Bold 12', x0 + w - 12, PI_PILL_H / 2 - 9,
                 mascot.rgba(self.ink('text', .62))[:3], alpha, align=1.0)

    # ── el ratón ────────────────────────────────────────────────────────────

    def on_pi_motion(self, _ctrl, x, y):
        self.pi_pointer = None if x is None else (x, y)
        if self.pi_da is not None:
            self.pi_da.queue_draw()

    def on_pi_click(self, _gesture, _n, x, y):
        x0, w, h = self.pi_rect(self.pi_da.get_width())
        if not (x0 <= x <= x0 + w and y <= h):
            return
        if self.pi_collapsed:
            self.pi_collapse(False)
            return
        for kind, key, hx, hy, hw, hh in self.pi_hits:
            if kind == 'pomodoro' and hx <= x <= hx + hw and hy <= y <= hy + hh:
                self.on_pomodoro_hit(key)
                return
