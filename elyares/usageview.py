"""El panel de Consumo de la isla suelta: lo que llevas de la sesión de 5 h y de la semana, en gráfica.

Se abre desde «Más → Consumo» o con `elyares-ctl usage`. Es lo que dice el módulo de Waybar
(`claudebar`), pero con barras y una gráfica del gasto de cada día (`usage.py`), y con cuánto falta
para que se reinicien. `UsageView` es parte de la isla (`app.Island` la hereda).
"""

from datetime import datetime

from . import mascot, prefsview, themes, usage

US_W = prefsview.PREFS_W
US_PAD = prefsview.PREFS_PAD
US_HEAD = prefsview.PREFS_HEAD
US_BAR_ROW = 46                          # una barra: nombre y %, la barra y cuándo se reinicia
US_CHART_TITLE = 22
US_CHART = 96                            # alto de la gráfica de días
US_LABELS = 16                           # las letras de los días bajo las barras
US_FOOT = 24
FONT_US_BIG = 'Sans Semi-Bold 11'
DAY_LETTERS = 'LMXJVSD'                  # lunes … domingo
WARN, CRIT = 60, 85                      # desde dónde la barra pasa a ámbar y a rojo


def level_color(pct):
    """Verde, ámbar o rojo de aviso según cuánto va (no son del tema)."""
    green, amber, red = themes.signal()
    return themes.tuple_of(red if pct >= CRIT else amber if pct >= WARN else green)


class UsageView:
    """Lo que guarda: `us_open` (el panel está a la vista) y `us_watch` (el lector de `claudebar`)."""

    us_open = False
    us_watch = None

    def toggle_usage(self):
        """Abre o cierra el panel. En la ventana no hay."""
        if self.windowed:
            return
        self.us_open = not self.us_open
        self.off = False
        if self.us_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.more_open = self.boxes_open = False
            self.themes_open = self.gf_open = self.sp_open = self.sv_open = self.pm_open = False
            if self.us_watch is None:
                self.us_watch = usage.Watcher()
            self.us_watch.refresh()
        self.ensure_tick()

    def usage_busy(self):
        """¿Hay algo que esperar? Aún no llega la primera respuesta de `claudebar`."""
        return self.us_open and not self.windowed and self.us_watch is not None and not self.us_watch.loaded

    def usage_goal(self):
        return US_W, US_HEAD + 2 * US_BAR_ROW + US_CHART_TITLE + US_CHART + US_LABELS + US_FOOT

    def draw_usage(self, cr, x0, w, h, alpha):
        left, width = x0 + US_PAD, w - 2 * US_PAD
        soft = mascot.rgba(self.ink('text', .62))[:3]
        self.put(cr, 'Consumo', prefsview.FONT_PREFS_TITLE, left, 14, mascot.rgba(self.ink('text'))[:3], alpha)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        x = left + width - lw
        over = self.over(x - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('usage', 'close', x - 4, 10, lw + 8, lh + 8))
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, US_HEAD - 8, width, 1)
        cr.fill()
        data = self.us_watch.read() if self.us_watch else None
        if not data:
            note = 'No se pudo leer el consumo.' if self.us_watch and self.us_watch.loaded else 'Leyendo el consumo…'
            self.put(cr, note, prefsview.FONT_PREFS, left + 4, US_HEAD + 8, mascot.rgba(self.ink('head'))[:3], alpha)
            self.put(cr, 'Hace falta `claudebar` y la sesión de claude abierta.', prefsview.FONT_PREFS_NOTE,
                     left + 4, US_HEAD + 28, soft, alpha, width=width)
            return
        y = US_HEAD
        for key, name, note in (('session', 'Sesión · 5 h', 'se reinicia en'), ('weekly', 'Semana', 'se reinicia en')):
            if key in data:
                self.draw_usage_bar(cr, left, y, width, name, note, data[key], soft, alpha)
            y += US_BAR_ROW
        self.draw_usage_days(cr, left, y, width, soft, alpha)
        plan = data['plan'] or 'Claude'
        models = ' · '.join(f'{name} {pct:.0f} %' for name, pct in data['models'])
        foot = f'{plan}' + (f' · semana por modelo: {models}' if models else '')
        self.put(cr, foot, prefsview.FONT_PREFS_NOTE, left, h - US_FOOT + 6, soft, alpha * .9, width=width)

    def draw_usage_bar(self, cr, x, y, w, name, note, window, soft, alpha):
        """Una ventana del plan: nombre, % a la derecha, la barra y cuánto falta para el reinicio."""
        pct, reset = window
        color = level_color(pct)
        self.put(cr, name, FONT_US_BIG, x, y, mascot.rgba(self.ink('head'))[:3], alpha)
        self.put(cr, f'{pct:.0f} %', FONT_US_BIG, x + w, y, color, alpha, align=1)
        mascot.box(cr, x, y + 22, w, 6, 3)
        cr.set_source_rgba(*themes.glow(), .12 * alpha)
        cr.fill()
        mascot.box(cr, x, y + 22, max(6, w * min(100, pct) / 100), 6, 3)
        cr.set_source_rgba(*color, .95 * alpha)
        cr.fill()
        self.put(cr, f'{note} {usage.left(reset)}', prefsview.FONT_PREFS_NOTE, x, y + 31, soft, alpha * .9)

    def draw_usage_days(self, cr, x, y, w, soft, alpha):
        """Las barras de gasto por día (puntos de la semana) de los últimos 7 días; hoy, resaltado."""
        samples = self.us_watch.samples if self.us_watch else []
        days = usage.daily(samples)
        self.put(cr, 'Gasto por día · puntos de la semana', prefsview.FONT_PREFS_NOTE, x, y + 2, soft, alpha)
        top, height = y + US_CHART_TITLE, US_CHART
        peak = max([points for _, points in days] + [5.0])           # el techo no baja de 5 puntos: no se infla un 0,2
        slot = w / len(days)
        bar = max(6, slot * .55)
        for i, (day, points) in enumerate(days):
            cx = x + slot * (i + .5)
            today = i == len(days) - 1
            fill = max(2.0, (height - 14) * points / peak) if points > 0 else 2.0
            mascot.box(cr, cx - bar / 2, top + height - fill, bar, fill, min(3, fill / 2))
            if points > 0:
                cr.set_source_rgba(*themes.hot(), (.9 if today else .5) * alpha)
            else:
                cr.set_source_rgba(*themes.glow(), .1 * alpha)
            cr.fill()
            if points > 0:
                self.put(cr, f'{points:.0f}' if points >= 1 else '<1', prefsview.FONT_PREFS_NOTE, cx,
                         top + height - fill - 14, soft, alpha, align=.5)
            tint = mascot.rgba(self.ink('head' if today else 'text', 1 if today else .62))[:3]
            self.put(cr, DAY_LETTERS[day.weekday()], prefsview.FONT_PREFS_NOTE, cx, top + height + 2, tint, alpha, align=.5)
        if not any(points for _, points in days):
            self.put(cr, 'Aún sin datos: la gráfica se llena sola con los días.', prefsview.FONT_PREFS_NOTE,
                     x + w / 2, top + height / 2 - 8, soft, alpha, width=w, align=.5)

    def on_usage_hit(self, key):
        if key == 'close':
            self.us_open = False
        self.ensure_tick()
