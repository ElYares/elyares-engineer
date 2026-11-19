"""El panel de Contenedores de la isla suelta: los proyectos de DevHerd y lo que corre en ellos.

Una fila por proyecto (cuántos contenedores van arriba, lo que gastan y «Levantar»/«Parar»);
un clic en el nombre la despliega y deja ver sus contenedores, cada uno con su ■ o ▶. Los datos
son los de `containers.Watcher` (el mismo de la ventana) y las órdenes, `window_containers`.
La vista completa (tabla, buscador, log en vivo) sigue en la ventana.

Se abre con la pastilla ▣ del pie o con `elyares-ctl containers`. `BoxesView` es parte de la
isla (`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

import time

from . import containers, mascot, themes

BOXES_W = 520
BOXES_PAD = 16
BOXES_HEAD = 48
BOXES_ROW = 28
BOXES_FOOT = 24
BOXES_MAX = 10                 # filas a la vista; las demás se ven en la ventana
BOXES_PILL = 'boxes'           # la pastilla ▣ del pie
BTN_W = 78
PENDING_SECS = 6               # cuánto se queda el «…» tras una orden, hasta que docker conteste
FONT_BOXES = 'Sans Medium 9'
FONT_BOXES_NOTE = 'JetBrainsMono Nerd Font 8'
FONT_BOXES_TITLE = 'Sans Semi-Bold 11'


class BoxesView:
    """Lo que guarda: `boxes_open` (el panel está a la vista), `box_unfolded` (rutas de los
    proyectos abiertos) y `box_pending` (órdenes salidas que docker aún no refleja)."""

    boxes_open = False
    box_unfolded = None
    box_pending = None

    def toggle_boxes(self):
        """Abre o cierra el panel. En la ventana no hay: tiene su vista Contenedores."""
        if self.windowed:
            return
        self.boxes_open = not self.boxes_open
        self.off = False
        if self.boxes_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.home_open = self.tasks_open = False
            self.box_unfolded, self.box_pending = set(), {}
            self.box_watch.refresh()
        self.ensure_tick()

    def box_rows(self):
        """Las filas a la vista: [('project', proyecto)] y, bajo los abiertos, [('box', contenedor)]."""
        data = self.box_watch.read()
        rows = []
        for proj in (data or {}).get('projects', []):
            rows.append(('project', proj))
            if proj['path'] in self.box_unfolded:
                rows.extend(('box', c) for c in proj['containers'])
        return rows

    def boxes_goal(self):
        shown = max(1, min(len(self.box_rows()), BOXES_MAX))
        return BOXES_W, BOXES_HEAD + shown * BOXES_ROW + BOXES_FOOT

    def draw_boxes(self, cr, x0, w, h, alpha):
        left, width = x0 + BOXES_PAD, w - 2 * BOXES_PAD
        soft = mascot.rgba(self.ink('text', .62))[:3]
        head = mascot.rgba(self.ink('head'))[:3]
        data = self.box_watch.read()
        self.put(cr, 'Contenedores', FONT_BOXES_TITLE, left, 14, themes.tuple_of(themes.get()['ink']), alpha)
        if data:
            tot = data['totals']
            self.put(cr, f'{tot["up"]}/{tot["total"]} arriba · CPU {tot["cpu"]:.0f} % · {containers.fmt_bytes(tot["mem"])}',
                     FONT_BOXES_NOTE,
                     left + 112, 18, soft, alpha, width=width - 190)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        x = left + width - lw
        over = self.over(x - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('boxes', ('close',), x - 4, 10, lw + 8, lh + 8))
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, BOXES_HEAD - 8, width, 1)
        cr.fill()
        rows = self.box_rows()
        if not rows:
            note = ('Docker no contesta.' if self.box_watch.loaded and data is None else
                    'Ningún proyecto de DevHerd.' if data else 'Preguntando a docker…')
            self.put(cr, note, FONT_BOXES, left + 4, BOXES_HEAD + 4, soft, alpha)
        for i, (kind, item) in enumerate(rows[:BOXES_MAX]):
            y = BOXES_HEAD + i * BOXES_ROW
            if kind == 'project':
                self.draw_box_project(cr, item, left, y, width, head, soft, alpha)
            else:
                self.draw_box_container(cr, item, left, y, width, head, soft, alpha)
        if len(rows) > BOXES_MAX:
            self.put(cr, f'+{len(rows) - BOXES_MAX} más en la ventana (elyares-ctl window)', FONT_BOXES_NOTE,
                     left, h - BOXES_FOOT + 6, soft, alpha * .9, width=width)

    def box_pending_for(self, key):
        """¿Salió esa orden hace poco y docker todavía no la refleja?"""
        return time.monotonic() - self.box_pending.get(key, -PENDING_SECS) < PENDING_SECS

    def draw_box_button(self, cr, label, x, y, w, key, alpha, pending):
        over = not pending and self.over(x, y, w, BOXES_ROW - 6)
        mascot.box(cr, x, y, w, BOXES_ROW - 6, 8)
        cr.set_source_rgba(*themes.glow(), (.18 if over else .09) * alpha)
        cr.fill()
        self.put(cr, '…' if pending else label, FONT_BOXES_NOTE, x + w / 2, y + 4,
                 mascot.rgba(self.ink('head'))[:3], alpha, align=.5)
        if not pending:
            self.hits.append(('boxes', key, x, y, w, BOXES_ROW - 6))

    def draw_box_project(self, cr, proj, x, y, w, head, soft, alpha):
        """Un proyecto: su nombre (un clic lo despliega), n/m arriba, lo que gasta y su botón."""
        path, up, total = proj['path'], proj['running'], proj['total']
        if self.over(x - 4, y, w - BTN_W - 8, BOXES_ROW):
            mascot.box(cr, x - 4, y, w - BTN_W - 4, BOXES_ROW - 2, 6)
            cr.set_source_rgba(*themes.glow(), .08 * alpha)
            cr.fill()
        color = 'green' if total and up == total else 'yellow' if up else 'metal'
        cr.new_sub_path()
        cr.arc(x + 14, y + BOXES_ROW / 2 - 1, 3.5, 0, 6.2832)
        cr.set_source_rgba(*mascot.rgba(color, alpha * (1 if up else .6)))
        cr.fill()
        self.put(cr, '▾' if path in self.box_unfolded else '▸', FONT_BOXES, x + 2, y + 4, soft, alpha)
        self.put(cr, proj['name'], FONT_BOXES, x + 26, y + 4, head, alpha, width=w - BTN_W - 190)
        self.put(cr, f'{up}/{total}', FONT_BOXES_NOTE, x + w - BTN_W - 128, y + 6, soft, alpha, align=1)
        if up:
            self.put(cr, f'{proj["cpu"]:.0f} % · {containers.fmt_bytes(proj["mem"])}', FONT_BOXES_NOTE,
                     x + w - BTN_W - 8, y + 6, soft, alpha * .9, align=1)
        order = 'stop-project' if up else 'up'
        self.draw_box_button(cr, '■ Parar' if up else '▶ Levantar', x + w - BTN_W, y, BTN_W, ('act', order, path),
                             alpha, self.box_pending_for((order, path)))
        self.hits.append(('boxes', ('fold', path), x - 4, y, w - BTN_W - 8, BOXES_ROW))

    def draw_box_container(self, cr, box, x, y, w, head, soft, alpha):
        up = box['state'] == 'running'
        cr.new_sub_path()
        cr.arc(x + 34, y + BOXES_ROW / 2 - 1, 3, 0, 6.2832)
        cr.set_source_rgba(*mascot.rgba('green' if up else 'metal', alpha * (1 if up else .6)))
        cr.fill()
        self.put(cr, box['service'] or box['name'], FONT_BOXES_NOTE, x + 46, y + 6, head if up else soft, alpha,
                 width=w - BTN_W - 200)
        if up and 'cpu' in box:
            self.put(cr, f'{box["cpu"]:.0f} % · {containers.fmt_bytes(box.get("mem", 0))}', FONT_BOXES_NOTE,
                     x + w - 36, y + 6, soft, alpha * .9, align=1)
        order = 'stop' if up else 'start'
        self.draw_box_button(cr, '■' if up else '▶', x + w - 28, y, 28, ('act', order, box['name']), alpha,
                             self.box_pending_for((order, box['name'])))

    def on_boxes_hit(self, key):
        """Un clic en el panel: cerrar, desplegar un proyecto o mandar una orden a docker."""
        if key[0] == 'close':
            self.boxes_open = False
        elif key[0] == 'fold':
            self.box_unfolded ^= {key[1]}
        elif key[0] == 'act':
            self.box_pending[(key[1], key[2])] = time.monotonic()
            self.window_containers(key[1], key[2])
        self.ensure_tick()
