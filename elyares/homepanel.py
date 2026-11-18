"""La vista Inicio de la ventana: el proyecto activo, un menú, los agentes y un panel de contexto.

Arriba el nombre del proyecto; a la izquierda un menú de atajos a las vistas; al centro una
rejilla de tarjetas de agentes (cinco y una punteada «+ n más», o todos en cuatro columnas) y,
abajo, el contexto del agente elegido: qué hace ahora y, si pide permiso, Permitir y Denegar.
Quien pide permiso sube primero, luego quien trabaja, y el elegido siempre se ve. Sin estado
propio de datos: lo llena la ventana con `set_data`; aquí solo viven lo elegido y el «ver todos».
"""

from gi.repository import GLib, Gtk, Pango

from . import habits
from .windowframe import SPACE, load_css

# (clave, texto, qué es): un panel del contexto («pane») o una vista de la ventana («view»). Las tareas viven en la vista Pomodoro.
MENU = (('pomodoro', 'Pomodoro', 'view'), ('pomodoro', 'Tareas', 'view'), ('habits', 'Hábitos', 'pane'),
        ('chat', 'Chat', 'view'), ('projects', 'Proyectos', 'view'), ('containers', 'Contenedores', 'view'))
SHOWN = 5                       # tarjetas a la vista antes de «+ n más»
COLS, COLS_ALL = 3, 4
FACE = 56


def ordered(cards, picked):
    """Quien pide permiso, luego quien trabaja, luego los libres; el elegido nunca se queda fuera de los SHOWN."""
    ranked = sorted(cards, key=lambda c: (not c['ask'], not c['busy']))
    head = ranked[:SHOWN]
    chosen = next((c for c in ranked if c['role'] == picked), None)
    if chosen is not None and chosen not in head:
        head = head[:SHOWN - 1] + [chosen]
    return head, ranked


class HomePanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[2])
        load_css()
        self.add_css_class('elyares-sources')
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self, f'set_margin_{side}')(SPACE[3])
        self.picked = ''            # el agente cuyo contexto se ve
        self.show_all = False
        self.pane = 'agent'         # qué ocupa el contexto: agent o habits
        self.signature = None
        self.faces = []
        self.title = Gtk.Label(xalign=.5)
        self.title.add_css_class('elyares-title')
        self.append(self.title)
        body = Gtk.Box(spacing=SPACE[3])
        body.set_vexpand(True)
        self.menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        self.menu.set_valign(Gtk.Align.START)
        self.menu.set_size_request(120, -1)
        self.main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[2])
        self.main.set_hexpand(True)
        self.grid = Gtk.Grid(column_spacing=SPACE[1], row_spacing=SPACE[1], column_homogeneous=True)
        self.context = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        self.context.add_css_class('elyares-card')
        self.context.set_vexpand(True)
        self.main.append(self.grid)
        self.main.append(self.context)
        body.append(self.menu)
        body.append(self.main)
        self.append(body)
        self.set_visible(False)

    def animate(self):
        for da in self.faces:
            da.queue_draw()

    def set_data(self, project, cards, handlers):
        """`cards`: un dict por agente (role, name, color, state, steps, busy, ask, pet).
        `handlers`: face(cr, role, pet, w, h, moving), decide(allow), view(clave), chat(role)."""
        self.last = (project, cards, handlers)
        if not self.picked or all(c['role'] != self.picked for c in cards):
            first = (next((c for c in cards if c['ask']), None) or next((c for c in cards if c['busy']), None)
                     or (cards[0] if cards else None))
            self.picked = first['role'] if first else ''
        sig = (project, self.picked, self.show_all, self.pane, repr(habits.items()),
               tuple((c['role'], c['busy'], c['ask'], c['state'], tuple(c['steps'])) for c in cards))
        if sig == self.signature:
            return
        self.signature = sig
        self.title.set_label(project.upper() if project else 'SIN PROYECTO')
        self._menu(handlers)
        self._grid(cards, handlers)
        self._context(next((c for c in cards if c['role'] == self.picked), None), handlers)

    def _menu(self, handlers):
        while (child := self.menu.get_first_child()) is not None:
            self.menu.remove(child)
        for key, text, kind in MENU:
            btn = Gtk.Button(label=text)
            btn.add_css_class('elyares-pill')
            btn.set_halign(Gtk.Align.FILL)
            btn.get_child().set_xalign(0)
            btn.connect('clicked', lambda _b, k=key, kd=kind: self._menu_click(k, kd, handlers))
            self.menu.append(btn)

    def _menu_click(self, key, kind, handlers):
        if kind == 'view':
            handlers['view'](key)
            return
        self.pane = 'agent' if self.pane == key else key
        self.signature = None
        self.set_data_again()

    def _grid(self, cards, handlers):
        while (child := self.grid.get_first_child()) is not None:
            self.grid.remove(child)
        self.faces = []
        head, ranked = ordered(cards, self.picked)
        shown = ranked if self.show_all else head
        tiles = [self._card(c, handlers) for c in shown]
        more = len(ranked) - len(head)
        if more > 0 or self.show_all:
            tiles.append(self._more(more))
        cols = COLS_ALL if self.show_all else COLS
        for i, tile in enumerate(tiles):
            self.grid.attach(tile, i % cols, i // cols, 1, 1)

    def _more(self, more):
        btn = Gtk.Button(label='Ver menos' if self.show_all else f'+ {more} más')
        btn.add_css_class('elyares-pill')
        btn.connect('clicked', self._toggle_all)
        return btn

    def _toggle_all(self, _btn):
        self.show_all = not self.show_all
        self.signature = None
        self.set_data_again()

    def set_data_again(self):
        """Rehace con lo último que dio la ventana (se llama tras un clic local)."""
        if self.last is not None:
            self.set_data(*self.last)

    last = None

    def _card(self, card, handlers):
        box = Gtk.Box(spacing=SPACE[2])
        box.add_css_class('elyares-card')
        box.set_size_request(-1, 84)
        if card['role'] == self.picked:
            box.add_css_class('raised')
        face = Gtk.DrawingArea()
        face.set_content_width(FACE)
        face.set_content_height(FACE)
        face.set_valign(Gtk.Align.CENTER)
        moving = card['busy']
        face.set_draw_func(lambda _da, cr, w, h, c=card: handlers['face'](cr, c['role'], c['pet'], w, h, moving))
        if moving:
            self.faces.append(face)
        box.append(face)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        name = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        name.set_markup(f'<span foreground="{card["color"]}" weight="bold">{GLib.markup_escape_text(card["name"])}</span>')
        state = Gtk.Label(label=card['state'], xalign=0, ellipsize=Pango.EllipsizeMode.END)
        state.add_css_class('elyares-muted')
        text.append(name)
        text.append(state)
        box.append(text)
        box.update_property([Gtk.AccessibleProperty.LABEL], [f'{card["name"]}, {card["state"]}'])
        click = Gtk.GestureClick()
        click.connect('released', lambda *_a, r=card['role']: self._pick(r))
        box.add_controller(click)
        return box

    def _pick(self, role):
        self.picked, self.pane = role, 'agent'
        self.signature = None
        self.set_data_again()

    def _habits(self):
        items = habits.items()
        if not items:
            self.context.append(Gtk.Label(label='Sin hábitos. Agrega uno con: elyares-ctl habit add "Leer 20 min"',
                                          xalign=0, wrap=True))
            return
        head = Gtk.Label(label=f'HÁBITOS DE HOY · {sum(1 for h in items if h["done_today"])}/{len(items)}', xalign=0)
        head.add_css_class('elyares-section')
        self.context.append(head)
        for h in items:
            check = Gtk.CheckButton(label=h['name'] + (f'   🔥{h["streak"]}' if h['streak'] else ''))
            check.set_active(h['done_today'])
            check.connect('toggled', lambda _b, n=h['name']: self._toggle_habit(n))
            self.context.append(check)

    def _toggle_habit(self, name):
        habits.toggle(name)
        self.signature = None
        self.set_data_again()

    def _context(self, card, handlers):
        while (child := self.context.get_first_child()) is not None:
            self.context.remove(child)
        if self.pane == 'habits':
            self._habits()
            return
        if card is None:
            self.context.append(Gtk.Label(label='Sin agentes a la vista.', xalign=0))
            return
        head = Gtk.Label(xalign=0)
        head.set_markup(f'<span foreground="{card["color"]}" weight="bold">{GLib.markup_escape_text(card["name"])}</span>'
                        f' · {GLib.markup_escape_text(card["state"])}')
        self.context.append(head)
        for line in card['steps'][-4:] or (['Libre: nada en curso.'] if not card['busy'] else []):
            step = Gtk.Label(label=line, xalign=0, wrap=True)
            step.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            step.add_css_class('elyares-muted')
            self.context.append(step)
        if card['ask']:
            row = Gtk.Box(spacing=SPACE[1])
            for text, allow, tone in (('Permitir', True, 'primary'), ('Denegar', False, 'danger')):
                btn = Gtk.Button(label=text)
                btn.add_css_class('elyares-btn')
                btn.add_css_class(tone)
                btn.connect('clicked', lambda _b, a=allow: handlers['decide'](a))
                row.append(btn)
            self.context.append(row)
        chat = Gtk.Button(label=f'Abrir el chat de {card["name"]}')
        chat.add_css_class('elyares-btn')
        chat.set_halign(Gtk.Align.START)
        chat.connect('clicked', lambda _b, r=card['role']: handlers['chat'](r))
        self.context.append(chat)
