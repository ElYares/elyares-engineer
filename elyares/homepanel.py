"""La vista Inicio de la ventana: el proyecto activo, un menú, los agentes y un panel de contexto.

Arriba el nombre del proyecto; a la izquierda un menú de atajos a las vistas; al centro una
rejilla de tarjetas de agentes (cinco y una punteada «+ n más», o todos en cuatro columnas) y,
abajo, el contexto del agente elegido: qué hace ahora y, si pide permiso, Permitir y Denegar.
Quien pide permiso sube primero, luego quien trabaja, y el elegido siempre se ve. Sin estado
propio de datos: lo llena la ventana con `set_data`; aquí solo viven lo elegido y el «ver todos».
"""

from gi.repository import GLib, Gtk, Pango

from . import habits, windowframe
from .windowframe import SPACE, load_css

# (clave, texto, qué es): un panel del contexto («pane») o una vista de la ventana («view»). Las tareas tienen su vista.
MENU = (('pomodoro', 'Pomodoro', 'view'), ('tasks', 'Tareas', 'view'), ('habits', 'Hábitos', 'pane'),
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
        self.context_sig = None     # el contexto se rehace solo si cambia lo suyo: no borra lo que escribes
        self.faces = []
        # El foco vuelve al control con la misma clave al rehacer (`focusables`, abajo).
        # El campo «Nuevo hábito» vive siempre: rehacer las casillas no borra lo escrito ni le quita el foco.
        self.habit_row = Gtk.Box(spacing=SPACE[1])
        self.habit_entry = Gtk.Entry(placeholder_text='Nuevo hábito (Enter para agregar)', max_length=40)
        self.habit_entry.set_hexpand(True)
        self.habit_entry.update_property([Gtk.AccessibleProperty.LABEL], ['Nuevo hábito'])
        self.habit_entry.connect('activate', self._add_habit)
        edit = Gtk.Button(label='Editar lista')
        edit.add_css_class('elyares-btn')
        edit.connect('clicked', self._edit_list)
        self.habit_row.append(self.habit_entry)
        self.habit_row.append(edit)
        self.habit_note = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.habit_note.add_css_class('elyares-muted')
        self.focusables = {('keep', 'entry'): self.habit_entry}
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
        picked = next((c for c in cards if c['role'] == self.picked), None)
        # Dos firmas: la rejilla cambia con cada paso de un agente; el contexto, solo con lo que muestra.
        # Con Hábitos abierto, lo que hagan los agentes no rehace el campo en el que escribes.
        sig = (project, self.picked, self.show_all,
               tuple((c['role'], c['name'], c['color'], c['busy'], c['ask'], c['state'], tuple(c['steps'])) for c in cards))
        held = windowframe.focused_key(self.focusables)
        if sig != self.signature:
            self.signature = sig
            self.title.set_label(project.upper() if project else 'SIN PROYECTO')
            self._menu(handlers)
            self._grid(cards, handlers)
        if self.pane == 'habits':
            context = ('habits', repr(habits.items()), habits.last_error())
        else:
            context = ('agent', picked and (picked['role'], picked['name'], picked['color'], picked['state'],
                                            tuple(picked['steps'][-4:]), picked['busy'], picked['ask']))
        if context != self.context_sig:
            self.context_sig = context
            self._context(picked, handlers)
        windowframe.refocus(self.focusables, held)

    def _forget(self, prefix):
        self.focusables = {k: w for k, w in self.focusables.items() if k[0] != prefix}

    def _menu(self, handlers):
        while (child := self.menu.get_first_child()) is not None:
            self.menu.remove(child)
        self._forget('menu')
        for key, text, kind in MENU:
            btn = Gtk.Button(label=text)
            btn.add_css_class('elyares-pill')
            btn.set_halign(Gtk.Align.FILL)
            btn.get_child().set_xalign(0)
            btn.connect('clicked', lambda _b, k=key, kd=kind: self._menu_click(k, kd, handlers))
            self.focusables[('menu', key)] = btn
            self.menu.append(btn)

    def _menu_click(self, key, kind, handlers):
        if kind == 'view':
            handlers['view'](key)
            return
        self.pane = 'agent' if self.pane == key else key
        self.context_sig = None
        self.set_data_again()

    def _grid(self, cards, handlers):
        while (child := self.grid.get_first_child()) is not None:
            self.grid.remove(child)
        self._forget('card')
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
        self.focusables[('card', '+more')] = btn
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
        """Una tarjeta es un botón: con el teclado se llega a ella y Enter o Espacio la elige."""
        tile = Gtk.Button()
        tile.add_css_class('elyares-card')
        tile.set_size_request(-1, 84)
        if card['role'] == self.picked:
            tile.add_css_class('raised')
        box = Gtk.Box(spacing=SPACE[2])
        tile.set_child(box)
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
        tile.update_property([Gtk.AccessibleProperty.LABEL], [f'{card["name"]}, {card["state"]}'])
        tile.connect('clicked', lambda _b, r=card['role']: self._pick(r))
        self.focusables[('card', card['role'])] = tile
        return tile

    def _pick(self, role):
        self.picked, self.pane = role, 'agent'
        self.signature = self.context_sig = None
        self.set_data_again()

    def _habits(self):
        items = habits.items()
        done = sum(1 for h in items if h['done_today'])
        head = Gtk.Label(label=f'HÁBITOS DE HOY · {done}/{len(items)}' if items else 'HÁBITOS', xalign=0)
        head.add_css_class('elyares-section')
        self.context.append(head)
        if not items:
            note = Gtk.Label(label=habits.last_error() or 'Tu lista está vacía. Escribe un hábito aquí abajo, o edita '
                                   f'tu archivo (un hábito por línea, con guion): {habits.list_path()}', xalign=0, wrap=True)
            note.add_css_class('elyares-muted')
            self.context.append(note)
        for h in items:
            check = Gtk.CheckButton(label=h['name'] + (f'   🔥{h["streak"]}' if h['streak'] else ''))
            check.set_active(h['done_today'])
            check.connect('toggled', lambda _b, n=h['name']: self._toggle_habit(n))
            self.focusables[('habit', h['name'].casefold())] = check
            self.context.append(check)
        self.context.append(self.habit_row)              # los mismos de siempre: lo escrito se queda
        self.context.append(self.habit_note)

    def _say(self, text):
        """Pone el aviso bajo el campo y, si GTK sabe, se lo dice al lector de pantalla."""
        self.habit_note.set_label(text)
        if text and hasattr(self.habit_note, 'announce'):
            self.habit_note.announce(text, Gtk.AccessibleAnnouncementPriority.MEDIUM)

    def _add_habit(self, entry):
        ok, said = habits.add(entry.get_text())
        if ok:
            entry.set_text('')
            self._say('')
            self.context_sig = None
            self.set_data_again()
            entry.grab_focus()                               # para agregar otro sin volver a tabular
        else:
            self._say(said)

    def _edit_list(self, _btn):
        ok, path = habits.edit()
        self._say('' if ok else f'No hay editor que lo abra. Ábrelo a mano: {path}')

    def _toggle_habit(self, name):
        habits.toggle(name)
        self.context_sig = None
        self.set_data_again()

    def _context(self, card, handlers):
        while (child := self.context.get_first_child()) is not None:
            self.context.remove(child)
        self._forget('habit')
        self._forget('ctx')
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
            # «Denegar» con velo neutro, igual que en la isla: no es la acción peligrosa
            for text, allow, tone in (('Permitir', True, 'primary'), ('Denegar', False, '')):
                btn = Gtk.Button(label=text)
                btn.add_css_class('elyares-btn')
                if tone:
                    btn.add_css_class(tone)
                btn.connect('clicked', lambda _b, a=allow: handlers['decide'](a))
                self.focusables[('ctx', text)] = btn
                row.append(btn)
            self.context.append(row)
        chat = Gtk.Button(label=f'Abrir el chat de {card["name"]}')
        chat.add_css_class('elyares-btn')
        chat.set_halign(Gtk.Align.START)
        chat.connect('clicked', lambda _b, r=card['role']: handlers['chat'](r))
        self.focusables[('ctx', 'chat')] = chat
        self.context.append(chat)
