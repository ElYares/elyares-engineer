"""El marco de widgets de la ventana de la app (decisión 009 del vault).

La ventana lleva widgets GTK4 en lo que es control —barra de título, vistas,
barra lateral— y deja en Cairo lo que es dibujo: el `overlay` de la isla va
dentro, como un contenido más, hasta que cada vista se migre. Este módulo solo
arma los widgets; qué hace cada botón lo decide quien lo crea con `on_view`.
"""

from gi.repository import Gdk, GLib, Gtk, Pango

# (clave, texto) en el orden de la barra de título.
VIEWS = (('board', 'Tablero'), ('chat', 'Chat'), ('flows', 'Flujos'),
         ('projects', 'Proyectos'), ('sources', 'Fuentes'), ('settings', 'Ajustes'))
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
.elyares-slot {{ background: rgba(5, 6, 8, 0.98); }}
.elyares-slot.glass, .elyares-side.glass, .elyares-bar.glass {{ background: rgba(5, 6, 8, 0.5); }}
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
.elyares-btn.compact {{ padding: {SPACE[0]}px {SPACE[1]}px; min-height: 0; }}
.elyares-btn.primary {{ background: {ACCENT}; color: {SURFACE[0]}; }}
.elyares-btn.danger {{ background: {DANGER}; color: {SURFACE[0]}; }}
.elyares-sources, .elyares-sources viewport {{ background: {SURFACE[0]}; color: {INK}; }}
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
        nav.set_spacing(SPACE[1])
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
        self.none = Gtk.ToggleButton()      # nadie del grupo marcado: la bandeja no es una de las vistas
        self.none.set_group(first)
        self.header.set_title_widget(nav)
        # La campana abre la bandeja y «?» la ayuda; van fuera del grupo de vistas.
        self.bell = Gtk.ToggleButton(label='Alertas')
        self.bell.update_property([Gtk.AccessibleProperty.LABEL], ['Alertas'])
        self.bell.connect('toggled', self._toggled, 'alerts')
        self.buttons['alerts'] = self.bell
        self.help = Gtk.Button(label='?')
        self.help.update_property([Gtk.AccessibleProperty.LABEL], ['Ayuda: atajos y comandos'])
        self.help.set_margin_start(SPACE[1])
        self.header.pack_end(self.help)
        self.header.pack_end(self.bell)
        self.board = BoardPanel()
        self.chat_head = ChatHead()
        self.focus = FocusPanel()
        self.sources = SourcesPanel()
        self.alerts = AlertsPanel()
        self.settings = SettingsPanel()
        self.sidebar = Gtk.ListBox()
        self.sidebar.set_size_request(SIDEBAR_W, -1)
        self.sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar.add_css_class('elyares-side')
        self.sidebar.connect('row-activated', self._picked)
        self.slot = Gtk.Box()           # donde va el contenido
        self.slot.add_css_class('elyares-slot')
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
            for set_expand in (child.set_hexpand, child.set_vexpand):
                set_expand(True)            # un Box solo da lo natural: sin esto quedan franjas grises
            child.set_halign(Gtk.Align.FILL)
            child.set_valign(Gtk.Align.FILL)
            self.slot.append(child)

    def sync(self, view):
        """Marca la vista que está a la vista, sin disparar `on_view`."""
        self.syncing = True
        try:
            bell = view == 'alerts'
            if self.bell.get_active() != bell:
                self.bell.set_active(bell)
            btn = self.none if bell else self.buttons.get(view)
            if btn is not None and not btn.get_active():
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

    def hide_panels(self):
        """Los paneles que van encima del dibujo solo valen en la ventana: al
        volver la isla suelta se esconden, o se verían sobre ella."""
        self.board.place(0)
        self.focus.place(0)
        self.chat_head.place(0)
        for panel in (self.sources, self.alerts, self.settings):
            panel.set_visible(False)

    def set_glass(self, on):
        """Con vidrio, el fondo del marco es translúcido; sin él, opaco."""
        for widget in (self.slot, self.sidebar, self.header):
            (widget.add_css_class if on else widget.remove_css_class)('glass')

    def set_bell(self, count):
        self.bell.set_label(f'Alertas · {count}' if count else 'Alertas')

    def fold(self, width):
        """Plegada, la barra lateral no achica el contenido: con la ventana
        angosta (hasta 480) el dibujo conserva todo su ancho."""
        self.sidebar.set_visible(not width or width >= FOLD_W)

    def chrome_h(self):
        """Lo que la barra de título le quita al alto de la ventana."""
        return self.header.get_height()

    def _toggled(self, btn, key):
        if self.syncing:
            return
        if btn.get_active():
            self.on_view(key)
        elif key == 'alerts':
            self.on_view('board')           # la campana otra vez la cierra


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
        for group, small in ((cards, False), (free, True)):
            if not group:
                continue
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_homogeneous(True)
            flow.set_min_children_per_line(1)
            flow.set_max_children_per_line(4)
            flow.set_column_spacing(SPACE[1])
            flow.set_row_spacing(SPACE[1])
            flow.set_activate_on_single_click(False)
            for card in group:
                flow.append(self._card(card, handlers, small=small))
            self.page.append(flow)

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
            btn.add_css_class('compact')
            if key == 'stop':
                btn.add_css_class('danger')
            btn.connect('clicked', lambda _b, k=key: handlers['act'](k))
            self.append(btn)


