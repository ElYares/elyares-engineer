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

from gi.repository import Gtk

from . import settings

APP_ID = 'dev.elyares.Engineer'
TITLE = 'Elyares Engineer'
MIN_W, MIN_H = 480, 320          # lo menos que se le deja a la ventana
FIT_H = 100                      # lo que se le resta a la pantalla para que no la tape entera
FIT_PAD = 12                     # aire bajo la isla
FIT_STEP = 6                     # cambios de alto menores no mueven la ventana
OPEN_H = 780                     # alto con el que abre: el tablero y el chat caben; el resto, con scroll de la pantalla


class WindowView:
    """Lo que guarda: `windowed` (la app está a la vista) y `app_win` (su
    ventana, que se crea la primera vez)."""

    fit_h = 0                       # el último alto al que se ajustó la ventana
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
        self.fit_h = 0
        self.off = False
        self.settings['window'] = True
        self.window_save()
        self.win.set_visible(False)
        self.app_win.present()
        self.expand()

    def close_window(self):
        """Cierra la ventana y devuelve la isla, con el estado que tenía."""
        if not self.windowed:
            return
        self.app_win.set_child(None)
        self.app_win.set_visible(False)
        self.windowed = False
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
        burbujas de las pastillas), para que no quede un negro debajo. Solo
        cuando el alto cambia de verdad: no pelea con quien la redimensiona."""
        want = max(MIN_H, int(content_h) + int(room) + FIT_PAD)
        if self.app_win is None or abs(want - self.fit_h) < FIT_STEP:
            return
        self.fit_h = want
        self.app_win.set_default_size(self.app_win.get_width(), want)

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
