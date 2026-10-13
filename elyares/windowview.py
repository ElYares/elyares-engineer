"""La isla como app: una ventana normal de Hyprland con lo mismo que la isla.

No es otro programa ni otra isla: es el mismo daemon con el mismo estado. El
dibujo de la isla (tablero, chat, proyectos) vive en un solo `Gtk.DrawingArea`
dentro de un `Gtk.Overlay`; abrir la ventana mueve ese `overlay` de la capa de
layer-shell a una `Gtk.ApplicationWindow` y esconde la capa, y cerrarla lo
devuelve. Nunca se ven las dos a la vez. Ver la decisión 008 del vault.

Se abre con `elyares-ctl window` (o el `.desktop`, que llama a lo mismo) y con
`elyares-ctl window toggle` se alterna. `Island.windowed` dice en cuál de los dos
modos está; la isla lo mira para no tocar el layer-shell mientras no se ve y para
quedarse siempre abierta, sin esconderse ni asomarse.
"""

import time

from gi.repository import GLib, Gtk

from . import hypr, settings

APP_ID = 'dev.elyares.Engineer'
TITLE = 'Elyares Engineer'
CLASS_RE = r'^(dev\.elyares\.Engineer)$'    # la `class` de la ventana, como regex de Hyprland
MIN_W, MIN_H = 480, 320          # lo menos que se le deja a la ventana
FIT_H = 100                      # lo que se le resta a la pantalla para que no la tape entera
FIT_PAD = 12                     # aire bajo la isla
FIT_STEP = 6                     # cambios de alto menores no mueven la ventana
REMEMBER_SECS = 2                # cada cuánto se guarda el tamaño que Yared va dejando
FIT_SETTLE = 0.6                 # lo que tarda Hyprland en dejarla del alto pedido
FIT_VOID = 120                   # con su medida guardada, el vacío bajo el contenido que se tolera antes de ajustarla
OPEN_H = 780                     # alto con el que abre: el tablero y el chat caben; el resto, con scroll de la pantalla