class SourcesPanel(Gtk.Box):
    """La vista *Fuentes*: a la izquierda una fila por fuente, con su punto y
    su estado en texto; a la derecha el detalle de la elegida, su interruptor
    y sus comandos. Sin estado propio: la llena la isla con `set_data`."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[2])
        self.add_css_class('elyares-sources')
        self.set_valign(Gtk.Align.FILL)
        self.set_halign(Gtk.Align.FILL)
        self.signature = None
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.set_size_request(220, -1)
        self.list.add_css_class('elyares-side')
        self.list.connect('row-activated', self._picked)
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.detail, f'set_margin_{side}')(SPACE[2])
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_hexpand(True)
        scroll.set_child(self.detail)
        self.append(self.list)
        self.append(scroll)
        self.handlers = {}
        self.set_visible(False)

    def set_data(self, rows, chosen, detail, handlers):
        """`rows`: [(key, nombre, color o None, estado en texto)]; `detail`:
        dict (title, status, about, lines, why, fix, toggle, on, cmds).
        `handlers`: pick(key), toggle(key)."""
        sig = repr((rows, chosen, detail))
        if sig == self.signature:
            return
        self.signature = sig
        self.handlers = handlers
        while (row := self.list.get_first_child()) is not None:
            self.list.remove(row)
        picked = None
        for key, name, color, text in rows:
            row = Gtk.ListBoxRow()
            row.key = key
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            dot = Gtk.Label()
            dot.set_markup(f'<span foreground="{color or MUTED}">{"●" if color else "○"}</span>')
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            col.append(Gtk.Label(label=name, xalign=0))
            sub = Gtk.Label(label=text, xalign=0)
            sub.add_css_class('dim-label')
            sub.set_ellipsize(Pango.EllipsizeMode.END)
            col.append(sub)
            box.append(dot)
            box.append(col)
            row.set_child(box)
            row.update_property([Gtk.AccessibleProperty.LABEL], [f'{name}, {text}'])
            self.list.append(row)
            if key == chosen:
                picked = row
        if picked is not None:
            self.list.select_row(picked)
        self._fill_detail(detail)

    def _fill_detail(self, d):
        while (child := self.detail.get_first_child()) is not None:
            self.detail.remove(child)
        title = Gtk.Label(xalign=0)
        title.set_markup(f'<span size="x-large" weight="bold">{GLib.markup_escape_text(d["title"])}</span>')
        self.detail.append(title)
        status = Gtk.Label(label=d['status'], xalign=0)
        self.detail.append(status)
        about = Gtk.Label(label=d['about'], xalign=0, wrap=True)
        about.add_css_class('dim-label')
        self.detail.append(about)
        for line in d['lines']:
            self.detail.append(Gtk.Label(label=line, xalign=0, wrap=True))
        for text in (d['why'], d['fix']):
            if text:
                self.detail.append(Gtk.Label(label=text, xalign=0, wrap=True))
        if d.get('retry'):
            btn = Gtk.Button(label='Reintentar')
            btn.add_css_class('elyares-btn')
            btn.set_halign(Gtk.Align.START)
            btn.connect('clicked', lambda _b, k=d['key']: self.handlers['retry'](k))
            self.detail.append(btn)
        for item in d.get('items', ()):
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            card.add_css_class('elyares-card')
            text = Gtk.Label(label=f'{item["label"]} · {item["note"]}', xalign=0, wrap=True)
            text.set_hexpand(True)
            card.append(text)
            btn = Gtk.Button(label='Abrir PR')
            btn.add_css_class('elyares-btn')
            btn.connect('clicked', lambda _b, u=item['url']: self.handlers['open'](u))
            card.append(btn)
            self.detail.append(card)
        if d['toggle']:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            label = Gtk.Label(label='Prendida', xalign=0)
            label.set_hexpand(True)
            switch = Gtk.Switch()
            switch.set_active(d['on'])
            switch.set_valign(Gtk.Align.CENTER)
            switch.update_property([Gtk.AccessibleProperty.LABEL], [f'Prendida: {d["title"]}'])
            key = d['key']
            switch.connect('notify::active', lambda sw, _p: sw.get_active() != d['on']
                           and self.handlers['toggle'](key))
            row.append(label)
            row.append(switch)
            self.detail.append(row)
        if d['cmds']:
            head = Gtk.Label(xalign=0)
            head.set_markup('<b>Comandos</b>')
            self.detail.append(head)
            grid = Gtk.Grid(column_spacing=SPACE[2], row_spacing=SPACE[0])
            for i, (cmd, text) in enumerate(d['cmds']):
                grid.attach(Gtk.Label(label=cmd, xalign=0, selectable=True), 0, i, 1, 1)
                what = Gtk.Label(label=text, xalign=0, wrap=True)
                what.add_css_class('dim-label')
                grid.attach(what, 1, i, 1, 1)
            self.detail.append(grid)

    def _picked(self, _box, row):
        self.handlers['pick'](row.key)


class AlertsPanel(Gtk.ScrolledWindow):
    """La bandeja: las alertas activas, cada una con su punto, su título, su
    detalle y sus botones. Es otra vista de lo mismo que la isla muestra en su
    ficha, no otra fuente. Sin estado propio: la llena la isla."""

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

    def set_alerts(self, alerts, handlers):
        """`alerts`: [dict(sid, title, color, lines, where, note, buttons)] con
        `buttons` = [(clave, texto)]. `handlers`: act(sid, clave)."""
        sig = repr(alerts)
        if sig == self.signature:
            return
        self.signature = sig
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        if not alerts:
            empty = Gtk.Label(label='Sin alertas. Todo en orden.', xalign=0)
            empty.add_css_class('dim-label')
            self.page.append(empty)
        for a in alerts:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
            card.add_css_class('elyares-card')
            title = Gtk.Label(xalign=0)
            title.set_markup(f'<span foreground="{a["color"]}">●</span> '
                             f'<b>{GLib.markup_escape_text(a["title"])}</b>')
            card.append(title)
            for line in a['lines']:
                card.append(Gtk.Label(label=line, xalign=0, wrap=True))
            where = ' · '.join(x for x in (a['where'], a['note']) if x)
            if where:
                dim = Gtk.Label(label=where, xalign=0)
                dim.add_css_class('dim-label')
                card.append(dim)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            for key, label in a['buttons']:
                btn = Gtk.Button(label=label)
                btn.add_css_class('elyares-btn')
                btn.connect('clicked', lambda _b, sid=a['sid'], k=key: handlers['act'](sid, k))
                row.append(btn)
            card.append(row)
            self.page.append(card)


class SettingsPanel(Gtk.ScrolledWindow):
    """Ajustes: un interruptor por cada clave que hoy se cambia con una orden
    o un clic. Cada fila es (clave, texto, activo, nota)."""

    def __init__(self):
        super().__init__()
        self.add_css_class('elyares-sources')
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.page, f'set_margin_{side}')(SPACE[2])
        self.set_child(self.page)
        self.signature = None
        self.position = None
        self.set_visible(False)

    def set_rows(self, rows, position, handlers):
        """`rows`: [(clave, texto, activo, nota)]; `position`: 0..100 o None.
        `handlers`: toggle(clave), move(valor), theme()."""
        sig = repr((rows, position))
        if sig == self.signature:
            return
        self.signature = sig
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        for key, text, on, note in rows:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            col.set_hexpand(True)
            col.append(Gtk.Label(label=text, xalign=0))
            if note:
                dim = Gtk.Label(label=note, xalign=0, wrap=True)
                dim.add_css_class('dim-label')
                col.append(dim)
            switch = Gtk.Switch()
            switch.set_active(on)
            switch.set_valign(Gtk.Align.CENTER)
            switch.update_property([Gtk.AccessibleProperty.LABEL], [text])
            switch.connect('notify::active', lambda sw, _p, k=key, was=on: sw.get_active() != was
                           and handlers['toggle'](k))
            row.append(col)
            row.append(switch)
            self.page.append(row)
        if position is not None:
            self.page.append(Gtk.Label(label='Posición de la isla', xalign=0))
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
            scale.set_value(position)
            scale.update_property([Gtk.AccessibleProperty.LABEL], ['Posición de la isla, de 0 a 100'])
            scale.connect('value-changed', lambda sc: sc.get_value() != position and handlers['move'](sc.get_value()))
            self.page.append(scale)
        theme = Gtk.Button(label='Releer el color de acento del tema')
        theme.add_css_class('elyares-btn')
        theme.set_halign(Gtk.Align.START)
        theme.connect('clicked', lambda _b: handlers['theme']())
        self.page.append(theme)


class HelpDialog(Gtk.Window):
    """La ayuda: buscador, atajos del teclado, del ratón y comandos. Solo se
    consulta; nada de aquí se ejecuta. El foco queda dentro, Esc la cierra y
    devuelve el foco al icono."""

    def __init__(self, parent, opener):
        super().__init__(title='Ayuda de elyares-engineer', transient_for=parent, modal=True)
        self.opener = opener
        self.returned = False
        self.items = []                 # [(bloque, atajo o comando, qué hace)]
        self.set_default_size(520, 480)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(SPACE[2])
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('Buscar un atajo o un comando')
        self.search.connect('search-changed', lambda _e: self._filter())
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list.set_filter_func(self._visible)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.list)
        box.append(self.search)
        box.append(scroll)
        self.set_child(box)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._key)
        self.add_controller(keys)
        self.connect('close-request', self._closing)

    def set_items(self, items):
        self.items = list(items)
        while (row := self.list.get_first_child()) is not None:
            self.list.remove(row)
        for block, what, text in self.items:
            row = Gtk.ListBoxRow()
            row.haystack = f'{block} {what} {text}'.lower()
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[2])
            cmd = Gtk.Label(label=what, xalign=0, selectable=True)
            cmd.set_size_request(200, -1)
            hint = Gtk.Label(label=text, xalign=0, wrap=True)
            hint.add_css_class('dim-label')
            line.append(cmd)
            line.append(hint)
            row.set_child(line)
            self.list.append(row)

    def shown(self):
        """Los textos que pasan el buscador, en orden."""
        rows, row = [], self.list.get_first_child()
        while row is not None:
            if self._visible(row):
                rows.append(row.haystack)
            row = row.get_next_sibling()
        return rows

    def _visible(self, row):
        return self.search.get_text().strip().lower() in row.haystack

    def _filter(self):
        self.list.invalidate_filter()

    def _key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self._closing(self)
            self.close()
            return True
        return False

    def _closing(self, _win):
        """Devuelve el foco al icono que la abrió, una sola vez por cierre."""
        if self.opener is not None and not self.returned:
            self.returned = True
            self.opener.grab_focus()
        return False


class FocusPanel(Gtk.ScrolledWindow):
    """El desglose de un agente en la ventana: a la izquierda quién es, cuánto
    lleva y sus enlaces; en medio todos sus pasos; abajo, los demás en
    miniatura. Sin estado propio: lo llena la isla con `set_focus`."""

    def __init__(self):
        super().__init__()
        self.add_css_class('elyares-board')
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_valign(Gtk.Align.START)
        self.set_halign(Gtk.Align.FILL)
        self.signature = None
        self.faces = []
        self.set_visible(False)

    place = BoardPanel.place
    animate = BoardPanel.animate

    def set_focus(self, d, handlers):
        """`d`: role, name, color, pet, busy, label, summary, steps
        [(marca, color, texto, tiempo)], links [(tipo, clave, texto)], others
        [(rol, pet, activo)], hidden, empty. `handlers`: face, link, other."""
        sig = repr(d)
        if sig == self.signature:
            return
        self.signature = sig
        self.faces = []
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[3])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(root, f'set_margin_{side}')(SPACE[2])
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        left.set_size_request(170, -1)
        face = Gtk.DrawingArea()
        face.set_content_width(84)
        face.set_content_height(84)
        face.set_halign(Gtk.Align.CENTER)
        face.set_draw_func(lambda _da, cr, w, h: handlers['face'](cr, d['role'], d['pet'], w, h, d['busy']))
        if d['busy']:
            self.faces.append(face)
        left.append(face)
        name = Gtk.Label()
        name.set_markup(f'<span foreground="{d["color"]}" weight="bold">{GLib.markup_escape_text(d["name"])}</span>')
        left.append(name)
        for text in (d['label'], d['summary']):
            lab = Gtk.Label(label=text)
            lab.add_css_class('dim-label')
            lab.set_ellipsize(Pango.EllipsizeMode.END)
            left.append(lab)
        for kind, key, text in d['links']:
            btn = Gtk.Button(label=text)
            btn.add_css_class('elyares-btn')
            btn.connect('clicked', lambda _b, k=kind, v=key: handlers['link'](k, v))
            left.append(btn)
        root.append(left)
        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        mid.set_hexpand(True)
        if d['empty']:
            mid.append(Gtk.Label(label=d['empty'], xalign=0, wrap=True))
        if d['hidden']:
            more = Gtk.Label(label=f'⋯ {d["hidden"]} paso{"" if d["hidden"] == 1 else "s"} antes', xalign=0)
            more.add_css_class('dim-label')
            mid.append(more)
        for mark, color, text, spent in d['steps']:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            row.add_css_class('elyares-card')
            m = Gtk.Label()
            m.set_markup(f'<span foreground="{color}">{GLib.markup_escape_text(mark)}</span>')
            t = Gtk.Label(label=text, xalign=0)
            t.set_hexpand(True)
            t.set_ellipsize(Pango.EllipsizeMode.END)
            when = Gtk.Label(label=spent)
            when.add_css_class('dim-label')
            row.append(m)
            row.append(t)
            row.append(when)
            mid.append(row)
        others = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
        for role, pet, busy in d['others']:
            btn = Gtk.Button()
            btn.add_css_class('flat')
            btn.update_property([Gtk.AccessibleProperty.LABEL], [role])
            btn.set_tooltip_text(role)
            da = Gtk.DrawingArea()
            da.set_content_width(32)
            da.set_content_height(32)
            da.set_draw_func(lambda _da, cr, w, h, r=role, p=pet, b=busy: handlers['face'](cr, r, p, w, h, False))
            btn.set_child(da)
            btn.connect('clicked', lambda _b, r=role, b=busy: handlers['other'](r, b))
            others.append(btn)
        mid.append(others)
        root.append(mid)
        self.set_child(root)
