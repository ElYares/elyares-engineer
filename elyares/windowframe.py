"""El marco de widgets de la ventana de la app (decisión 009 del vault).

La ventana lleva widgets GTK4 en lo que es control —barra de título, vistas,
barra lateral— y deja en Cairo lo que es dibujo: el `overlay` de la isla va
dentro, como un contenido más, hasta que cada vista se migre. Este módulo solo
arma los widgets; qué hace cada botón lo decide quien lo crea con `on_view`.
"""

from gi.repository import Gdk, GLib, Gtk, Pango

from . import fonts, mascot, themes

# (clave, texto) en el orden de la barra de título.
VIEWS = (('board', 'Tablero'), ('chat', 'Chat'), ('flows', 'Flujos'),
         ('projects', 'Proyectos'), ('tmux', 'Sesiones'), ('pomodoro', 'Pomodoro'),
         ('editor', 'Editor'), ('terminal', 'Terminal'), ('taller', 'Taller'),
         ('sources', 'Fuentes'), ('settings', 'Ajustes'))
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
GLASS = ('5, 6, 8', '16, 19, 26', '26, 31, 43')     # lo mismo en rgb, para el vidrio
ACCENT_RGB = '110, 168, 255'
GLOW = '255, 255, 255'                          # velos y filos: blanco en oscuro, negro en claro


def _role_rows():
    """El agente elegido en la barra lateral, con el fondo de su color."""
    rows = []
    for role in mascot.ROLES:
        r, g, b = (round(c * 255) for c in mascot.rgba(mascot.accent(role))[:3])
        rows.append(f'.elyares-side row.role-{role}:selected {{ background: rgba({r}, {g}, {b}, 0.28); }}')
    return '\n'.join(rows) + '\n'


ROLE_ROWS = _role_rows()

def tech_css():
    """El estilo técnico: todo recto, sin sombras y con el filo a 1 px bien marcado."""
    return f"""
.elyares-segments, .elyares-segments button, .elyares-pill, .elyares-side row, .elyares-card,
.elyares-btn, entry, textview, dropdown, button, popover, popover contents, scrollbar slider, switch, switch slider
  {{ border-radius: 0; box-shadow: none; }}
.elyares-segments, .elyares-card, .elyares-btn, .elyares-pill, .elyares-chathead
  {{ border: 1px solid rgba({GLOW}, 0.22); }}
.elyares-segments button:checked, .elyares-pill:checked, .elyares-side row:selected
  {{ border-left: 2px solid {ACCENT}; }}
"""


def season_css():
    """El adorno de temporada de la ventana: con Navidad, una guirnalda roja, verde y dorada bajo la barra."""
    if themes.current != 'navidad':
        return ''
    return """
.elyares-bar { border-bottom: 3px solid transparent;
  border-image: repeating-linear-gradient(90deg, #d63a3a 0 14px, #2f9e5b 14px 28px, #f5c542 28px 42px) 0 0 3 0 / 0 0 3px 0 stretch; }
.elyares-sidebox { border-right: 2px solid #2f9e5b; }
.elyares-btn.primary { background: #d63a3a; color: #ffffff; }
"""


