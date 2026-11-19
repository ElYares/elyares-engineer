"""El panel «Más» de la isla suelta: lo que no cabe en el pie de pastillas.

Una fila por opción (Flujos, Proyectos, Contenedores, Temas, Ajustes), con su nota y un «›», en el mismo formato
del panel de Ajustes. Un clic en la fila cierra este panel y abre el de la opción, igual que
la pastilla que antes estaba en el pie. Se abre con la pastilla «Más» o `elyares-ctl more`.
`MoreView` es parte de la isla (`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

from . import mascot, prefsview, themes

MORE_PILL = 'more'                        # la pastilla «Más» del pie
MORE_W = prefsview.PREFS_W
# (clave, texto, nota): lo que abre cada fila, en el orden en que salían las pastillas.
MORE_ROWS = (
    ('flows', 'Flujos', 'Tus cadenas de agentes guardadas.'),
    ('projects', 'Proyectos', 'Empieza un chat en cualquiera.'),
    ('boxes', 'Contenedores', 'Proyectos de DevHerd: levantar, parar y ver qué corre.'),
    ('themes', 'Temas', 'Cambia los colores de la isla y de la ventana.'),
    ('prefs', 'Ajustes', 'Vidrio, brillo, estilo y vista cansada.'),
)


class MoreView:
    """Lo que guarda: `more_open` (el panel está a la vista)."""

    more_open = False

    def toggle_more(self):
        """Abre o cierra el panel. En la ventana no hay: sus vistas están en la barra de título."""
        if self.windowed:
            return
        self.more_open = not self.more_open
        self.off = False
        if self.more_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.boxes_open = self.themes_open = False
        self.ensure_tick()

    def more_goal(self):
        return MORE_W, prefsview.PREFS_HEAD + len(MORE_ROWS) * prefsview.PREFS_ROW + prefsview.PREFS_FOOT

    def draw_more(self, cr, x0, w, h, alpha):
        pad, row = prefsview.PREFS_PAD, prefsview.PREFS_ROW
        left, width = x0 + pad, w - 2 * pad
        soft = mascot.rgba(self.ink('text', .62))[:3]
        self.put(cr, 'Más', prefsview.FONT_PREFS_TITLE, left, 14, (.95, .96, 1), alpha)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        x = left + width - lw
        over = self.over(x - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('more', 'close', x - 4, 10, lw + 8, lh + 8))
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, prefsview.PREFS_HEAD - 8, width, 1)
        cr.fill()
        for i, (key, label, note) in enumerate(MORE_ROWS):
            self.draw_more_row(cr, key, label, note, left, prefsview.PREFS_HEAD + i * row, width, soft, alpha)

    def draw_more_row(self, cr, key, label, note, x, y, w, soft, alpha):
        """Una opción: su texto, su nota y «›» a la derecha. Todo el renglón es un clic."""
        row = prefsview.PREFS_ROW
        if self.over(x - 4, y, w + 8, row):
            mascot.box(cr, x - 4, y, w + 8, row, 6)
            cr.set_source_rgba(*themes.glow(), .08 * alpha)
            cr.fill()
        self.put(cr, label, prefsview.FONT_PREFS, x + 4, y + 3, mascot.rgba(self.ink('head'))[:3], alpha, width=w - 60)
        self.put(cr, note, prefsview.FONT_PREFS_NOTE, x + 4, y + 16, soft, alpha, width=w - 60)
        self.put(cr, '›', prefsview.FONT_PREFS_TITLE, x + w - 14, y + 4, soft, alpha)
        self.hits.append(('more', key, x - 4, y, w + 8, row))

    def on_more_hit(self, key):
        """Un clic: cerrar, o pasar al panel de la opción."""
        self.more_open = False
        if key == 'flows':
            self.toggle_workflows()
        elif key == 'projects':
            self.toggle_projects()
        elif key == 'boxes':
            self.toggle_boxes()
        elif key == 'themes':
            self.toggle_themes()
        elif key == 'prefs':
            self.toggle_prefs()
        self.ensure_tick()
