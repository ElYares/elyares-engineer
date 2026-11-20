"""El panel de Servidores de la isla suelta: tus `Host` de ssh, y un clic abre uno en Ghostty.

Se abre desde «Más → Servidores» o con `elyares-ctl servers`. La lista sale de `~/.ssh/config`
(`servers.py`), que se vuelve a leer cada vez que se abre el panel. No es una terminal: abre la
de siempre ya conectada. `ServersView` es parte de la isla (`app.Island` la hereda).
"""

from . import mascot, prefsview, servers, themes

SV_W = prefsview.PREFS_W
SV_ROWS_MIN = 2                          # el panel no baja de esto aunque haya uno o ningún servidor


class ServersView:
    """Lo que guarda: `sv_open` (el panel está a la vista), `sv_hosts` (los alias) y `sv_msg` (el último aviso)."""

    sv_open = False
    sv_hosts = ()
    sv_msg = ''

    def toggle_servers(self):
        """Abre o cierra el panel. En la ventana no hay."""
        if self.windowed:
            return
        self.sv_open = not self.sv_open
        self.off = False
        if self.sv_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.more_open = self.boxes_open = False
            self.themes_open = self.gf_open = self.sp_open = self.pm_open = False
            self.sv_hosts, self.sv_msg = tuple(servers.hosts()[:servers.MAX]), ''
        self.ensure_tick()

    def servers_goal(self):
        rows = max(SV_ROWS_MIN, len(self.sv_hosts))
        return SV_W, prefsview.PREFS_HEAD + rows * prefsview.PREFS_ROW + prefsview.PREFS_FOOT

    def draw_servers(self, cr, x0, w, h, alpha):
        pad, row = prefsview.PREFS_PAD, prefsview.PREFS_ROW
        left, width = x0 + pad, w - 2 * pad
        soft = mascot.rgba(self.ink('text', .62))[:3]
        self.put(cr, 'Servidores', prefsview.FONT_PREFS_TITLE, left, 14, mascot.rgba(self.ink('text'))[:3], alpha)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        x = left + width - lw
        over = self.over(x - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('servers', 'close', x - 4, 10, lw + 8, lh + 8))
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, prefsview.PREFS_HEAD - 8, width, 1)
        cr.fill()
        if not self.sv_hosts:
            self.put(cr, 'No hay servidores en ~/.ssh/config.', prefsview.FONT_PREFS, left + 4,
                     prefsview.PREFS_HEAD + 4, soft, alpha)
        for i, alias in enumerate(self.sv_hosts):
            self.draw_server_row(cr, alias, left, prefsview.PREFS_HEAD + i * row, width, soft, alpha)
        note = self.sv_msg or 'Un clic lo abre en Ghostty con ssh.'
        self.put(cr, note, prefsview.FONT_PREFS_NOTE, left, h - prefsview.PREFS_FOOT + 6, soft, alpha * .9, width=width)

    def draw_server_row(self, cr, alias, x, y, w, soft, alpha):
        """Un servidor: su alias y «›» a la derecha. Todo el renglón es un clic."""
        row = prefsview.PREFS_ROW
        if self.over(x - 4, y, w + 8, row):
            mascot.box(cr, x - 4, y, w + 8, row, 6)
            cr.set_source_rgba(*themes.glow(), .08 * alpha)
            cr.fill()
        self.put(cr, alias, prefsview.FONT_PREFS, x + 4, y + 7, mascot.rgba(self.ink('head'))[:3], alpha, width=w - 60)
        self.put(cr, '›', prefsview.FONT_PREFS_TITLE, x + w - 14, y + 4, soft, alpha)
        self.hits.append(('servers', alias, x - 4, y, w + 8, row))

    def on_servers_hit(self, key):
        """Un clic: cerrar, o abrir ese servidor. El alias tiene que seguir en la lista de `~/.ssh/config`."""
        if key == 'close':
            self.sv_open = False
        elif key in self.sv_hosts:
            self.sv_msg = f'Abriendo {key} en Ghostty…' if servers.connect(key) else f'No se pudo abrir {key}.'
        self.ensure_tick()