def build_css():
    return f"""
.elyares-slot {{ background: rgba({GLASS[0]}, 0.98); }}
.elyares-slot.glass, .elyares-side.glass, .elyares-bar.glass, .elyares-sidebox.glass {{ background: rgba({GLASS[0]}, {fonts.glass(.5)}); }}
/* Con vidrio, también las tarjetas, pastillas y fuentes dejan pasar el fondo. */
.glass .elyares-card, .glass .elyares-segments, .glass .elyares-pill {{ background: rgba({GLASS[1]}, {fonts.glass(.45)}); }}
.glass .elyares-card:hover, .glass .elyares-card.raised, .glass .elyares-pill:hover, .glass .elyares-pill:checked,
.glass .elyares-segments button:checked {{ background: rgba({GLASS[2]}, {fonts.glass(.6)}); }}
.glass .elyares-sources, .glass .elyares-sources viewport, .glass .elyares-chathead {{ background: transparent; }}
.elyares-bar {{ background: {SURFACE[0]}; color: {INK}; border: none; box-shadow: none;
  border-bottom: 1px solid rgba({GLOW}, 0.06); }}
/* Las vistas, como el control segmentado de macOS: una pastilla con la activa elevada. */
.elyares-segments {{ background: {SURFACE[1]}; border-radius: {RADIUS[0]}px; padding: 2px;
  border: 1px solid rgba({GLOW}, 0.06); }}
.elyares-segments button {{ background: transparent; color: {MUTED}; border: none; box-shadow: none;
  padding: {SPACE[0]}px {SPACE[2]}px; border-radius: 6px; min-height: 24px; min-width: 24px; }}
.elyares-segments button:hover {{ background: rgba({GLOW}, 0.05); }}
.elyares-segments button:checked {{ background: {SURFACE[2]}; color: {INK};
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.5); }}
.elyares-pill {{ background: {SURFACE[1]}; color: {MUTED}; border: none;
  box-shadow: none; padding: {SPACE[0]}px {SPACE[2]}px; border-radius: {RADIUS[0]}px; min-height: 24px; min-width: 24px; }}
.elyares-pill:checked {{ background: {SURFACE[2]}; color: {INK}; }}
.elyares-pill:hover {{ background: {SURFACE[2]}; }}
/* La barra lateral: sección en versalitas y la fila elegida con el acento, como en macOS. */
.elyares-sidebox {{ background: {SURFACE[0]}; border-right: 1px solid rgba({GLOW}, 0.06); }}
.elyares-section {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px;
  padding: {SPACE[2]}px {SPACE[2]}px {SPACE[0]}px; }}
.elyares-side {{ background: transparent; color: {INK}; padding: {SPACE[0]}px {SPACE[1]}px; }}
.elyares-side row {{ border-radius: {RADIUS[0]}px; padding: {SPACE[1]}px {SPACE[1]}px; margin: 1px 0; }}
.elyares-side row:hover {{ background: rgba({GLOW}, 0.05); }}
.elyares-side row:selected {{ background: rgba({ACCENT_RGB}, 0.22); color: {INK}; }}
{ROLE_ROWS}.elyares-card {{ background: {SURFACE[1]}; color: {INK}; border-radius: {RADIUS[1]}px;
  padding: {SPACE[1]}px {SPACE[2]}px; border: 1px solid rgba({GLOW}, 0.06); }}
.elyares-card:hover {{ background: {SURFACE[2]}; }}
.elyares-card.raised {{ background: {SURFACE[2]}; }}
.elyares-btn {{ background: {SURFACE[2]}; color: {INK}; border-radius: 6px;
  padding: {SPACE[1]}px {SPACE[3]}px; border: 1px solid rgba({GLOW}, 0.08); box-shadow: none; }}
.elyares-btn:disabled {{ opacity: 0.4; }}
.elyares-btn:hover {{ background: rgba({GLOW}, 0.14); }}
.elyares-btn.compact {{ padding: {SPACE[0]}px {SPACE[1]}px; min-height: 24px; min-width: 24px; }}
.elyares-btn.primary {{ background: {ACCENT}; color: {SURFACE[0]}; border: none; }}
.elyares-btn.danger {{ background: {DANGER}; color: {SURFACE[0]}; border: none; }}
.elyares-sources, .elyares-sources viewport {{ background: {SURFACE[0]}; color: {INK}; }}
.elyares-chathead {{ background: {SURFACE[0]}; color: {INK}; padding: {SPACE[1]}px {SPACE[2]}px;
  border-bottom: 1px solid rgba({GLOW}, 0.06); }}
.elyares-segments button:focus-visible, .elyares-side row:focus-visible, .elyares-btn:focus-visible,
.elyares-pill:focus-visible, .elyares-card:focus-visible, entry:focus-within, textview:focus-within,
dropdown:focus-within, switch:focus-visible, checkbutton:focus-visible, button:focus-visible {{
  outline: 2px solid {ACCENT}; outline-offset: 2px; }}
{tech_css() if mascot.SQUARE else ''}{season_css()}"""

CSS = build_css()
_provider = None


def use_theme():
    """Toma los colores del tema de ahora; con los estilos ya puestos, los rehace en caliente."""
    global SURFACE, INK, MUTED, ACCENT, DANGER, GLASS, ACCENT_RGB, GLOW, CSS
    look = themes.get()
    SURFACE, INK, MUTED = look['surface'], look['ink'], look['muted']
    ACCENT, DANGER = look['accent'], look['danger']
    GLASS = tuple(', '.join(str(c) for c in themes.rgb255(color)) for color in SURFACE)
    ACCENT_RGB = ', '.join(str(c) for c in themes.rgb255(ACCENT))
    GLOW = '0, 0, 0' if themes.is_light() else '255, 255, 255'
    CSS = build_css()
    if _provider is not None:
        _provider.load_from_string(CSS)


def load_css():
    """Instala los estilos una sola vez para toda la app."""
    global _provider
    if _provider is None:
        _provider = Gtk.CssProvider()
        _provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        load_fonts()


