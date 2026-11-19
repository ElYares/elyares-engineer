"""El panel de Temas de la isla suelta: los temas de la ventana, para cambiar de uno con un clic.

Una muestra de cada tema (su fondo, su acento y su tinta), su nombre y su nota, en dos columnas y
con el formato del panel de Ajustes. El de ahora lleva «✓». Un clic cambia el tema de la isla y de
la ventana por `pick_theme`, el mismo camino de la vista Ajustes y de `elyares-ctl theme`; el panel
queda abierto para probar otro. Se abre desde el panel «Más» o con `elyares-ctl themes`.
`ThemesView` es parte de la isla (`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

import math

from . import mascot, prefsview, themes

THEMES_COLS = 2
THEMES_GAP = 12


def split_label(label):
    """«Moonfly (el de nvim)» -> ('Moonfly', 'el de nvim'); sin paréntesis, la nota va vacía."""
    name, _, note = label.partition(' (')
    return name, note.rstrip(')')


class ThemesView:
    """Lo que guarda: `themes_open` (el panel está a la vista)."""

    themes_open = False

    def toggle_themes(self):
        """Abre o cierra el panel. En la ventana no hay: tiene su vista Ajustes."""
        if self.windowed:
            return
        self.themes_open = not self.themes_open
        self.off = False
        if self.themes_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.more_open = self.boxes_open = self.gf_open = self.sp_open = self.sv_open = False
        self.ensure_tick()

    def themes_rows(self):
        return math.ceil(len(themes.THEMES) / THEMES_COLS)

    def themes_goal(self):
        return prefsview.PREFS_W, prefsview.PREFS_HEAD + self.themes_rows() * prefsview.PREFS_ROW + prefsview.PREFS_FOOT

    def draw_themes(self, cr, x0, w, h, alpha):
        pad, row = prefsview.PREFS_PAD, prefsview.PREFS_ROW
        left, width = x0 + pad, w - 2 * pad
        soft = mascot.rgba(self.ink('text', .62))[:3]
        self.put(cr, 'Temas', prefsview.FONT_PREFS_TITLE, left, 14, (.95, .96, 1), alpha)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        x = left + width - lw
        over = self.over(x - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('themes', 'close', x - 4, 10, lw + 8, lh + 8))
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, prefsview.PREFS_HEAD - 8, width, 1)
        cr.fill()
        col_w = (width - THEMES_GAP * (THEMES_COLS - 1)) / THEMES_COLS
        rows = self.themes_rows()
        for i, name in enumerate(themes.THEMES):
            cx = left + (i // rows) * (col_w + THEMES_GAP)
            self.draw_theme(cr, name, cx, prefsview.PREFS_HEAD + (i % rows) * row, col_w, soft, alpha)

    def draw_theme(self, cr, name, x, y, w, soft, alpha):
        """Un tema: su muestra, su nombre, su nota y «✓» si es el de ahora. Todo el renglón es un clic."""
        row, look = prefsview.PREFS_ROW, themes.THEMES[name]
        current = name == themes.current
        if current or self.over(x - 4, y, w + 8, row):
            mascot.box(cr, x - 4, y, w + 8, row, 6)
            cr.set_source_rgba(*themes.glow(), (.12 if current else .08) * alpha)
            cr.fill()
        # La muestra: el fondo de la isla en ese tema, con su acento y su tinta encima.
        mascot.box(cr, x + 2, y + 5, 30, row - 10, 6)
        cr.set_source_rgba(*themes.tuple_of(look['island']), alpha)
        cr.fill_preserve()
        cr.set_source_rgba(*mascot.rgba(self.ink('text', .35))[:3], .6 * alpha)
        cr.set_line_width(1)
        cr.stroke()
        for dx, color in ((9, look['accent']), (21, look['ink'])):
            cr.new_sub_path()
            cr.arc(x + 2 + dx, y + row / 2, 4, 0, 2 * math.pi)
            cr.set_source_rgba(*themes.tuple_of(color), alpha)
            cr.fill()
        label, note = split_label(look['label'])
        self.put(cr, label, prefsview.FONT_PREFS, x + 42, y + 3,
                 themes.hot() if current else mascot.rgba(self.ink('head'))[:3], alpha, width=w - 66)
        if note:
            self.put(cr, note, prefsview.FONT_PREFS_NOTE, x + 42, y + 16, soft, alpha, width=w - 66)
        if current:
            self.put(cr, '✓', prefsview.FONT_PREFS, x + w - 6, y + 7, themes.hot(), alpha, align=1)
        self.hits.append(('themes', name, x - 4, y, w + 8, row))

    def on_themes_hit(self, key):
        """Un clic: cerrar, o poner ese tema."""
        if key == 'close':
            self.themes_open = False
        else:
            self.pick_theme(key)
        self.ensure_tick()
