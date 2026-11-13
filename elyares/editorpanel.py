"""La vista Editor: lo que cambió en el proyecto, el archivo y su diff.

Un visor, no un editor: nada se escribe. Muestra los archivos con cambios
(los que toca el agente o tú desde otro sitio) y, del elegido, el archivo con
su sintaxis y el diff contra HEAD. Sin estado propio: la llena la ventana.
"""

import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('GtkSource', '5')

from gi.repository import GLib, Gtk, GtkSource

from . import gitview, themes
from .windowframe import SPACE

LIST_W = 280              # lo que mide la lista al abrir; el divisor se arrastra
LIST_MIN = 160
CODES = {'M': 'M', 'A': 'A', 'D': 'D', 'R': 'R', '?': 'N', 'U': '!'}      # la marca de cada fila


def scheme():
    """El esquema de colores de GtkSource, claro u oscuro según el tema, o None si no existe."""
    manager = GtkSource.StyleSchemeManager.get_default()
    for name in (('Adwaita', 'classic') if themes.is_light() else ('Adwaita-dark', 'classic-dark')):
        found = manager.get_scheme(name)
        if found is not None:
            return found
    return None


def make_view():
    view = GtkSource.View()
    view.set_editable(False)
    view.set_monospace(True)
    view.set_show_line_numbers(True)
    view.set_wrap_mode(Gtk.WrapMode.NONE)
    view.set_left_margin(SPACE[1])
    return view


class EditorPanel(Gtk.Paned):
    """La lista de archivos a un lado y el visor al otro, con un divisor que se arrastra:
    el visor se queda con todo lo que la ventana gane o pierda."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class('elyares-sources')
        self.signature = self.file_sig = self.theme_sig = None
        self.files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.files_box, f'set_margin_{side}')(SPACE[1])
        side_scroll = Gtk.ScrolledWindow()
        side_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        side_scroll.set_size_request(LIST_MIN, -1)
        side_scroll.set_child(self.files_box)
        self.head = Gtk.Label(xalign=0)
        self.head.set_margin_start(SPACE[1])
        self.head.set_margin_top(SPACE[1])
        self.note = Gtk.Label(xalign=0)
        self.note.add_css_class('dim-label')
        self.note.set_margin_start(SPACE[1])
        self.file_view, self.diff_view = make_view(), make_view()
        self.tabs = Gtk.Notebook()
        self.tabs.set_vexpand(True)
        self.tabs.set_hexpand(True)
        for title, view in (('Archivo', self.file_view), ('Cambios', self.diff_view)):
            holder = Gtk.ScrolledWindow()
            holder.set_child(view)
            self.tabs.append_page(holder, Gtk.Label(label=title))
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        right.set_hexpand(True)
        right.set_size_request(LIST_MIN, -1)
        right.append(self.head)
        right.append(self.note)
        right.append(self.tabs)
        self.set_start_child(side_scroll)
        self.set_end_child(right)
        self.set_position(LIST_W)
        self.set_resize_start_child(False)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)
        self.set_visible(False)

    def set_editor(self, state, handlers):
        """`state`: un `gitview.State`. `handlers`: choose(ruta)."""
        theme = (themes.current, themes.is_light())
        if theme != self.theme_sig:
            self.theme_sig = theme
            found = scheme()
            for view in (self.file_view, self.diff_view):
                view.get_buffer().set_style_scheme(found)
        sig = (state.root, state.branch, repr(state.files), state.chosen)
        if sig != self.signature:
            self.signature = sig
            self._head(state)
            self._files(state, handlers)
        body = (state.chosen, state.text, state.note, state.diff)
        if body != self.file_sig:
            self.file_sig = body
            self._body(state)

    def _head(self, state):
        where = GLib.markup_escape_text(os.path.basename(state.root.rstrip('/')) or state.root or 'sin proyecto')
        on = f'  <span alpha="60%">{GLib.markup_escape_text(state.branch)}</span>' if state.branch else ''
        self.head.set_markup(f'<b>{where}</b>{on}')

    def _files(self, state, handlers):
        while (child := self.files_box.get_first_child()) is not None:
            self.files_box.remove(child)
        if state.files is None:
            text = 'Buscando el proyecto…' if not state.root else 'Esta carpeta no es un repositorio de git.'
            self._side_note(text)
        elif not state.files:
            self._side_note('Sin cambios. Cuando el agente (o tú) toque un archivo, aparece aquí.')
        for code, path in state.files or []:
            btn = Gtk.Button()
            btn.add_css_class('elyares-btn')
            btn.set_halign(Gtk.Align.FILL)
            label = Gtk.Label(xalign=0, ellipsize=3)       # Pango.EllipsizeMode.END
            mark = GLib.markup_escape_text(CODES.get(code, 'M'))
            style = 'weight="bold"' if path == state.chosen else ''
            label.set_markup(f'<span alpha="60%">{mark}</span>  <span {style}>{GLib.markup_escape_text(path)}</span>')
            btn.set_child(label)
            btn.update_property([Gtk.AccessibleProperty.LABEL],
                                [f'{gitview.LABELS.get(code, "")}: {path}'])
            btn.connect('clicked', lambda _b, p=path: handlers['choose'](p))
            self.files_box.append(btn)

    def _side_note(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        label.add_css_class('dim-label')
        self.files_box.append(label)

    def _body(self, state):
        langs = GtkSource.LanguageManager.get_default()
        self._fill(self.file_view, state.text, langs.guess_language(state.chosen, None) if state.chosen else None)
        self._fill(self.diff_view, state.diff or '', langs.get_language('diff'))
        self.note.set_text(state.note)
        self.note.set_visible(bool(state.note))

    @staticmethod
    def _fill(view, text, lang):
        """Cambia el texto sin mandar el scroll al principio: el agente edita mientras se mira."""
        adj = view.get_parent().get_vadjustment() if view.get_parent() is not None else None
        keep = adj.get_value() if adj is not None else 0
        buf = view.get_buffer()
        buf.set_language(lang)
        buf.set_text(text)
        if adj is not None and keep:
            GLib.idle_add(lambda: (adj.set_value(keep), False)[1])