class Lights(Gtk.DrawingArea):
    """Las luces de Navidad: una tira de focos de colores por el borde del contenido, que parpadean.

    Solo se ven con el tema `navidad`; el resto del tiempo está escondida y no repinta.
    """
    COLORS = ((.91, .23, .23), (.18, .72, .42), (.96, .77, .26), (.30, .60, 1.0))
    STEP = 30           # px entre foco y foco
    INSET = 6           # lo que la tira se separa del borde
    BULB = 4            # radio del foco
    BLINK_MS = 450

    def __init__(self):
        super().__init__()
        self.set_can_target(False)          # los clics pasan de largo
        self.set_can_focus(False)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self.paint)
        self.phase = 0
        self.timer = 0
        self.set_visible(False)
        # El reloj corre aunque esté escondida (un widget escondido nunca se «mapea»): es lo que la muestra.
        self.timer = GLib.timeout_add(self.BLINK_MS, self.tick)

    def tick(self):
        on = themes.current == 'navidad'
        if on != self.get_visible():
            self.set_visible(on)
        if on:
            self.phase += 1
            self.queue_draw()
        return True

    @classmethod
    def points(cls, w, h):
        """Dónde van los focos: por todo el borde, empezando arriba a la izquierda y en sentido horario."""
        a, b = cls.INSET, cls.INSET
        right, bottom = w - cls.INSET, h - cls.INSET
        out = []
        for x in range(a, int(right), cls.STEP):
            out.append((x, b))
        for y in range(b, int(bottom), cls.STEP):
            out.append((right, y))
        for x in range(int(right), a, -cls.STEP):
            out.append((x, bottom))
        for y in range(int(bottom), b, -cls.STEP):
            out.append((a, y))
        return out

    def paint(self, _area, cr, w, h):
        if w < 4 * self.STEP or h < 4 * self.STEP:
            return
        i = self.INSET
        cr.set_source_rgba(.05, .25, .12, .75)          # el cable
        cr.set_line_width(1.5)
        cr.rectangle(i, i, w - 2 * i, h - 2 * i)
        cr.stroke()
        for n, (x, y) in enumerate(self.points(w, h)):
            r, g, b = self.COLORS[n % len(self.COLORS)]
            lit = (n + self.phase) % 3 != 0             # un foco de cada tres está apagado, y va corriendo
            if lit:
                cr.set_source_rgba(r, g, b, .22)
                cr.arc(x, y, self.BULB * 2.6, 0, 6.2832)
                cr.fill()
            cr.set_source_rgba(r, g, b, 1 if lit else .35)
            cr.arc(x, y, self.BULB, 0, 6.2832)
            cr.fill()


