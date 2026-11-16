"""La vista Taller: el editor (lista y nvim) y la terminal sobre el mismo proyecto.

Cada mitad es su propio widget de terminal (su propio cliente de tmux, enganchado a la
misma sesión que su vista suelta): esta clase solo las acomoda en un divisor que se arrastra.
Siempre el editor arriba y la terminal abajo; solo si la ventana es angosta pasan a pestañas
«Editor | Terminal» (una a la vista). La ventana les da lo que necesitan (`windowview`).
"""

import gi

gi.require_version('Gtk', '4.0')

from gi.repository import GLib, Gtk

from . import fonts, responsive
from .editorpanel import EditorPanel
from .terminalpanel import TerminalPanel
from .windowframe import SPACE

TOP_SHARE = 0.60          # lo que se queda el editor de la altura al abrir; el divisor se arrastra
MIN_PART = 120
MIN_SIDE = 280


def layout(width, height):
    """'tabs' (angosto) o 'stack' (el editor arriba y la terminal abajo)."""
    return 'tabs' if responsive.mode(width, scale=fonts.view_scale()) == responsive.COMPACT else 'stack'


class TallerPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class('elyares-sources')
        self.editor = EditorPanel()
        self.terminal = TerminalPanel()
        self.editor.set_visible(True)        # solo se ven cuando se ve el Taller entero
        self.terminal.set_visible(True)
        self.editor.set_size_request(MIN_SIDE, MIN_PART)
        self.terminal.set_size_request(MIN_SIDE, MIN_PART)
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        self.paned.set_start_child(self.editor)
        self.paned.set_end_child(self.terminal)
        self.paned.set_resize_start_child(True)
        self.paned.set_resize_end_child(True)
        self.paned.set_shrink_start_child(False)
        self.paned.set_shrink_end_child(False)
        self.tabs = Gtk.Box(spacing=2, margin_bottom=SPACE[0])
        self.tabs.add_css_class('elyares-segments')
        self.tab_btn = {}
        self.shown = 'editor'           # la pestaña a la vista en modo angosto
        first = None
        for key, text in (('editor', 'Editor'), ('terminal', 'Terminal')):
            btn = Gtk.ToggleButton(label=text, hexpand=True)
            if first is None:
                first = btn
            else:
                btn.set_group(first)
            btn.connect('toggled', self._tab, key)
            self.tabs.append(btn)
            self.tab_btn[key] = btn
        self.tab_btn['editor'].set_active(True)
        self.mode = None
        self.height = 0
        self.placed = False
        self.tabs.set_visible(False)
        self.append(self.tabs)
        self.append(self.paned)
        self.add_tick_callback(self._measure)
        self.set_visible(False)

    def _tab(self, btn, key):
        if btn.get_active() and key != self.shown:
            self.shown = key
            self._apply()

    def _measure(self, _widget, _clock):
        width = self.get_width()
        if width and self.height:
            new = layout(width, self.height)
            if new != self.mode:
                self.mode = new
                self._apply()
        return GLib.SOURCE_CONTINUE

    def _apply(self):
        """Acomoda las dos mitades según el modo: pestañas o una sobre otra."""
        tabs = self.mode == 'tabs'
        self.tabs.set_visible(tabs)
        self.editor.set_visible(not tabs or self.shown == 'editor')
        self.terminal.set_visible(not tabs or self.shown == 'terminal')

    def fit(self, height):
        """El alto que tiene la ventana para esta vista: con él se decide el modo y se pone el divisor."""
        self.height = height
        if not self.placed and height > 2 * MIN_PART:
            self.placed = True              # el divisor, la primera vez: arriba el editor, abajo la terminal
            self.paned.set_position(int(height * TOP_SHARE))
        if self.mode is None and self.get_width():
            self.mode = layout(self.get_width(), height)
            self._apply()
