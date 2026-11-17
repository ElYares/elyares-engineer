"""La vista «Git» de la ventana: los PRs abiertos y las revisiones que te piden, con el estado de su CI.

Solo muestra lo que ya trae la fuente de GitHub (`github.items`); un clic abre el PR en el navegador.
"""

from gi.repository import Gtk, Pango

from . import themes
from . import windowframe
from .windowframe import SPACE

# El tono de `github.items` -> (índice en `themes.signal()` o None, texto del chip).
CHIPS = {'ok': (0, 'verde'), 'run': (1, 'corriendo'), 'bad': (2, 'rojo'), 'info': (None, 'revisión')}
ORDER = {'bad': 0, 'info': 1, 'run': 2, 'ok': 3}      # lo que pide atención, arriba


def order(items):
    """Rojos primero, luego revisiones pedidas, corriendo, verdes y sin checks; estable dentro de cada grupo."""
    return sorted(items, key=lambda it: ORDER.get(it.get('tone'), 4))


def chip(item):
    """(texto, índice de color de aviso o None) del chip de un PR."""
    index, text = CHIPS.get(item.get('tone'), (None, 'sin checks'))
    return text, index


class GitPanel(Gtk.ScrolledWindow):
    """Sin estado propio: la llena la isla con lo que sabe la fuente de GitHub."""

    def __init__(self):
        super().__init__()
        self.add_css_class('elyares-sources')
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.page, f'set_margin_{side}')(SPACE[2])
        self.set_child(self.page)
        self.signature = None
        self.set_visible(False)

    def set_prs(self, items, state, handlers):
        """`items`: lo de `github.items`; `state`: 'on', 'bad' u 'off' de la fuente. `handlers`: open(url)."""
        sig = (state, repr(items), themes.is_light())
        if sig == self.signature:
            return
        self.signature = sig
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        if state != 'on':
            text = ('GitHub está apagado en Ajustes.' if state == 'off'
                    else 'GitHub no responde. Revisa la sesión con: gh auth status')
            note = Gtk.Label(label=text, xalign=0, wrap=True)
            note.add_css_class('elyares-muted')
            self.page.append(note)
            return
        if not items:
            note = Gtk.Label(label='Sin PRs abiertos ni revisiones pendientes.', xalign=0)
            note.add_css_class('elyares-muted')
            self.page.append(note)
            return
        for item in order(items):
            self.page.append(self._row(item, handlers))

    def _row(self, item, handlers):
        row = Gtk.Button()
        row.add_css_class('elyares-card')
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[2])
        text, index = chip(item)
        color = themes.signal()[index] if index is not None else windowframe.MUTED
        tag = Gtk.Label()
        tag.set_markup(f'<span foreground="{color}" weight="bold">● {text}</span>')
        tag.set_size_request(110, -1)
        tag.set_xalign(0)
        title = Gtk.Label(label=f'{item["where"]}#{item["number"]}  {item["title"]}', xalign=0, hexpand=True)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        who = Gtk.Label(label=item['who'], xalign=1)
        who.add_css_class('elyares-muted')
        line.append(tag)
        line.append(title)
        line.append(who)
        row.set_child(line)
        row.connect('clicked', lambda _b, url=item['url']: handlers['open'](url))
        return row