class Frame:
    """Barra de título con las vistas, barra lateral y el hueco del contenido."""

    def __init__(self, on_view, on_session=None):
        self.on_view = on_view
        self.on_session = on_session or (lambda sid: None)
        self.session_shape = None       # qué filas hay: sin cambios no se reconstruye, solo se retocan los textos
        self.session_chosen = None
        self.session_refs = {}
        self.syncing = False            # sincronizar los botones no es un clic de Yared
        self.buttons = {}
        load_css()
        self.header = Gtk.HeaderBar()
        self.header.add_css_class('elyares-bar')
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        nav.set_spacing(2)
        nav.add_css_class('elyares-segments')
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
        self.bell.add_css_class('elyares-pill')
        self.bell.update_property([Gtk.AccessibleProperty.LABEL], ['Alertas'])
        self.bell.connect('toggled', self._toggled, 'alerts')
        self.buttons['alerts'] = self.bell
        self.help = Gtk.Button(label='?')
        self.help.add_css_class('elyares-pill')
        self.help.update_property([Gtk.AccessibleProperty.LABEL], ['Ayuda: atajos y comandos'])
        self.help.set_margin_start(SPACE[1])
        self.header.pack_end(self.help)
        self.header.pack_end(self.bell)
        self.board = BoardPanel()
        self.chat_head = ChatHead()
        self.focus = FocusPanel()
        self.flows = FlowsPanel()
        self.sources = SourcesPanel()
        self.alerts = AlertsPanel()
        self.tmux = TmuxPanel()
        self.pomodoro = PomodoroPanel()
        self.extra = []                 # paneles que monta la ventana (el editor y la terminal importan de este módulo)
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
        self.section = Gtk.Label(label='SESIONES', xalign=0)
        self.section.add_css_class('elyares-section')
        self.side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.side_box.add_css_class('elyares-sidebox')
        self.side_box.append(self.section)
        self.side_box.append(self.sidebar)
        self.body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.body.append(self.side_box)
        self.body.append(self.slot)

    def attach(self, win):
        win.set_titlebar(self.header)
        dressed = Gtk.Overlay()         # encima del contenido, las luces de temporada
        dressed.set_child(self.body)
        self.lights = Lights()
        dressed.add_overlay(self.lights)
        win.set_child(dressed)

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
        self.section.set_label('AGENTES' if face is not None else 'SESIONES')
        shape = tuple((r[0], len(r) > 4) for r in rows)
        if shape == self.session_shape:
            self._refresh_sessions(rows, chosen)        # las mismas filas: solo cambian los textos
            return
        self.session_shape, self.session_chosen = shape, chosen
        self.session_refs = {}
        while (row := self.sidebar.get_first_child()) is not None:
            self.sidebar.remove(row)
        picked = None
        for sid, name, color, text, *role in rows:
            row = Gtk.ListBoxRow()
            row.sid = sid
            if role:
                row.add_css_class(f'role-{role[0]}')
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
            self.session_refs[sid] = dict(row=row, dot=dot if not role or face is None else None,
                                          title=title, sub=sub, last=(name, color, text))
            self.sidebar.append(row)
            if sid == chosen:
                picked = row
        if picked is not None:
            self.sidebar.select_row(picked)     # no emite `row-activated`: no es un clic

    def _refresh_sessions(self, rows, chosen):
        for sid, name, color, text, *_role in rows:
            ref = self.session_refs.get(sid)
            if ref is None or ref['last'] == (name, color, text):
                continue
            ref['last'] = (name, color, text)
            ref['title'].set_label(name)
            ref['sub'].set_label(text)
            if ref['dot'] is not None:
                ref['dot'].set_markup(f'<span foreground="{color or MUTED}">{"●" if color else "○"}</span>')
            ref['row'].update_property([Gtk.AccessibleProperty.LABEL], [f'{name}, {text}'])
        if chosen != self.session_chosen:
            self.session_chosen = chosen
            row = (self.session_refs.get(chosen) or {}).get('row')
            if row is not None:
                self.sidebar.select_row(row)

    def _picked(self, _box, row):
        self.on_session(row.sid)

    def hide_panels(self):
        """Los paneles que van encima del dibujo solo valen en la ventana: al
        volver la isla suelta se esconden, o se verían sobre ella."""
        self.board.place(0)
        self.focus.place(0)
        self.flows.set_visible(False)
        self.chat_head.place(0)
        for panel in (self.sources, self.alerts, self.settings, self.tmux, self.pomodoro, *self.extra):
            panel.set_visible(False)

    def set_glass(self, on):
        """Con vidrio, el fondo del marco es translúcido; sin él, opaco."""
        for widget in (self.slot, self.side_box, self.header):
            (widget.add_css_class if on else widget.remove_css_class)('glass')

    def set_bell(self, count):
        self.bell.set_label(f'Alertas · {count}' if count else 'Alertas')

    def fold(self, width):
        """Plegada, la barra lateral no achica el contenido: con la ventana
        angosta (hasta 480) el dibujo conserva todo su ancho."""
        self.side_box.set_visible(not width or width >= FOLD_W)

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
        self.refs = {}
        self.set_visible(False)

    def natural_h(self, width):
        """Lo que mide el contenido a ese ancho: el tablero pide ese alto."""
        return self.page.measure(Gtk.Orientation.VERTICAL, max(1, int(width)))[1]

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
        def shape(group):
            return tuple((c['role'], c['busy'], c['ask'], c['pet'], len(self._lines(c))) for c in group)
        structure = (shape(cards), shape(free))
        if structure == self.signature:
            self._refresh_texts(list(cards) + list(free))   # mismo tablero: solo cambian los textos
            return
        self.signature = structure
        self.faces = []
        self.refs = {}
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        for group, small in ((cards, False), (free, True)):
            if not group:
                continue
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_homogeneous(small)          # los libres, en mosaico parejo que llena el ancho
            flow.set_min_children_per_line(2 if small else 1)
            flow.set_max_children_per_line(4)
            flow.set_column_spacing(SPACE[1])
            flow.set_row_spacing(SPACE[1])
            flow.set_activate_on_single_click(False)
            for card in group:
                flow.append(self._card(card, handlers, small=small))
            self.page.append(flow)

    @staticmethod
    def _lines(card):
        return card['steps'][-(2 if card['ask'] else 1):]

    def _refresh_texts(self, cards):
        """Cambia el texto de las etiquetas que ya están, sin tocar nada más:
        reconstruir cada segundo pierde el foco y el hover y hace parpadear."""
        for card in cards:
            ref = self.refs.get(card['role'])
            if ref is None:
                continue
            if ref['state'] is not None and ref['state'].get_label() != card['state']:
                ref['state'].set_label(card['state'])
            for label, line in zip(ref['steps'], self._lines(card)):
                if label.get_label() != line:
                    label.set_label(line)

    def _card(self, card, handlers, small=False):
        ref = {'state': None, 'steps': [], 'small': small}
        self.refs[card['role']] = ref
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
        ref['box'] = box
        box.add_css_class('elyares-card')
        size = 40 if small else 48
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
        ref['state'] = state
        if small:
            box.update_property([Gtk.AccessibleProperty.LABEL], [f'{card["role"]}, {card["state"]}'])
        for line in self._lines(card):
            step = Gtk.Label(label=line, xalign=0, wrap=True)
            step.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            step.set_max_width_chars(20)    # sin esto una línea larga ensancha la tarjeta y caben menos por fila
            step.set_lines(3 if card['ask'] else 2)
            step.set_ellipsize(Pango.EllipsizeMode.END)
            text.append(step)
            ref['steps'].append(step)
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
        self.info = None
        self.set_visible(False)

    def place(self, height):
        self.set_visible(height > 0)
        if height > 0:
            self.set_size_request(-1, int(height))

    def _refresh(self, info):
        where = f' · {info["where"]}' if info['where'] else ''
        now = (info['name'], info['project'], info['status'], where)
        if now != self.last:
            self.last = now
            self.title.set_markup(f'<span foreground="{info["color"]}" weight="bold">'
                                  f'{GLib.markup_escape_text(info["name"])}</span>'
                                  f' | {GLib.markup_escape_text(info["project"])}')
            self.status.set_label(info['status'] + where)
        self.face.queue_draw()

    def set_info(self, info, handlers):
        """`info`: role, pet, name, color, project, status, where, busy,
        can_split. `handlers`: face(cr, role, pet, w, h, moving), act(key)."""
        self.info = info                # la cara lee siempre lo último
        shape = (info['role'], info['busy'], info['can_split'])
        if shape == self.signature:
            self._refresh(info)         # mismos botones: solo cambian los textos
            return
        self.signature = shape
        while (child := self.get_first_child()) is not None:
            self.remove(child)
        face = Gtk.DrawingArea()
        face.set_content_width(40)
        face.set_content_height(40)
        face.set_draw_func(lambda _da, cr, w, h: handlers['face'](
            cr, self.info['role'], self.info['pet'], w, h, self.info['busy']))
        self.face = face
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
        self.title, self.status, self.last = title, status, (info['name'], info['project'], info['status'], where)
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


