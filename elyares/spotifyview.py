"""El panel de Spotify de la isla suelta: la portada, qué suena y ⏮ ⏯ ⏭.

Se abre desde «Más → Spotify» o con `elyares-ctl spotify`. Lee Spotify por MPRIS (`spotify.py`):
no muestra la playlist, solo la canción de ahora. Con Spotify cerrado dice que no está abierto.
`SpotifyView` es parte de la isla (`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

import math
import threading

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf  # noqa: E402

from . import mascot, prefsview, spotify, themes  # noqa: E402

SPOTIFY_PILL = 'spotify'                 # la pastilla «♪» del pie
SPOTIFY_LABEL = '♪'
SP_W = prefsview.PREFS_W
SP_PAD = prefsview.PREFS_PAD
SP_HEAD = prefsview.PREFS_HEAD
SP_COVER = 112
SP_FOOT = 24
SP_GAP = 16                              # entre la portada y el texto
FONT_SP_TITLE = 'Sans Semi-Bold 12'
FONT_SP_ARTIST = 'Sans Medium 10'
BTN = 30                                 # diámetro de ⏮ y ⏭; el ⏯ mide BTN + 8
_covers = {}                             # (ruta, px) -> GdkPixbuf, o None si no se pudo leer


def clock(seconds):
    """3:07 para 187 s."""
    seconds = max(0, int(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


def pixbuf(path, px):
    """La portada de `path` como imagen cuadrada de `px` px, o None. Una sola lectura por ruta y tamaño."""
    key = (path, px)
    if key not in _covers:
        try:
            _covers[key] = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, px, px, False)
        except Exception:               # un archivo roto no debe tumbar el dibujo
            _covers[key] = None
    return _covers[key]


class SpotifyView:
    """Lo que guarda: `sp_open` (el panel está a la vista) y `sp_watch` (el lector de Spotify)."""

    sp_open = False
    sp_watch = None

    def toggle_spotify(self):
        """Abre o cierra el panel. En la ventana no hay."""
        if self.windowed:
            return
        self.sp_open = not self.sp_open
        self.off = False
        if self.sp_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.more_open = self.boxes_open = False
            self.themes_open = self.gf_open = self.sv_open = self.pm_open = False
            if self.sp_watch is None:
                self.sp_watch = spotify.Watcher()
            self.sp_watch.refresh()
        self.ensure_tick()

    def spotify_busy(self):
        """¿Hay algo que esperar? Spotify aún no contesta, o la portada no termina de bajar."""
        if not self.sp_open or self.windowed or self.sp_watch is None:
            return False
        return not self.sp_watch.loaded or bool(self.sp_watch.fetching)

    def spotify_goal(self):
        return SP_W, SP_HEAD + SP_COVER + SP_FOOT

    def draw_spotify(self, cr, x0, w, h, alpha):
        left, width = x0 + SP_PAD, w - 2 * SP_PAD
        soft = mascot.rgba(self.ink('text', .62))[:3]
        head = mascot.rgba(self.ink('head'))[:3]
        self.put(cr, 'Spotify', prefsview.FONT_PREFS_TITLE, left, 14, mascot.rgba(self.ink('text'))[:3], alpha)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        x = left + width - lw
        over = self.over(x - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('spotify', 'close', x - 4, 10, lw + 8, lh + 8))
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, SP_HEAD - 8, width, 1)
        cr.fill()
        data = self.sp_watch.read() if self.sp_watch else None
        if not data:
            note = 'Spotify no está abierto.' if self.sp_watch and self.sp_watch.loaded else 'Buscando Spotify…'
            self.put(cr, note, prefsview.FONT_PREFS, left + 4, SP_HEAD + 8, head, alpha)
            self.put(cr, 'Ábrelo y la canción aparece aquí.', prefsview.FONT_PREFS_NOTE, left + 4, SP_HEAD + 28, soft, alpha)
            return
        top = SP_HEAD
        self.draw_cover(cr, left, top, SP_COVER, alpha)
        tx, tw = left + SP_COVER + SP_GAP, width - SP_COVER - SP_GAP
        self.put(cr, data['title'] or '(sin título)', FONT_SP_TITLE, tx, top + 2, head, alpha, width=tw)
        self.put(cr, data['artist'], FONT_SP_ARTIST, tx, top + 26, soft, alpha, width=tw)
        self.put(cr, data['album'], prefsview.FONT_PREFS_NOTE, tx, top + 46, soft, alpha * .85, width=tw)
        self.draw_sp_progress(cr, tx, top + 64, tw, data, soft, alpha)
        self.draw_sp_buttons(cr, tx, top + 86, tw, data['playing'], alpha)

    def draw_cover(self, cr, x, y, size, alpha):
        """La portada con esquinas redondas; sin ella (o mientras baja), un cuadro con una nota."""
        path = self.sp_watch.cover() if self.sp_watch else None
        buf = pixbuf(path, size * 2) if path else None
        mascot.box(cr, x, y, size, size, 10)
        if buf is None:
            cr.set_source_rgba(*themes.glow(), .08 * alpha)
            cr.fill()
            self.put(cr, '♪', 'Sans Semi-Bold 28', x + size / 2, y + size / 2 - 22, mascot.rgba(self.ink('text', .5))[:3],
                     alpha, align=.5)
            return
        cr.save()
        cr.clip()
        cr.translate(x, y)
        cr.scale(.5, .5)
        Gdk.cairo_set_source_pixbuf(cr, buf, 0, 0)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def draw_sp_progress(self, cr, x, y, w, data, soft, alpha):
        """La barra de avance con el tiempo corrido y el total. Sin duración (radio, anuncio), solo el corrido."""
        length, pos = data['length'], data['position']
        mascot.box(cr, x, y, w, 4, 2)
        cr.set_source_rgba(*themes.glow(), .12 * alpha)
        cr.fill()
        if length > 0:
            mascot.box(cr, x, y, max(4, w * min(1, pos / length)), 4, 2)
            cr.set_source_rgba(*themes.hot(), .9 * alpha)
            cr.fill()
        self.put(cr, clock(pos), prefsview.FONT_PREFS_NOTE, x, y + 8, soft, alpha * .9)
        if length > 0:
            self.put(cr, clock(length), prefsview.FONT_PREFS_NOTE, x + w, y + 8, soft, alpha * .9, align=1)

    def draw_sp_buttons(self, cr, x, y, w, playing, alpha):
        """⏮ ⏯ ⏭ en fila, centrados bajo la barra. Los iconos se dibujan: la letra no los trae todos."""
        play = BTN + 8
        gap = 14
        total = 2 * BTN + play + 2 * gap
        cx = x + (w - total) / 2
        for key, size in (('prev', BTN), ('play', play), ('next', BTN)):
            by = y + (play - size) / 2
            over = self.over(cx, by, size, size)
            cr.new_sub_path()
            cr.arc(cx + size / 2, by + size / 2, size / 2, 0, 2 * math.pi)
            cr.set_source_rgba(*(themes.hot() if key == 'play' else themes.glow()), (.9 if key == 'play' else .16 if over else .09) * alpha)
            cr.fill()
            # El círculo del ⏯ es blanco en oscuro y tinta en claro: su icono va del color de la isla.
            ink = themes.tuple_of(themes.get()['island']) if key == 'play' else mascot.rgba(self.ink('head'))[:3]
            self.draw_sp_icon(cr, key, cx + size / 2, by + size / 2, size * .34, playing, ink, alpha)
            self.hits.append(('spotify', key, cx, by, size, size))
            cx += size + gap

    @staticmethod
    def draw_sp_icon(cr, key, cx, cy, r, playing, ink, alpha):
        cr.set_source_rgba(*ink, alpha)
        if key == 'play' and playing:                     # pausa: dos barras
            for dx in (-r * .7, r * .1):
                cr.rectangle(cx + dx, cy - r, r * .6, 2 * r)
            cr.fill()
        elif key == 'play':                               # play: triángulo
            cr.move_to(cx - r * .6, cy - r)
            cr.line_to(cx + r, cy)
            cr.line_to(cx - r * .6, cy + r)
            cr.close_path()
            cr.fill()
        else:                                             # ⏮ y ⏭: triángulo y barra
            sign = 1 if key == 'next' else -1
            cr.move_to(cx - sign * r, cy - r)
            cr.line_to(cx + sign * r * .6, cy)
            cr.line_to(cx - sign * r, cy + r)
            cr.close_path()
            cr.fill()
            cr.rectangle(cx + sign * r * .6 - (0 if sign > 0 else r * .3), cy - r, r * .3, 2 * r)
            cr.fill()

    def on_spotify_hit(self, key):
        """Un clic: cerrar, o un botón. La orden va en un hilo y el panel vuelve a leer al terminar."""
        if key == 'close':
            self.sp_open = False
        elif key in spotify.ACTIONS and self.sp_watch is not None:
            watch = self.sp_watch
            if key == 'play' and watch.data:
                watch.data = dict(watch.data, playing=not watch.data['playing'])      # responde al instante

            def go():
                spotify.control(key)
                watch.refresh()
            threading.Thread(target=go, daemon=True).start()
        self.ensure_tick()
