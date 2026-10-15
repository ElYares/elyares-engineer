"""El marco de widgets de la ventana de la app (decisión 009 del vault).

La ventana lleva widgets GTK4 en lo que es control —barra de título, vistas,
barra lateral— y deja en Cairo lo que es dibujo: el `overlay` de la isla va
dentro, como un contenido más, hasta que cada vista se migre. Este módulo solo
arma los widgets; qué hace cada botón lo decide quien lo crea con `on_view`.
"""

from gi.repository import Gdk, GLib, Gtk, Pango

# (clave, texto) en el orden de la barra de título.
VIEWS = (('board', 'Tablero'), ('chat', 'Chat'), ('flows', 'Flujos'),
         ('projects', 'Proyectos'), ('sources', 'Fuentes'))
SIDEBAR_W = 180
FOLD_W = 640                    # más angosta que esto, la barra lateral se pliega y el texto conserva su tamaño

# Tokens (HU-005). Espacios en px: 4, 8, 12, 16; radios: 8 y 12. Tres
# superficies, de la más honda a la más alta: ventana, tarjeta, tarjeta
# elevada. El texto y su relleno van en par con contraste de 4.5:1 o más.
SPACE = (4, 8, 12, 16)
RADIUS = (8, 12)
SURFACE = ('#050608', '#10131a', '#1a1f2b')     # ventana, tarjeta, tarjeta elevada
INK, MUTED = '#f2f5ff', '#8f9ab8'               # sobre cualquiera de las tres
ACCENT = '#6ea8ff'                              # foco y botón primario
DANGER = '#ff6b6b'                              # el aviso rojo, no del tema

CSS = f"""
.elyares-bar {{ background: {SURFACE[0]}; color: {INK}; border: none; box-shadow: none; }}
.elyares-bar button {{ background: {SURFACE[1]}; color: {MUTED}; border: none; box-shadow: none;
  padding: {SPACE[0]}px {SPACE[2]}px; border-radius: {RADIUS[0]}px; }}
.elyares-bar button:checked {{ background: {SURFACE[2]}; color: {INK}; }}
.elyares-side {{ background: {SURFACE[0]}; color: {INK}; padding: {SPACE[1]}px; }}
.elyares-side row:selected {{ background: {SURFACE[2]}; color: {INK}; }}
.elyares-side row {{ border-radius: {RADIUS[0]}px; padding: {SPACE[1]}px {SPACE[2]}px; }}
.elyares-card {{ background: {SURFACE[1]}; color: {INK}; border-radius: {RADIUS[1]}px; padding: {SPACE[1]}px {SPACE[2]}px; }}
.elyares-card.raised {{ background: {SURFACE[2]}; }}
.elyares-btn {{ background: {SURFACE[2]}; color: {INK}; border-radius: {RADIUS[0]}px;
  padding: {SPACE[1]}px {SPACE[3]}px; border: none; box-shadow: none; }}
.elyares-btn.primary {{ background: {ACCENT}; color: {SURFACE[0]}; }}
.elyares-btn.danger {{ background: {DANGER}; color: {SURFACE[0]}; }}
.elyares-chathead {{ background: {SURFACE[0]}; color: {INK}; padding: {SPACE[1]}px {SPACE[2]}px;
  border-bottom: 1px solid {SURFACE[2]}; }}
.elyares-bar button:focus-visible, .elyares-side row:focus-visible, .elyares-btn:focus-visible {{
  outline: 2px solid {ACCENT}; outline-offset: 2px; }}
"""

_provider = None