class TmuxPanel(Gtk.ScrolledWindow):
    """Las sesiones de tmux como proyectos: una tarjeta por sesión y, dentro,
    un botón por ventana que salta a ella. Sin estado propio: la llena la isla."""

    STATES = {'permission': ('●', 'pide permiso'), 'waiting': ('▲', 'espera respuesta'),
              'working': ('●', 'trabaja'), 'done': ('○', 'terminó'), 'idle': ('○', 'en reposo')}
    TONES = {'permission': 'red', 'waiting': 'yellow', 'working': 'green', 'done': 'metal', 'idle': 'metal'}

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

    def set_sessions(self, sessions, handlers):
        """`sessions`: [dict(name, state, claudes, windows=[dict(index, name, state, path)])] o
        None si tmux aún no contestó. `handlers`: jump(sesión, ventana)."""
        sig = repr(sessions)
        if sig == self.signature:
            return
        self.signature = sig
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        if sessions is None:
            self._note('Buscando sesiones de tmux…')
        elif not sessions:
            self._note('tmux no está corriendo. Abre una sesión en la terminal y aparecerá aquí.')
        for sess in sessions or []:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
            card.add_css_class('elyares-card')
            claudes = sess['claudes']
            count = 'sin Claude' if not claudes else '1 Claude' if claudes == 1 else f'{claudes} Claude'
            title = Gtk.Label(xalign=0)
            title.set_markup(f'<b>{GLib.markup_escape_text(sess["name"])}</b>  '
                             f'<span alpha="60%">{count}</span>')
            card.append(title)
            for win in sess['windows']:
                card.append(self._window(sess['name'], win, handlers))
            self.page.append(card)

    def _note(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        label.add_css_class('dim-label')
        self.page.append(label)

    def _window(self, session, win, handlers):
        mark, said = self.STATES.get(win['state'], ('', ''))
        btn = Gtk.Button()
        btn.add_css_class('elyares-btn')
        btn.set_halign(Gtk.Align.FILL)
        label = Gtk.Label(xalign=0)
        color = mascot.COLORS.get(self.TONES.get(win['state'], 'metal'), '#8f9ab8')
        dot = f'<span foreground="{color}">{mark}</span> ' if mark else ''
        tail = f'  <span alpha="60%">{said}</span>' if said else ''
        crew = ''.join(f' <span foreground="{mascot.accent(role)}">●</span>' for role in win.get('agents', ()))
        label.set_markup(f'{dot}{win["index"]} · {GLib.markup_escape_text(win["name"])}{tail}{crew}')
        btn.set_child(label)
        btn.update_property([Gtk.AccessibleProperty.LABEL],
                            [f'Ir a la ventana {win["name"]} de {session}' + (f', {said}' if said else '')
                             + (f', con {len(win["agents"])} subagentes' if win.get('agents') else '')])
        btn.connect('clicked', lambda _b: handlers['jump'](session, win['index']))
        return btn


class PomodoroPanel(Gtk.ScrolledWindow):
    """El pomodoro de `coffe`: el reloj, la tarea en curso con sus botones y
    las tareas pendientes para empezar una. Sin estado propio: la llena la isla."""

    TONES = {'focus': 'green', 'overlearning': 'green', 'break': 'yellow', 'break-long': 'yellow'}

    def __init__(self):
        super().__init__()
        self.add_css_class('elyares-sources')
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.page, f'set_margin_{side}')(SPACE[2])
        self.set_child(self.page)
        self.signature = None
        self.clock = None               # el reloj se retoca en el sitio: reconstruir pierde foco y hover
        self.set_visible(False)

    def set_pomodoro(self, status, tasks, handlers):
        """`status`: lo que da `pomodoro.describe` (None si el reloj no responde);
        `tasks`: [dict(id, title, project)]. `handlers`: act(orden, *args)."""
        if status is None:
            sig = ('off',)
        else:
            sig = (status['phase'], status['task'], status['parked'], status['today'], status['cycle'],
                   repr(tasks))
        if sig != self.signature:
            self.signature = sig
            self._build(status, tasks, handlers)
        if status is not None and self.clock is not None:
            self.clock.set_markup(self._clock_markup(status))

    @staticmethod
    def _clock_markup(status):
        color = mascot.COLORS.get(PomodoroPanel.TONES.get(status['phase'], 'metal'), '#8f9ab8')
        return (f'<span size="xx-large" weight="bold" foreground="{color}">{status["clock"]}</span>  '
                f'<span alpha="70%">{status["text"]}</span>')

    def _build(self, status, tasks, handlers):
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        self.clock = None
        if status is None:
            note = Gtk.Label(label='El reloj de coffe no responde. Arráncalo con: systemctl --user start coffe',
                             xalign=0, wrap=True)
            note.add_css_class('dim-label')
            self.page.append(note)
            return
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        card.add_css_class('elyares-card')
        self.clock = Gtk.Label(xalign=0)
        card.append(self.clock)
        task = Gtk.Label(xalign=0, wrap=True)
        task.set_text(status['task'] or ('Tarea en el refri' if status['parked'] else 'Sin tarea en curso'))
        card.append(task)
        done = ' '.join('●' if i < status['cycle'] else '○' for i in range(status['cycle_of']))
        count = Gtk.Label(xalign=0)
        count.set_markup(f'<span alpha="60%">Hoy {status["today"]} · ciclo {done}</span>')
        card.append(count)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
        if status['parked']:
            row.append(self._button('Sacar del refri', lambda: handlers['act']('resume')))
        if status['running']:
            row.append(self._button('Al refri', lambda: handlers['act']('pause')))
            row.append(self._button('Tirar pomodoro', lambda: handlers['act']('void')))
            if status['task']:
                row.append(self._button('Tarea hecha', lambda: handlers['act']('done')))
        card.append(row)
        self.page.append(card)
        head = Gtk.Label(label='EMPEZAR UNA TAREA', xalign=0)
        head.add_css_class('elyares-section')
        self.page.append(head)
        if not tasks:
            self._note('Sin tareas pendientes.')
        for t in tasks:
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[0])
            btn = Gtk.Button()
            btn.add_css_class('elyares-btn')
            btn.set_hexpand(True)
            label = Gtk.Label(xalign=0)
            label.set_markup(f'{GLib.markup_escape_text(t["title"])}  '
                             f'<span alpha="60%">{GLib.markup_escape_text(t["project"])}</span>')
            btn.set_child(label)
            btn.update_property([Gtk.AccessibleProperty.LABEL],
                                [f'Empezar un pomodoro en {t["title"]}, de {t["project"]}'])
            btn.connect('clicked', lambda _b, tid=t['id']: handlers['act']('start', tid))
            line.append(btn)
            if t.get('repo') and 'agent' in handlers:
                with_agent = Gtk.Button(label='Con agente')
                with_agent.add_css_class('elyares-btn')
                with_agent.update_property([Gtk.AccessibleProperty.LABEL],
                                           [f'Empezar un pomodoro en {t["title"]} y abrir el chat en su proyecto'])
                with_agent.connect('clicked', lambda _b, t=t: handlers['agent'](t['id'], t['repo']))
                line.append(with_agent)
            self.page.append(line)

    def _note(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        label.add_css_class('dim-label')
        self.page.append(label)

    @staticmethod
    def _button(text, call):
        btn = Gtk.Button(label=text)
        btn.add_css_class('elyares-btn')
        btn.connect('clicked', lambda _b: call())
        return btn


_font_provider = None


def load_fonts():
    """La letra de los widgets: un segundo estilo, encima del primero, que se rehace al cambiarla."""
    global _font_provider
    if _font_provider is None:
        _font_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), _font_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    _font_provider.load_from_string(fonts.css())


