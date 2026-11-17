"""La paleta de la ventana (Ctrl+K): un cuadro de búsqueda para ir a una vista o cambiar un ajuste.

Solo arma el widget y filtra; qué hace cada entrada lo decide quien la da (`Frame.open_palette`).
"""

import unicodedata

from gi.repository import Gdk, Gtk


def fold(text):
    """Minúsculas y sin acentos, para que «ajus» encuentre «Ajustes» y «sesion» a «Sesión»."""
    plain = unicodedata.normalize('NFD', text.lower())
    return ''.join(c for c in plain if not unicodedata.combining(c))


def matches(query, label):
    """Todas las palabras de `query` aparecen en `label`; sin consulta, entra todo."""
    text = fold(label)
    return all(word in text for word in fold(query).split())


class Palette(Gtk.Popover):
    def __init__(self):
        super().__init__()
        self.add_css_class('elyares-palette')
        self.set_autohide(True)
        self.set_has_arrow(False)
        self.entries = []               # (texto, nota, callback)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_spacing(6)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('Ir a una vista o cambiar un ajuste…')
        self.search.set_size_request(360, -1)
        self.search.connect('search-changed', lambda _e: self.list.invalidate_filter())
        self.search.connect('activate', lambda _e: self._run_first())
        box.append(self.search)
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.list.set_filter_func(self._visible)
        self.list.connect('row-activated', lambda _l, row: self._run(row))
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(260)
        scroll.set_max_content_height(260)
        scroll.set_child(self.list)
        box.append(scroll)
        self.set_child(box)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._key)
        self.search.add_controller(keys)

    def set_entries(self, entries):
        """`entries`: lista de (texto, nota, callback)."""
        self.entries = list(entries)
        while (row := self.list.get_row_at_index(0)) is not None:
            self.list.remove(row)
        for label, note, _cb in self.entries:
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            line.set_spacing(12)
            name = Gtk.Label(label=label, xalign=0, hexpand=True)
            hint = Gtk.Label(label=note, xalign=1)
            hint.add_css_class('elyares-muted')
            hint.add_css_class('elyares-small')
            line.append(name)
            line.append(hint)
            self.list.append(line)

    def _visible(self, row):
        return matches(self.search.get_text(), self.entries[row.get_index()][0])

    def _first(self):
        index = 0
        while (row := self.list.get_row_at_index(index)) is not None:
            if row.get_child_visible() and self._visible(row):
                return row
            index += 1
        return None

    def _run_first(self):
        row = self.list.get_selected_row()
        if row is None or not self._visible(row):
            row = self._first()
        if row is not None:
            self._run(row)

    def _run(self, row):
        callback = self.entries[row.get_index()][2]
        self.popdown()
        callback()

    def _key(self, _ctl, keyval, _code, _state):
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            row = self.list.get_selected_row() or self._first()
            step = 1 if keyval == Gdk.KEY_Down else -1
            index = row.get_index() + step if row else 0
            while (nxt := self.list.get_row_at_index(index)) is not None:
                if self._visible(nxt):
                    self.list.select_row(nxt)
                    return True
                index += step
            return True
        return False

    def show_at(self, parent):
        self.search.set_text('')
        self.list.invalidate_filter()
        first = self._first()
        if first is not None:
            self.list.select_row(first)
        if self.get_parent() is None:
            self.set_parent(parent)
        self.popup()
        self.search.grab_focus()
