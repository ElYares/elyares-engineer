"""El marco de widgets de la ventana de la app (decisión 009 del vault).

La ventana lleva widgets GTK4 en lo que es control —barra de título, vistas,
barra lateral— y deja en Cairo lo que es dibujo: el `overlay` de la isla va
dentro, como un contenido más, hasta que cada vista se migre. Este módulo solo
arma los widgets; qué hace cada botón lo decide quien lo crea con `on_view`.
"""

from gi.repository import Gdk, Gtk, Pango

# (clave, texto) en el orden de la barra de título.
VIEWS = (('board', 'Tablero'), ('chat', 'Chat'), ('flows', 'Flujos'),
         ('projects', 'Proyectos'), ('sources', 'Fuentes'))
SIDEBAR_W = 180

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
.elyares-side row {{ border-radius: {RADIUS[0]}px; padding: {SPACE[1]}px {SPACE[2]}px; }}
.elyares-card {{ background: {SURFACE[1]}; color: {INK}; border-radius: {RADIUS[1]}px; padding: {SPACE[2]}px; }}
.elyares-card.raised {{ background: {SURFACE[2]}; }}
.elyares-btn {{ background: {SURFACE[2]}; color: {INK}; border-radius: {RADIUS[0]}px;
  padding: {SPACE[1]}px {SPACE[3]}px; border: none; box-shadow: none; }}
.elyares-btn.primary {{ background: {ACCENT}; color: {SURFACE[0]}; }}
.elyares-btn.danger {{ background: {DANGER}; color: {SURFACE[0]}; }}
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

    def set_sessions(self, rows, chosen):
        """La barra lateral: una fila por sesión, `rows` = [(sid, nombre,
        color del punto o None, texto de estado)]. El estado va también en
        texto y en el nombre accesible: no depende solo del color."""
        key = (tuple(rows), chosen)
        if key == self.session_rows:
            return
        self.session_rows = key
        while (row := self.sidebar.get_first_child()) is not None:
            self.sidebar.remove(row)
        picked = None
        for sid, name, color, text in rows:
            row = Gtk.ListBoxRow()
            row.sid = sid
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE[1])
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

    def chrome_h(self):
        """Lo que la barra de título le quita al alto de la ventana."""
        return self.header.get_height()

    def _toggled(self, btn, key):
        if btn.get_active() and not self.syncing:
            self.on_view(key)
