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

    def set_files(self, state, choose, edited=()):
        """`state`: un `gitview.State`. `choose(ruta)`: el clic en un archivo. `edited`: las rutas
        (relativas al proyecto) que el agente cambió en el chat, la última primero."""
        sig = (state.root, state.branch, repr(state.files), state.chosen, tuple(edited))
        if sig == self.signature:
            return
        self.signature = sig
        while (child := self.box.get_first_child()) is not None:
            self.box.remove(child)
        if edited:
            self._section('TOCADOS POR EL AGENTE')
            for path in edited:
                self._row('✎', path, state.chosen, f'Tocado por el agente: {path}', choose)
            self._section('CAMBIOS SIN COMMITEAR')
        if state.files is None:
            self._note('Buscando el proyecto…' if not state.root else 'Esta carpeta no es un repositorio de git.')
        elif not state.files:
            self._note('Sin cambios. Cuando el agente (o tú) toque un archivo, aparece aquí.')
        for code, path in state.files or []:
            self._row(CODES.get(code, 'M'), path, state.chosen, f'{gitview.LABELS.get(code, "")}: {path}', choose)

    def _section(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class('elyares-section')
        self.box.append(label)

    def _row(self, mark, path, chosen, said, choose):
        btn = Gtk.Button()
        btn.add_css_class('elyares-btn')
        btn.set_halign(Gtk.Align.FILL)
        label = Gtk.Label(xalign=0, ellipsize=3)       # Pango.EllipsizeMode.END
        style = 'weight="bold"' if path == chosen else ''
        label.set_markup(f'<span alpha="60%">{GLib.markup_escape_text(mark)}</span>  '
                         f'<span {style}>{GLib.markup_escape_text(path)}</span>')
        btn.set_child(label)
        btn.update_property([Gtk.AccessibleProperty.LABEL], [said])
        btn.connect('clicked', lambda _b, p=path: choose(p))
        self.box.append(btn)

    def _note(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        label.add_css_class('dim-label')
        self.box.append(label)


class EditorPanel(Gtk.Paned):
    """La lista de archivos a un lado y nvim al otro, con un divisor que se arrastra:
    nvim se queda con todo lo que la ventana gane o pierda. La lista se pliega con ««» y
    vuelve con «»»; plegada, nvim ocupa todo el ancho. Quién guarda esa preferencia lo decide
    `on_fold` (la ventana: la comparten el Editor y el Taller)."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class('elyares-sources')
        self.on_fold = lambda folded: None
        self.folded = False
        self.files = FileList()
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = Gtk.Label(label='ARCHIVOS', xalign=0)
        title.add_css_class('elyares-section')
        title.set_hexpand(True)
        title.set_margin_start(SPACE[1])
        self.fold_btn = self._button('«', 'Ocultar la lista de archivos', lambda: self.set_folded(True, notify=True))
        head.append(title)
        head.append(self.fold_btn)
        self.side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.side.append(head)
        self.side.append(self.files)
        self.files.set_vexpand(True)
        self.nvim = TerminalPanel(kind=terminal.NVIM)
        self.nvim.set_visible(True)         # solo se ve cuando se ve el panel entero
        self.nvim.set_size_request(LIST_MIN, -1)
        self.nvim.set_hexpand(True)
        self.unfold_btn = self._button('»', 'Mostrar la lista de archivos', lambda: self.set_folded(False, notify=True))
        self.unfold_btn.set_valign(Gtk.Align.START)
        self.unfold_btn.set_visible(False)
        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        right.append(self.unfold_btn)
        right.append(self.nvim)
        self.set_start_child(self.side)
        self.set_end_child(right)
        self.set_position(LIST_W)
        self.set_resize_start_child(False)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)
        self.set_visible(False)

    @staticmethod
    def _button(text, said, call):
        btn = Gtk.Button(label=text)
        btn.add_css_class('elyares-btn')
        btn.add_css_class('compact')
        btn.update_property([Gtk.AccessibleProperty.LABEL], [said])
        btn.set_tooltip_text(said)
        btn.connect('clicked', lambda _b: call())
        return btn

    def set_folded(self, folded, notify=False):
        """Pliega o despliega la lista. `notify`: lo pidió un clic (y hay que guardarlo); la ventana
        solo sincroniza el estado sin avisar."""
        if folded == self.folded:
            return
        self.folded = folded
        self.side.set_visible(not folded)
        self.unfold_btn.set_visible(folded)
        if notify:
            self.on_fold(folded)