def load_css():
    """Instala los estilos una sola vez para toda la app."""
    global _provider
    if _provider is None:
        _provider = Gtk.CssProvider()
        _provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class Frame:
    """Barra de título con las vistas, barra lateral y el hueco del contenido."""

    def __init__(self, on_view, on_session=None):
        self.on_view = on_view
        self.on_session = on_session or (lambda sid: None)
        self.session_rows = ()          # lo último que se armó: sin cambios no se reconstruye
        self.syncing = False            # sincronizar los botones no es un clic de Yared
        self.buttons = {}
        load_css()
        self.header = Gtk.HeaderBar()
        self.header.add_css_class('elyares-bar')
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        nav.add_css_class('linked')
        first = None
        for key, text in VIEWS:
            btn = Gtk.ToggleButton(label=text)
            if first is None:
                first = btn
            else:
                btn.set_group(first)
            btn.connect('toggled', self._toggled, key)
            nav.append(btn)
            self.buttons[key] = btn
        self.header.set_title_widget(nav)
        self.board = BoardPanel()
        self.chat_head = ChatHead()
        self.sidebar = Gtk.ListBox()
        self.sidebar.set_size_request(SIDEBAR_W, -1)
        self.sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar.add_css_class('elyares-side')
        self.sidebar.connect('row-activated', self._picked)
        self.slot = Gtk.Box()           # donde va el contenido
        self.slot.set_hexpand(True)
        self.slot.set_vexpand(True)
        self.body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.body.append(self.sidebar)
        self.body.append(self.slot)

    def attach(self, win):
        win.set_titlebar(self.header)
        win.set_child(self.body)

    def set_content(self, child):
        """Pone (o quita, con None) el contenido; nunca más de uno."""
        old = self.slot.get_first_child()
        if old is not None:
            self.slot.remove(old)
        if child is not None:
            self.slot.append(child)

    def sync(self, view):
        """Marca la vista que está a la vista, sin disparar `on_view`."""
        btn = self.buttons.get(view)
        if btn is None or btn.get_active():
            return
        self.syncing = True
        try:
            btn.set_active(True)
        finally:
            self.syncing = False

    def set_sessions(self, rows, chosen, face=None):
        """La barra lateral: una fila por sesión (o por agente en el chat),
        `rows` = [(sid, nombre, color del punto o None, texto de estado[, rol])].
        Con rol y `face(cr, rol, w, h)`, la fila lleva la cara en vez del
        punto. El estado va también en texto y en el nombre accesible: no
        depende solo del color."""
        key = (tuple(rows), chosen)
        if key == self.session_rows:
            return
        self.session_rows = key
        while (row := self.sidebar.get_first_child()) is not None:
            self.sidebar.remove(row)
        picked = None
        for sid, name, color, text, *role in rows:
            row = Gtk.ListBoxRow()
            row.sid = sid
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            if role and face is not None:
                dot = Gtk.DrawingArea()
                dot.set_content_width(28)
                dot.set_content_height(28)
                dot.set_draw_func(lambda _da, cr, w, h, r=role[0]: face(cr, r, w, h))
            else:
                dot = Gtk.Label()
                dot.set_markup(f'<span foreground="{color or MUTED}">{"●" if color else "○"}</span>')
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            title = Gtk.Label(label=name, xalign=0)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            sub = Gtk.Label(label=text, xalign=0)
            sub.add_css_class('dim-label')
            col.append(title)
            col.append(sub)
            box.append(dot)
            box.append(col)
            row.set_child(box)
            row.update_property([Gtk.AccessibleProperty.LABEL], [f'{name}, {text}'])
            self.sidebar.append(row)
            if sid == chosen:
                picked = row
        if picked is not None:
            self.sidebar.select_row(picked)     # no emite `row-activated`: no es un clic

    def _picked(self, _box, row):
        self.on_session(row.sid)

    def fold(self, width):
        """Plegada, la barra lateral no achica el contenido: con la ventana
        angosta (hasta 480) el dibujo conserva todo su ancho."""
        self.sidebar.set_visible(not width or width >= FOLD_W)

    def chrome_h(self):
        """Lo que la barra de título le quita al alto de la ventana."""
        return self.header.get_height()

    def _toggled(self, btn, key):
        if btn.get_active() and not self.syncing:
            self.on_view(key)


