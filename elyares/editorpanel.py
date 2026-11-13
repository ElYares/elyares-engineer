"""La vista Editor: la lista de lo que cambió en el proyecto y, al lado, nvim.

A la izquierda los archivos con cambios sin commitear (los que toca el agente o
tú); a la derecha un nvim con tu configuración, en una sesión de tmux que
sobrevive al reload. Un clic en un archivo de la lista se lo pide a ese nvim por
su socket: la app no teclea nada en él. El Taller usa esta misma pieza arriba.
"""

import gi

gi.require_version('Gtk', '4.0')

from gi.repository import GLib, Gtk

from . import gitview, terminal
from .terminalpanel import TerminalPanel
from .windowframe import SPACE

LIST_W = 280              # lo que mide la lista al abrir; el divisor se arrastra
LIST_MIN = 160
CODES = {'M': 'M', 'A': 'A', 'D': 'D', 'R': 'R', '?': 'N', 'U': '!'}      # la marca de cada fila


class FileList(Gtk.ScrolledWindow):
    """Los archivos con cambios, uno por botón."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_size_request(LIST_MIN, -1)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.box, f'set_margin_{side}')(SPACE[1])
        self.set_child(self.box)
        self.signature = None

    def set_files(self, state, choose):
        """`state`: un `gitview.State`. `choose(ruta)`: el clic en un archivo."""
        sig = (state.root, state.branch, repr(state.files), state.chosen)
        if sig == self.signature:
            return
        self.signature = sig
        while (child := self.box.get_first_child()) is not None:
            self.box.remove(child)
        if state.files is None:
            self._note('Buscando el proyecto…' if not state.root else 'Esta carpeta no es un repositorio de git.')
        elif not state.files:
            self._note('Sin cambios. Cuando el agente (o tú) toque un archivo, aparece aquí.')
        for code, path in state.files or []:
            btn = Gtk.Button()
            btn.add_css_class('elyares-btn')
            btn.set_halign(Gtk.Align.FILL)
            label = Gtk.Label(xalign=0, ellipsize=3)       # Pango.EllipsizeMode.END
            mark = GLib.markup_escape_text(CODES.get(code, 'M'))
            style = 'weight="bold"' if path == state.chosen else ''
            label.set_markup(f'<span alpha="60%">{mark}</span>  <span {style}>{GLib.markup_escape_text(path)}</span>')
            btn.set_child(label)
            btn.update_property([Gtk.AccessibleProperty.LABEL], [f'{gitview.LABELS.get(code, "")}: {path}'])
            btn.connect('clicked', lambda _b, p=path: choose(p))
            self.box.append(btn)

    def _note(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        label.add_css_class('dim-label')
        self.box.append(label)


class EditorPanel(Gtk.Paned):
    """La lista de archivos a un lado y nvim al otro, con un divisor que se arrastra:
    nvim se queda con todo lo que la ventana gane o pierda."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class('elyares-sources')
        self.files = FileList()
        self.nvim = TerminalPanel(kind=terminal.NVIM)
        self.nvim.set_visible(True)         # solo se ve cuando se ve el panel entero
        self.nvim.set_size_request(LIST_MIN, -1)
        self.set_start_child(self.files)
        self.set_end_child(self.nvim)
        self.set_position(LIST_W)
        self.set_resize_start_child(False)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)
        self.set_visible(False)