class WindowView:
    """Lo que guarda: `windowed` (la app está a la vista) y `app_win` (su
    ventana, que se crea la primera vez)."""

    fit_h = 0                       # el último alto al que se ajustó la ventana
    fit_at = 0.0                    # cuándo se pidió
    fit_manual = False              # Yared la estiró a mano: su medida manda para lo alto
    fit_shrunk = False              # se encogió sola por un contenido corto: no se guarda ese alto
    fit_saved = (0, 0, 0.0)         # el último tamaño guardado: ancho, alto y cuándo
    windowed = False                # la isla, que se arma sin __init__ en las pruebas, la mira siempre
    app_win = None

    def window_init(self):
        self.windowed = False
        self.app_win = None

    # ── abrir y cerrar ──────────────────────────────────────────────────────

    def open_window(self):
        """Abre la ventana de la app, o si ya está abierta, la enfoca."""
        if self.windowed:
            self.app_win.present()
            return
        if self.app_win is None:
            self.app_win = self.window_make()
        # Un widget solo puede tener un padre: primero se suelta de la capa.
        self.win.set_child(None)
        self.app_win.set_child(self.overlay)
        self.da.set_content_width(MIN_W)
        self.da.set_content_height(MIN_H)
        self.windowed = True
        self.flows_dock()
        self.fit_h = 0
        self.fit_manual = False
        self.off = False
        self.settings['window'] = True
        self.window_save()
        self.win.set_visible(False)
        self.app_win.present()
        self.expand()
        kept = self.window_kept()
        if kept:
            # La dejó a su medida la última vez: se respeta, y no se ajusta sola.
            self.fit_manual = True
            GLib.timeout_add(250, self.window_restore, kept)

    def close_window(self):
        """Cierra la ventana y devuelve la isla, con el estado que tenía."""
        if not self.windowed:
            return
        if self.fit_manual:
            self.window_remember(force=True)
        self.app_win.set_child(None)
        self.app_win.set_visible(False)
        self.windowed = False
        self.flows_dock()
        self.settings['window'] = False
        self.window_save()
        self.win.set_child(self.overlay)
        self.da.set_content_width(self.island_w)
        self.da.set_content_height(self.island_h)
        self.region = None              # la capa vuelve a estrenar su zona de entrada
        self.win.present()
        self.place()
        self.update_region()
        self.collapse()

    def toggle_window(self):
        if self.windowed:
            self.close_window()
        else:
            self.open_window()

    def window_make(self):
        win = Gtk.ApplicationWindow(application=self.gtk_app)
        win.set_title(TITLE)
        win.set_icon_name(APP_ID)
        width, height = self.window_size()
        win.set_default_size(width, height)
        # Cerrarla no es salir: solo vuelve la isla.
        win.connect('close-request', self.on_window_close)
        win.connect('notify::is-active', self.on_window_focus)
        return win

    def window_size(self):
        """Con el tamaño con el que la isla abierta cabe entera, sin pasarse de la pantalla."""
        width, height = self.island_w, min(self.island_h, OPEN_H)
        if self.screen_h:
            height = min(height, self.screen_h - FIT_H)
        if self.screen_w:
            width = min(width, self.screen_w)
        return max(width, MIN_W), max(height, MIN_H)

    def window_fit(self, content_h, room):
        """El alto de la ventana sigue al del contenido (más el sitio de las
        burbujas de las pastillas), para que no quede un negro debajo.
        Si Yared la estira (el alto ya no es el que se pidió), su medida manda:
        se guarda y vale para lo alto (el chat). Un contenido mucho más corto
        (el tablero) la encoge igual, sin pisar la medida guardada, y al
        volver lo alto recupera la suya."""
        if self.app_win is None:
            return
        now = time.monotonic()
        height = self.app_win.get_height()
        want = max(MIN_H, int(content_h) + int(room) + FIT_PAD)
        if self.fit_h and height and abs(height - self.fit_h) >= FIT_STEP and now - self.fit_at > FIT_SETTLE:
            # No es el alto que se pidió: Yared la estiró.
            self.fit_manual, self.fit_shrunk = True, False
            self.fit_h = height
            self.window_remember(force=True)
            return
        if self.fit_manual:
            kept = self.window_kept()
            if kept is None:
                self.window_remember()
                return
            self.fit_shrunk = kept[1] - want > FIT_VOID
            want = want if self.fit_shrunk else kept[1]
            self.window_remember()
        if abs(want - self.fit_h) < FIT_STEP:
            return
        self.fit_h, self.fit_at = want, now
        self.window_resize(self.app_win.get_width() or MIN_W, want)

    def window_resize(self, width, height):
        # GTK no encoge una ventana flotante cambiándole el tamaño por defecto:
        # se lo pedimos a Hyprland, que es quien la dimensiona.
        try:
            hypr.request(f'dispatch resizewindowpixel exact {width} {height},class:{CLASS_RE}')
        except OSError:
            self.app_win.set_default_size(width, height)

    # ── el tamaño que Yared le deja ─────────────────────────────────────────

    def window_kept(self):
        """El tamaño guardado de la última vez, o None."""
        size = self.settings.get('window_size')
        if (isinstance(size, (list, tuple)) and len(size) == 2
                and all(isinstance(n, int) and MIN_W <= n <= 8000 for n in size)):
            return tuple(size)
        return None

    def window_remember(self, force=False):
        """Guarda el tamaño actual de la ventana para la próxima vez; sin
        `force`, como mucho cada REMEMBER_SECS y solo si cambió."""
        if self.app_win is None:
            return
        now = time.monotonic()
        width, height = self.app_win.get_width(), self.app_win.get_height()
        kept = self.window_kept()
        if self.fit_shrunk and kept:
            height = kept[1]                # encogida por un contenido corto: la medida de Yared no cambia
        saved_w, saved_h, at = self.fit_saved
        if not width or not height or (width, height) == (saved_w, saved_h):
            return
        if not force and now - at < REMEMBER_SECS:
            return
        self.fit_saved = (width, height, now)
        self.settings['window_size'] = [width, height]
        self.window_save()

    def window_restore(self, size):
        self.fit_h, self.fit_at = size[1], time.monotonic()     # lo pedido: no se toma por estirada
        self.window_resize(*size)
        return GLib.SOURCE_REMOVE

    # ── eventos ─────────────────────────────────────────────────────────────

    def on_window_close(self, _win):
        self.close_window()
        return True                     # la ventana ya la quitamos nosotros

    def on_window_focus(self, win, _param):
        """Sin foco, la caja del chat no recibe teclas: se deja de «escribir»."""
        if not win.is_active() and self.chat_typing:
            self.chat_type(False)

    def window_save(self):
        settings.save(self.settings)
