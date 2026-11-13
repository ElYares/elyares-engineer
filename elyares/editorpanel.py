"""La vista Editor: la lista de lo que cambió en el proyecto y, al lado, nvim.

A la izquierda los archivos con cambios sin commitear (los que toca el agente o
tú); a la derecha un nvim con tu configuración, en una sesión de tmux que
sobrevive al reload. Un clic en un archivo de la lista se lo pide a ese nvim por
su socket: la app no teclea nada en él. El Taller usa esta misma pieza arriba.
"""

import gi

gi.require_version('Gtk', '4.0')

from gi.repository import Gdk, GLib, Gtk

from . import gitview, terminal
from .terminalpanel import TerminalPanel
from .windowframe import SPACE

LIST_W = 300              # lo que mide la lista al abrir; el divisor se arrastra
LIST_MIN = 160
CODES = {'M': 'M', 'A': 'A', 'D': 'D', 'R': 'R', '?': 'N', 'U': '!'}      # la marca de cada archivo cambiado
MAX_ROWS = 1500           # filas del árbol que se dibujan; más que eso, un repositorio enorme con todo abierto
INDENT = 14
# El color de cada cambio (los de aviso, no del tema): modificado, nuevo, borrado, en conflicto.
TONES = {'M': '#f5c542', 'A': '#4ade80', '?': '#4ade80', 'D': '#ff6b6b', 'R': '#f5c542', 'U': '#ff6b6b'}
AGENT = '#6ea8ff'         # lo que tocó el agente en el chat
CSS = """
.ftree-row { background: none; border: none; box-shadow: none; border-radius: 6px; padding: 1px 4px; min-height: 22px; }
.ftree-row:hover { background: alpha(currentColor, 0.08); }
.ftree-row.picked { background: alpha(currentColor, 0.16); }
"""
_css = None


def load_css():
    global _css
    if _css is None:
        _css = Gtk.CssProvider()
        _css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), _css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)


class FileList(Gtk.ScrolledWindow):
    """El árbol del proyecto: carpetas que se abren y se cierran y, en otro color, los archivos que
    cambiaron (amarillo modificado, verde nuevo, rojo borrado) con sus líneas `+n −n`. Cada proyecto
    se acuerda de qué carpetas tenía abiertas; la primera vez, abre las que tienen cambios."""

    def __init__(self):
        super().__init__()
        load_css()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_size_request(LIST_MIN, -1)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.box, f'set_margin_{side}')(SPACE[0])
        self.set_child(self.box)
        self.signature = None
        self.expanded = {}          # raíz del proyecto → carpetas abiertas
        self.last = None            # (estado, choose, edited) de la última vez, para repintar al abrir o cerrar

    def set_files(self, state, choose, edited=()):
        """`state`: un `gitview.State`. `choose(ruta)`: el clic en un archivo. `edited`: las rutas
        (relativas al proyecto) que el agente cambió en el chat, la última primero."""
        self.last = (state, choose, tuple(edited))
        if state.root not in self.expanded and state.files is not None:
            self.expanded[state.root] = gitview.parents([p for _c, p in state.files] + list(edited))
        self._render()

    def collapse_all(self):
        if self.last:
            self.expanded[self.last[0].root] = set()
            self._render()

    def expand_all(self):
        if self.last:
            self.expanded[self.last[0].root] = gitview.parents(self.last[0].paths)
            self._render()

    def _toggle(self, path):
        opened = self.expanded.setdefault(self.last[0].root, set())
        opened.symmetric_difference_update({path})
        self._render()

    def _render(self):
        state, choose, edited = self.last
        opened = self.expanded.get(state.root, set())
        sig = (state.root, state.branch, repr(state.files), state.chosen, hash(tuple(state.paths)),
               repr(state.stats), edited, frozenset(opened))
        if sig == self.signature:
            return
        self.signature = sig
        adj = self.get_vadjustment()
        keep = adj.get_value()
        while (child := self.box.get_first_child()) is not None:
            self.box.remove(child)
        if state.files is None:
            self._note('Buscando el proyecto…' if not state.root else 'Esta carpeta no es un repositorio de git.')
            return
        changes = {path: code for code, path in state.files}
        rows = gitview.tree_rows(state.paths, changes, opened)
        if not rows:
            self._note('El proyecto no tiene archivos todavía.')
        for row in rows[:MAX_ROWS]:
            self.box.append(self._dir(row) if row['dir'] else self._file(row, state, choose, edited))
        if len(rows) > MAX_ROWS:
            self._note(f'… y {len(rows) - MAX_ROWS} más. Cierra carpetas para verlas.')
        GLib.idle_add(adj.set_value, keep)      # rehacer el árbol no devuelve el scroll arriba

    def _button(self, depth, said, call):
        btn = Gtk.Button()
        btn.add_css_class('ftree-row')
        btn.set_halign(Gtk.Align.FILL)
        btn.set_margin_start(depth * INDENT)
        btn.update_property([Gtk.AccessibleProperty.LABEL], [said])
        btn.connect('clicked', lambda _b: call())
        return btn

    @staticmethod
    def _mark(markup):
        """La columna de la marca (▸ ▾ M A D ✎): de ancho fijo, para que los nombres queden alineados."""
        label = Gtk.Label(xalign=0.5, width_chars=2)
        label.set_markup(markup)
        return label

    def _dir(self, row):
        extra = f'  <span foreground="{TONES["M"]}">● {row["count"]}</span>' if row['count'] and not row['open'] else ''
        name = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        name.set_markup(f'<b>{GLib.markup_escape_text(row["name"])}</b>{extra}')
        line = Gtk.Box(spacing=SPACE[0])
        line.append(self._mark(f'<span alpha="60%">{"▾" if row["open"] else "▸"}</span>'))
        line.append(name)
        said = f'Carpeta {row["path"]}: {"cerrar" if row["open"] else "abrir"}'
        btn = self._button(row['depth'], said, lambda p=row['path']: self._toggle(p))
        btn.set_child(line)
        return btn

    def _file(self, row, state, choose, edited):
        path, code = row['path'], row['code']
        color = TONES.get(code)
        text = GLib.markup_escape_text(row['name'])
        name = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        name.set_markup(f'<span foreground="{color}">{text}</span>' if color else text)
        if path in edited:
            mark = f'<span foreground="{AGENT}">✎</span>'
        else:
            mark = f'<span foreground="{color}" weight="bold">{CODES.get(code, "M")}</span>' if color else ''
        line = Gtk.Box(spacing=SPACE[0])
        line.append(self._mark(mark))
        line.append(name)
        added, removed = (state.stats or {}).get(path, (0, 0))
        if added or removed:
            amount = Gtk.Label(xalign=1)
            amount.set_markup(f'<span foreground="{TONES["A"]}">+{added}</span> '
                              f'<span foreground="{TONES["D"]}">−{removed}</span>')
            amount.add_css_class('dim-label')
            line.append(amount)
        said = f'{gitview.LABELS.get(code, "sin cambios")}: {path}'
        btn = self._button(row['depth'], said, lambda p=path: choose(p))
        if path == state.chosen:
            btn.add_css_class('picked')
        btn.set_child(line)
        return btn

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
        head.append(self._button('⊟', 'Cerrar todas las carpetas', lambda: self.files.collapse_all()))
        head.append(self._button('⊞', 'Abrir todas las carpetas', lambda: self.files.expand_all()))
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
