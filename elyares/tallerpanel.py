"""La vista Taller: el editor (lista y nvim) arriba y la terminal abajo, sobre el mismo proyecto.

Cada mitad es su propio widget de terminal (su propio cliente de tmux, enganchado a la
misma sesión que su vista suelta): esta clase solo las apila en un divisor que se arrastra.
La ventana les da lo que necesitan (`windowview`).
"""

import gi

gi.require_version('Gtk', '4.0')

from gi.repository import Gtk

from .editorpanel import EditorPanel
from .terminalpanel import TerminalPanel

TOP_SHARE = 0.60          # lo que se queda el editor de la altura al abrir; el divisor se arrastra
MIN_PART = 120


class TallerPanel(Gtk.Paned):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class('elyares-sources')
        self.editor = EditorPanel()
        self.terminal = TerminalPanel()
        self.editor.set_visible(True)        # solo se ven cuando se ve el Taller entero
        self.terminal.set_visible(True)
        self.editor.set_size_request(-1, MIN_PART)
        self.terminal.set_size_request(-1, MIN_PART)
        self.set_start_child(self.editor)
        self.set_end_child(self.terminal)
        self.set_resize_start_child(True)
        self.set_resize_end_child(True)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)
        self.placed = False
        self.set_visible(False)

    def fit(self, height):
        """El divisor, la primera vez que la ventana ya tiene alto: arriba el editor, abajo la terminal."""
        if not self.placed and height > 2 * MIN_PART:
            self.placed = True
            self.set_position(int(height * TOP_SHARE))
