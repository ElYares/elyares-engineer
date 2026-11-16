"""La vista Editor: la lista de lo que cambió en el proyecto y, al lado, nvim.

A la izquierda los archivos con cambios sin commitear (los que toca el agente o
tú); a la derecha un nvim con tu configuración, en una sesión de tmux que
sobrevive al reload. Un clic en un archivo de la lista se lo pide a ese nvim por
su socket: la app no teclea nada en él. El Taller usa esta misma pieza arriba.
"""

import gi

gi.require_version('Gtk', '4.0')

from gi.repository import Gdk, GLib, Gtk

from . import gitview, responsive, terminal, themes, windowframe
from .terminalpanel import TerminalPanel
from .windowframe import SPACE

LIST_W = 300              # lo que mide la lista al abrir; el divisor se arrastra
LIST_MIN = 160
CODES = {'M': 'M', 'A': 'A', 'D': 'D', 'R': 'R', '?': 'N', 'U': '!'}      # la marca de cada archivo cambiado
MAX_ROWS = 1500           # filas del árbol que se dibujan; más que eso, un repositorio enorme con todo abierto
INDENT = 14


def tones():
    """El color de cada cambio (los de aviso, que siguen al tema claro/oscuro): modificado, nuevo, borrado, en conflicto."""
    green, amber, red = themes.signal()
    return {'M': amber, 'A': green, '?': green, 'D': red, 'R': amber, 'U': red}


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
        self.on_chosen = lambda: None       # el Editor lo usa para volver a nvim en angosto
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
        extra = f'  <span foreground="{tones()["M"]}">● {row["count"]}</span>' if row['count'] and not row['open'] else ''
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
        color = tones().get(code)
        text = GLib.markup_escape_text(row['name'])
        name = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        name.set_markup(f'<span foreground="{color}">{text}</span>' if color else text)
        if path in edited:
            mark = f'<span foreground="{windowframe.ACCENT}">✎</span>'
        else:
            mark = f'<span foreground="{color}" weight="bold">{CODES.get(code, "M")}</span>' if color else ''
        line = Gtk.Box(spacing=SPACE[0])
        line.append(self._mark(mark))
        line.append(name)
        added, removed = (state.stats or {}).get(path, (0, 0))
        if added or removed:
            amount = Gtk.Label(xalign=1)
            amount.set_markup(f'<span foreground="{tones()["A"]}">+{added}</span> '
                              f'<span foreground="{tones()["D"]}">−{removed}</span>')
            amount.add_css_class('dim-label')
            line.append(amount)
        said = f'{gitview.LABELS.get(code, "sin cambios")}: {path}'
        btn = self._button(row['depth'], said, lambda p=path: (choose(p), self.on_chosen()))
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
        self.files.on_chosen = self._chosen
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = Gtk.Label(label='ARCHIVOS', xalign=0)
        title.add_css_class('elyares-section')
        title.set_hexpand(True)
        title.set_margin_start(SPACE[1])
        self.narrow = False             # ventana angosta: la lista y nvim no caben juntos, se turnan
        self.sheet = False              # en angosto: ¿se ve la lista (y no nvim)?
        self.fold_btn = self._button('«', 'Ocultar la lista de archivos', lambda: self._toggle_list(False))
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
        self.unfold_btn = self._button('»', 'Mostrar la lista de archivos', lambda: self._toggle_list(True))
        self.unfold_btn.set_valign(Gtk.Align.START)
        self.unfold_btn.set_visible(False)
        right = self.right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        right.append(self.unfold_btn)
        right.append(self.nvim)
        self.set_start_child(self.side)
        self.set_end_child(right)
        self.set_position(LIST_W)
        self.set_resize_start_child(False)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)
        self.add_tick_callback(self._measure)
        self.set_visible(False)

    def _measure(self, _widget, _clock):
        width = self.get_width()
        if width:
            narrow = responsive.mode(width) == responsive.COMPACT
            if narrow != self.narrow:
                self.narrow, self.sheet = narrow, False
                self._apply()
        return GLib.SOURCE_CONTINUE

    def _chosen(self):
        """Elegido un archivo en angosto, se vuelve a nvim para verlo."""
        if self.narrow and self.sheet:
            self.sheet = False
            self._apply()

    def _toggle_list(self, show):
        """«»» y «««: con espacio, pliega o despliega la lista (y se guarda); en angosto la lista y nvim se turnan."""
        if self.narrow:
            self.sheet = show
            self._apply()
        else:
            self.set_folded(not show, notify=True)

    def _apply(self):
        if self.narrow:
            self.side.set_visible(self.sheet)
            self.right.set_visible(not self.sheet)
            self.unfold_btn.set_visible(True)
        else:
            self.side.set_visible(not self.folded)
            self.right.set_visible(True)
            self.unfold_btn.set_visible(self.folded)

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
        self._apply()
        if notify:
            self.on_fold(folded)