class SettingsPanel(Gtk.ScrolledWindow):
    """Ajustes: un interruptor por cada clave que hoy se cambia con una orden
    o un clic. Cada fila es (clave, texto, activo, nota)."""

    def __init__(self):
        super().__init__()
        self.add_css_class('elyares-sources')
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[2])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.page, f'set_margin_{side}')(SPACE[2])
        self.set_child(self.page)
        self.signature = None
        self.position = None
        self.set_visible(False)

    def set_rows(self, rows, position, handlers, family=fonts.SYSTEM, theme_key=themes.DEFAULT, tired_scale=125):
        """`rows`: [(clave, texto, activo, nota)]; `position`: 0..100 o None.
        `handlers`: toggle(clave), move(valor), theme(), font(familia), pick_theme(clave), tired_scale(%)."""
        sig = repr((rows, position, family, theme_key, tired_scale))
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
        self.page.append(Gtk.Label(label='Tamaño de la vista cansada', xalign=0))
        sizes = Gtk.DropDown.new_from_strings([f'{pct} %' for pct in fonts.TIRED_SCALES])
        sizes.set_halign(Gtk.Align.START)
        sizes.set_selected(fonts.TIRED_SCALES.index(tired_scale) if tired_scale in fonts.TIRED_SCALES else 0)
        sizes.update_property([Gtk.AccessibleProperty.LABEL], ['Tamaño de la letra con la vista cansada'])
        sizes.connect('notify::selected', lambda dd, _p: fonts.TIRED_SCALES[dd.get_selected()] != tired_scale
                      and handlers['tired_scale'](fonts.TIRED_SCALES[dd.get_selected()]))
        self.page.append(sizes)
        self.page.append(Gtk.Label(label='Tema', xalign=0))
        tema = Gtk.DropDown.new_from_strings([themes.label(key) for key in themes.keys()])
        tema.set_halign(Gtk.Align.START)
        tema.set_selected(themes.keys().index(themes.valid(theme_key)))
        tema.update_property([Gtk.AccessibleProperty.LABEL], ['Tema de la isla y la app'])
        tema.connect('notify::selected', lambda dd, _p: themes.keys()[dd.get_selected()] != theme_key
                     and handlers['pick_theme'](themes.keys()[dd.get_selected()]))
        self.page.append(tema)
        self.page.append(Gtk.Label(label='Letra', xalign=0))
        names = [choice[1] for choice in fonts.CHOICES]
        pick = Gtk.DropDown.new_from_strings(names)
        pick.set_halign(Gtk.Align.START)
        pick.set_selected(next((i for i, choice in enumerate(fonts.CHOICES) if choice[0] == family), 0))
        pick.update_property([Gtk.AccessibleProperty.LABEL], ['Letra de la app'])
        pick.connect('notify::selected', lambda dd, _p: fonts.CHOICES[dd.get_selected()][0] != family
                     and handlers['font'](fonts.CHOICES[dd.get_selected()][0]))
        self.page.append(pick)
        note = Gtk.Label(label='Vale para la isla y para la ventana; el código sigue en monoespaciada.',
                         xalign=0, wrap=True)
        note.add_css_class('dim-label')
        self.page.append(note)
        theme = Gtk.Button(label='Releer los colores del tema')
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
        self.refs = {'steps': []}
        self.picked = None              # el paso abierto abajo, con su texto entero
        self.last = None                # (d, handlers) para rehacerlo al elegir otro paso
        self.set_visible(False)

    place = BoardPanel.place
    animate = BoardPanel.animate

    def natural_h(self, width):
        """Lo que mide el desglose a ese ancho: la ventana crece hasta ahí en vez de pedir scroll."""
        root = self.get_child()
        return 0 if root is None else root.measure(Gtk.Orientation.VERTICAL, max(1, int(width)))[1]

    def _pick(self, index):
        """Un clic en un paso lo abre abajo; otro clic en el mismo lo cierra."""
        self.picked = None if self.picked == index else index
        if self.last is not None:
            self.signature = None
            self.set_focus(*self.last)
            self.last[1]['pick']()

    @staticmethod
    def _detail_head(index, spent):
        return f'Paso {index + 1}' + (f' · {spent}' if spent else '')

    def _refresh(self, d):
        for key in ('label', 'summary'):
            lab = self.refs.get(key)
            if lab is not None and lab.get_label() != d[key]:
                lab.set_label(d[key])
        for (m, t, when), (mark, color, text, spent) in zip(self.refs['steps'], d['steps']):
            if t.get_label() != text:
                t.set_label(text)
            if when.get_label() != spent:
                when.set_label(spent)
        if self.picked is not None and 'detail' in self.refs:
            head, body = self.refs['detail']
            _mark, _color, text, spent = d['steps'][self.picked]
            if body.get_label() != text:
                body.set_label(text)
            if head.get_label() != self._detail_head(self.picked, spent):
                head.set_label(self._detail_head(self.picked, spent))

    def set_focus(self, d, handlers):
        """`d`: role, name, color, pet, busy, label, summary, steps
        [(marca, color, texto, tiempo)], links [(tipo, clave, texto)], others
        [(rol, pet, activo)], hidden, empty. `handlers`: face, link, other, pick."""
        self.last = (d, handlers)
        if self.picked is not None and self.picked >= len(d['steps']):
            self.picked = None
        shape = (d['role'], d['busy'], d['pet'], tuple(d['links']), tuple(d['others']),
                 d['hidden'], d['empty'], len(d['steps']), tuple(s[0] for s in d['steps']), self.picked)
        if shape == self.signature:
            self._refresh(d)            # el mismo desglose: solo cambian los textos
            return
        self.signature = shape
        self.faces = []
        self.refs = {'steps': []}
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[2])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(root, f'set_margin_{side}')(SPACE[2])
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        left.set_size_request(150, -1)
        face = Gtk.DrawingArea()
        face.set_content_width(64)
        face.set_content_height(64)
        face.set_halign(Gtk.Align.CENTER)
        face.set_draw_func(lambda _da, cr, w, h: handlers['face'](cr, d['role'], d['pet'], w, h, d['busy']))
        if d['busy']:
            self.faces.append(face)
        left.append(face)
        name = Gtk.Label()
        name.set_markup(f'<span foreground="{d["color"]}" weight="bold">{GLib.markup_escape_text(d["name"])}</span>')
        left.append(name)
        for key, text in (('label', d['label']), ('summary', d['summary'])):
            lab = Gtk.Label(label=text)
            lab.add_css_class('dim-label')
            lab.set_ellipsize(Pango.EllipsizeMode.END)
            left.append(lab)
            self.refs[key] = lab
        for kind, key, text in d['links']:
            btn = Gtk.Button(label=text)
            btn.add_css_class('elyares-btn')
            btn.add_css_class('compact')
            btn.connect('clicked', lambda _b, k=kind, v=key: handlers['link'](k, v))
            left.append(btn)
        root.append(left)
        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        mid.set_hexpand(True)
        mid.set_size_request(0, -1)
        if d['empty']:
            mid.append(Gtk.Label(label=d['empty'], xalign=0, wrap=True))
        if d['hidden']:
            more = Gtk.Label(label=f'⋯ {d["hidden"]} paso{"" if d["hidden"] == 1 else "s"} antes', xalign=0)
            more.add_css_class('dim-label')
            mid.append(more)
        for i, (mark, color, text, spent) in enumerate(d['steps']):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            row.add_css_class('elyares-card')
            if i == self.picked:
                row.add_css_class('raised')
            row.set_cursor_from_name('pointer')
            click = Gtk.GestureClick()
            click.connect('released', lambda _g, _n, _x, _y, i=i: self._pick(i))
            row.add_controller(click)
            m = Gtk.Label()
            m.set_markup(f'<span foreground="{color}">{GLib.markup_escape_text(mark)}</span>')
            t = Gtk.Label(label=text, xalign=0, wrap=True)
            t.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            t.set_lines(2)
            t.set_hexpand(True)
            t.set_max_width_chars(1)        # el mínimo es una letra: se envuelve al ancho que haya
            t.set_ellipsize(Pango.EllipsizeMode.END)
            when = Gtk.Label(label=spent)
            when.add_css_class('dim-label')
            row.append(m)
            row.append(t)
            row.append(when)
            mid.append(row)
            self.refs['steps'].append((m, t, when))
        if self.picked is not None:
            _mark, _color, text, spent = d['steps'][self.picked]
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
            box.add_css_class('elyares-card')
            head = Gtk.Label(label=self._detail_head(self.picked, spent), xalign=0)
            head.add_css_class('dim-label')
            body = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True)
            body.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            body.set_max_width_chars(1)
            box.append(head)
            box.append(body)
            mid.append(box)
            self.refs['detail'] = (head, body)
        others = Gtk.FlowBox()              # envuelve: en una fila no cabrían en una ventana angosta
        others.set_selection_mode(Gtk.SelectionMode.NONE)
        others.set_max_children_per_line(8)
        others.set_column_spacing(SPACE[0])
        others.set_row_spacing(SPACE[0])
        others.set_halign(Gtk.Align.START)
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


