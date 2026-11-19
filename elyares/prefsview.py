"""El panel de Ajustes de la isla suelta: lo que se cambia más seguido, sin abrir la ventana.

Interruptores de vidrio, brillo, compacto, fijada, estilo, chat técnico, movimiento
reducido y vista cansada, y la opacidad del vidrio con − y +. Todo lo demás (tema,
letra, posición, fuentes) sigue en la vista Ajustes de la ventana.

Se abre con la pastilla «Ajustes» del pie de la isla o con `elyares-ctl prefs`.
Cada cambio pasa por `window_setting`, el mismo camino de la ventana y la paleta.
`PrefsView` es parte de la isla (`app.Island` la hereda) y usa sus ayudantes de
dibujo. Se llama «prefs» y no «settings» porque `self.settings` ya es el diccionario.
"""

import math

from . import mascot, themes

PREFS_W = 460
PREFS_PAD = 16
PREFS_HEAD = 48
PREFS_ROW = 30
PREFS_FOOT = 24
PREFS_PILL = 'prefs'                       # la pastilla «Ajustes» del pie
FONT_PREFS = 'Sans Medium 9'
FONT_PREFS_NOTE = 'JetBrainsMono Nerd Font 8'
FONT_PREFS_TITLE = 'Sans Semi-Bold 11'
ALPHA_STEP = 5
# (clave, texto, nota): las claves son las de `window_setting`.
PREFS_ROWS = (
    ('glass', 'Vidrio', 'La isla translúcida, desenfocada por Hyprland.'),
    ('glass_fx', 'Brillo y filo del vidrio', 'Apagado: solo transparencia con desenfoque.'),
    ('compact', 'Modo compacto', 'Una pastilla pequeña hasta que pasa algo.'),
    ('pinned', 'Isla fijada', 'Se queda abierta y no se esconde.'),
    ('tech_style', 'Estilo técnico', 'Esquinas rectas, bordes de 1 px y letra monoespaciada.'),
    ('chat_tech', 'Chat técnico', 'Bloques y tablas con borde fino.'),
    ('reduce_motion', 'Movimiento reducido', 'Quieta no parpadea y redibuja a 2 fps.'),
    ('tired_eyes', 'Vista cansada', 'Letra más grande y más gruesa.'),
)


class PrefsView:
    """Lo que guarda: `prefs_open` (el panel está a la vista)."""

    prefs_open = False

    def toggle_prefs(self):
        """Abre o cierra el panel. En la ventana no hay: tiene su vista Ajustes."""
        if self.windowed:
            return
        self.prefs_open = not self.prefs_open
        self.off = False
        if self.prefs_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.more_open = self.boxes_open = self.themes_open = self.gf_open = self.sp_open = self.sv_open = False
        self.ensure_tick()

    def prefs_goal(self):
        return PREFS_W, PREFS_HEAD + (len(PREFS_ROWS) + 1) * PREFS_ROW + PREFS_FOOT

    def draw_prefs(self, cr, x0, w, h, alpha):
        left, width = x0 + PREFS_PAD, w - 2 * PREFS_PAD
        soft = mascot.rgba(self.ink('text', .62))[:3]
        self.put(cr, 'Ajustes', FONT_PREFS_TITLE, left, 14, mascot.rgba(self.ink('text'))[:3], alpha)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        x = left + width - lw
        over = self.over(x - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('prefs', 'close', x - 4, 10, lw + 8, lh + 8))
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, PREFS_HEAD - 8, width, 1)
        cr.fill()
        for i, (key, label, note) in enumerate(PREFS_ROWS):
            self.draw_pref(cr, key, label, note, left, PREFS_HEAD + i * PREFS_ROW, width, soft, alpha)
        self.draw_pref_opacity(cr, left, PREFS_HEAD + len(PREFS_ROWS) * PREFS_ROW, width, soft, alpha)
        self.put(cr, 'Tema, letra y fuentes: en la ventana (elyares-ctl window)', FONT_PREFS_NOTE,
                 left, h - PREFS_FOOT + 6, soft, alpha * .9, width=width)

    def draw_pref(self, cr, key, label, note, x, y, w, soft, alpha):
        """Un interruptor: su texto, su nota y la palanca a la derecha. Todo el renglón es un clic."""
        on = bool(self.settings.get(key))
        if self.over(x - 4, y, w + 8, PREFS_ROW):
            mascot.box(cr, x - 4, y, w + 8, PREFS_ROW, 6)
            cr.set_source_rgba(*themes.glow(), .08 * alpha)
            cr.fill()
        self.put(cr, label, FONT_PREFS, x + 4, y + 3, mascot.rgba(self.ink('head'))[:3], alpha, width=w - 60)
        self.put(cr, note, FONT_PREFS_NOTE, x + 4, y + 16, soft, alpha, width=w - 60)
        sx, sy = x + w - 36, y + PREFS_ROW / 2 - 8
        mascot.box(cr, sx, sy, 32, 16, 8)
        cr.set_source_rgba(*(themes.hot() if on else mascot.rgba('metal', .5)[:3]), (.9 if on else .6) * alpha)
        cr.fill()
        cr.new_sub_path()
        cr.arc(sx + (24 if on else 8), sy + 8, 6, 0, 2 * math.pi)
        cr.set_source_rgba(.98, .98, 1, alpha)
        cr.fill()
        self.hits.append(('prefs', key, x - 4, y, w + 8, PREFS_ROW))

    def draw_pref_opacity(self, cr, x, y, w, soft, alpha):
        """La opacidad del vidrio: una barra con − y + de a ALPHA_STEP."""
        pct = self.glass_pct()
        self.put(cr, 'Opacidad del vidrio', FONT_PREFS, x + 4, y + 3, mascot.rgba(self.ink('head'))[:3], alpha)
        self.put(cr, f'{pct} %', FONT_PREFS_NOTE, x + 4, y + 16, soft, alpha)
        right = x + w
        for key, label, bx in (('alpha+', '+', right - 24), ('alpha-', '−', right - 24 - 120 - 8 - 24)):
            over = self.over(bx, y + 3, 24, 24)
            mascot.box(cr, bx, y + 3, 24, 24, 12)
            cr.set_source_rgba(*themes.glow(), (.16 if over else .08) * alpha)
            cr.fill()
            self.put(cr, label, FONT_PREFS, bx + 12, y + 7, mascot.rgba(self.ink('head'))[:3], alpha, align=.5)
            self.hits.append(('prefs', key, bx, y + 3, 24, 24))
        bar_x, bar_w = right - 24 - 4 - 120, 120
        mascot.box(cr, bar_x, y + 13, bar_w, 4, 2)
        cr.set_source_rgba(*themes.glow(), .12 * alpha)
        cr.fill()
        mascot.box(cr, bar_x, y + 13, max(4, bar_w * (pct - 50) / 50), 4, 2)
        cr.set_source_rgba(*themes.hot(), .9 * alpha)
        cr.fill()

    def on_prefs_hit(self, key):
        """Un clic en el panel: cerrar, mover la opacidad o cambiar un interruptor."""
        if key == 'close':
            self.prefs_open = False
        elif key in ('alpha+', 'alpha-'):
            self.window_glass_alpha(self.glass_pct() + (ALPHA_STEP if key == 'alpha+' else -ALPHA_STEP))
        else:
            self.window_setting(key)
        self.ensure_tick()