class BoardPanel(Gtk.ScrolledWindow):
    """El tablero en widgets: una tarjeta por cada uno que trabaja, con su
    cara, su estado y sus pasos y, si pide permiso, lo que quiere hacer con
    Permitir y Denegar; los libres van en una fila debajo. Lo llena la isla con
    `set_cards`; aquí no hay estado propio."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_valign(Gtk.Align.START)
        self.set_halign(Gtk.Align.FILL)
        self.add_css_class('elyares-board')
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.page, f'set_margin_{side}')(SPACE[1])
        self.set_child(self.page)
        self.signature = None
        self.faces = []
        self.set_visible(False)

    def place(self, height):
        """Visible con ese alto, o escondido (`height` 0)."""
        self.set_visible(height > 0)
        if height > 0:
            self.set_size_request(-1, int(height))
            self.set_vexpand(False)

    def animate(self):
        """Las caras de los que trabajan se mueven: las pide repintar."""
        for da in self.faces:
            da.queue_draw()

    def set_cards(self, cards, free, handlers):
        """`cards`: lo que trabaja; `free`: lo que descansa. Cada uno es un
        dict (role, name, color, state, steps, ask, busy, pet). `handlers`:
        face(cr, role, pet, size, moving), pick(role, busy), decide(allow)."""
        sig = repr((cards, free))
        if sig == self.signature:
            return
        self.signature = sig
        self.faces = []
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        if cards:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[2], homogeneous=True)
            for card in cards:
                row.append(self._card(card, handlers))
            self.page.append(row)
        if free:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1], homogeneous=True)
            for card in free:
                row.append(self._card(card, handlers, small=True))
            self.page.append(row)

    def _card(self, card, handlers, small=False):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
        box.add_css_class('elyares-card')
        size = 36 if small else 56
        face = Gtk.DrawingArea()
        face.set_content_width(size)
        face.set_content_height(size)
        face.set_halign(Gtk.Align.START)
        face.set_valign(Gtk.Align.CENTER)
        moving = card['busy']
        face.set_draw_func(lambda _da, cr, w, h, c=card: handlers['face'](cr, c['role'], c['pet'], w, h, moving))
        if moving:
            self.faces.append(face)
        box.append(face)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        name = Gtk.Label(xalign=0)
        name.set_markup(f'<span foreground="{card["color"]}" weight="bold">{GLib.markup_escape_text(card["name"])}</span>')
        name.set_ellipsize(Pango.EllipsizeMode.END)
        state = Gtk.Label(label=card['state'], xalign=0)
        state.add_css_class('dim-label')
        text.append(name)
        text.append(state)
        for line in card['steps'][-2:]:
            step = Gtk.Label(label=line, xalign=0, wrap=True)
            step.set_lines(3)
            step.set_ellipsize(Pango.EllipsizeMode.END)
            text.append(step)
        box.append(text)
        if card['ask']:
            buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            allow = Gtk.Button(label='Permitir')
            allow.add_css_class('elyares-btn')
            allow.add_css_class('primary')
            allow.connect('clicked', lambda _b: handlers['decide'](True))
            deny = Gtk.Button(label='Denegar')
            deny.add_css_class('elyares-btn')
            deny.add_css_class('danger')
            deny.connect('clicked', lambda _b: handlers['decide'](False))
            buttons.append(allow)
            buttons.append(deny)
            text.append(buttons)
        click = Gtk.GestureClick()
        click.connect('released', lambda *_a: handlers['pick'](card['role'], card['busy']))
        box.add_controller(click)
        return box


class ChatHead(Gtk.Box):
    """La cabecera del chat en widgets: la cara del agente, «agente | proyecto»,
    su estado y su carpeta, y a la derecha Otra, Nuevo, Detener y Cerrar. El
    resto del chat (la conversación y la caja) sigue debajo, en Cairo."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[2])
        self.add_css_class('elyares-chathead')
        self.set_valign(Gtk.Align.START)
        self.set_halign(Gtk.Align.FILL)
        self.signature = None
        self.set_visible(False)

    def place(self, height):
        self.set_visible(height > 0)
        if height > 0:
            self.set_size_request(-1, int(height))

    def set_info(self, info, handlers):
        """`info`: role, pet, name, color, project, status, where, busy,
        can_split. `handlers`: face(cr, role, pet, w, h, moving), act(key)."""
        sig = repr(info)
        if sig == self.signature:
            return
        self.signature = sig
        while (child := self.get_first_child()) is not None:
            self.remove(child)
        face = Gtk.DrawingArea()
        face.set_content_width(40)
        face.set_content_height(40)
        face.set_draw_func(lambda _da, cr, w, h: handlers['face'](cr, info['role'], info['pet'], w, h, info['busy']))
        self.append(face)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title = Gtk.Label(xalign=0)
        title.set_markup(f'<span foreground="{info["color"]}" weight="bold">{GLib.markup_escape_text(info["name"])}</span>'
                         f' | {GLib.markup_escape_text(info["project"])}')
        title.set_ellipsize(Pango.EllipsizeMode.END)
        where = f' · {info["where"]}' if info['where'] else ''
        status = Gtk.Label(label=info['status'] + where, xalign=0)
        status.add_css_class('dim-label')
        status.set_ellipsize(Pango.EllipsizeMode.END)
        text.append(title)
        text.append(status)
        text.set_hexpand(True)
        self.append(text)
        links = [('split', 'Otra')] if info['can_split'] else []
        links += [('new', 'Nuevo')] + ([('stop', 'Detener')] if info['busy'] else []) + [('close', 'Cerrar')]
        for key, label in links:
            btn = Gtk.Button(label=label)
            btn.add_css_class('elyares-btn')
            if key == 'stop':
                btn.add_css_class('danger')
            btn.connect('clicked', lambda _b, k=key: handlers['act'](k))
            self.append(btn)