class FlowsPanel(Gtk.ScrolledWindow):
    """Flujos: la lista de workflows guardados, con el mismo estilo que el resto
    de la app. Cada uno es una tarjeta con su nombre, sus pasos y dónde corre,
    y sus botones Lanzar, Editar y Borrar. El editor y la corrida siguen en el
    dibujo de la isla. Sin estado propio: la llena la isla con `set_flows`."""

    def __init__(self):
        super().__init__()
        self.add_css_class('elyares-sources')
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[2])
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.page, f'set_margin_{side}')(SPACE[3])
        self.set_child(self.page)
        self.signature = None
        self.refs = []
        self.set_visible(False)

    def set_flows(self, rows, handlers):
        """`rows`: [dict(name, steps, place, status, tone, mine, busy, launch,
        delete)]. `handlers`: act(clave) con las claves de siempre:
        launch:N, edit:N, delete:N, view, new, close."""
        shape = tuple((r['name'], r['mine'], r['busy'], r['launch'], r['delete']) for r in rows)
        if shape == self.signature:
            for ref, r in zip(self.refs, rows):
                note = r['place'] if not r['status'] else f'{r["place"]} · {r["status"]}'
                if ref.get_label() != note:
                    ref.set_label(note)
            return
        self.signature = shape
        self.refs = []
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
        title = Gtk.Label(xalign=0)
        title.set_markup('<span size="x-large" weight="bold">Workflows</span>')
        head.append(title)
        count = Gtk.Label(label='' if not rows else '1 guardado' if len(rows) == 1 else f'{len(rows)} guardados')
        count.add_css_class('dim-label')
        count.set_hexpand(True)
        count.set_xalign(0)
        head.append(count)
        new = Gtk.Button(label='Nuevo')
        new.add_css_class('elyares-btn')
        new.add_css_class('primary')
        new.connect('clicked', lambda _b: handlers['act']('new'))
        close = Gtk.Button(label='Cerrar')
        close.add_css_class('elyares-btn')
        close.connect('clicked', lambda _b: handlers['act']('close'))
        head.append(new)
        head.append(close)
        self.page.append(head)
        if not rows:
            empty = Gtk.Label(label='Todavía no guardaste ningún workflow. Crea uno para repetir una cadena '
                                    'de agentes sin escribirla cada vez.', xalign=0, wrap=True)
            empty.add_css_class('dim-label')
            self.page.append(empty)
            return
        for i, r in enumerate(rows):
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
            card.add_css_class('elyares-card')
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
            col.set_hexpand(True)
            name = Gtk.Label(xalign=0)
            name.set_markup(f'<b>{GLib.markup_escape_text(r["name"])}</b>')
            name.set_ellipsize(Pango.EllipsizeMode.END)
            note = Gtk.Label(xalign=0, wrap=True)
            note.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            note.set_max_width_chars(1)
            note.add_css_class('dim-label')
            note.set_label(r['place'] if not r['status'] else f'{r["place"]} · {r["status"]}')
            self.refs.append(note)
            col.append(name)
            col.append(note)
            card.append(col)
            buttons = [('Ver', 'view', False, r['mine']),
                       ('Lanzar', f'launch:{i}', True, r['launch']),
                       ('Editar', f'edit:{i}', False, True),
                       ('Borrar', f'delete:{i}', False, r['delete'])]
            for label, key, primary, on in buttons:
                if label == 'Ver' and not r['mine']:
                    continue
                btn = Gtk.Button(label=label)
                btn.add_css_class('elyares-btn')
                btn.add_css_class('compact')
                if primary:
                    btn.add_css_class('primary')
                if label == 'Borrar':
                    btn.add_css_class('danger')
                btn.set_sensitive(on)
                btn.set_valign(Gtk.Align.CENTER)
                btn.connect('clicked', lambda _b, k=key: handlers['act'](k))
                card.append(btn)
            self.page.append(card)
