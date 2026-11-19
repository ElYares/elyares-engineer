"""El panel de Contenedores de la isla suelta: los proyectos de DevHerd y lo que corre en ellos.

Una fila por proyecto (cuántos contenedores van arriba, lo que gastan y «Levantar»/«Parar»);
un clic en el nombre la despliega y deja ver sus contenedores, cada uno con su ■ o ▶. Los datos
son los de `containers.Watcher` (el mismo de la ventana) y las órdenes, `window_containers`.
La vista completa (tabla, buscador, log en vivo) sigue en la ventana. Mientras docker contesta
salen filas que laten, y una orden en camino muestra un aro girando: nunca queda quieto sin decir
que trabaja.

Se abre desde el panel «Más» o con `elyares-ctl containers`. `BoxesView` es parte de la
isla (`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

import math
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')

from gi.repository import Gdk, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from . import containers, mascot, themes  # noqa: E402

BOXES_W = 520
BOXES_PAD = 16
BOXES_HEAD = 48
BOXES_ROW = 28
BOXES_FOOT = 24
BOXES_SEARCH = 30              # el renglón del buscador, entre la cabecera y las filas
BOXES_ROWS_Y = BOXES_HEAD + BOXES_SEARCH
BOXES_IDLE_SECS = 60           # sin teclear tanto rato, el buscador suelta el teclado solo
BOXES_MAX = 10                 # filas a la vista; las demás se ven en la ventana
SKELETON_ROWS = 3              # filas que laten mientras docker contesta por primera vez
PULSE_SECS = 1.3               # lo que tarda una fila en latir una vez
SPIN_SECS = 0.9                # lo que tarda el aro en dar una vuelta
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
    box_scroll = 0                 # cuántas filas se han corrido hacia arriba
    box_filter = ''                # lo escrito en el buscador, en minúsculas
    box_typing = False             # el buscador tiene el teclado
    box_keyed = 0.0
    box_entry = None
    box_css = None

    def boxes_widgets(self, overlay):
        """La caja del buscador: un Gtk.Entry de verdad encima del dibujo, que se pone en su renglón."""
        entry = Gtk.Entry()
        entry.add_css_class('elyares-boxsearch')
        entry.set_placeholder_text('Buscar proyecto o contenedor…')
        entry.set_halign(Gtk.Align.START)
        entry.set_valign(Gtk.Align.START)
        entry.set_visible(False)
        entry.connect('changed', self.on_box_search)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.on_box_key)
        entry.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect('pressed', lambda *_: self.boxes_type(True))
        entry.add_controller(click)
        overlay.add_overlay(entry)
        self.box_entry = entry
        self.box_css = Gtk.CssProvider()
        self.boxes_theme()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.box_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.connect('scroll', self.on_boxes_scroll)
        self.da.add_controller(wheel)

    def boxes_theme(self):
        """El buscador, con la tinta del tema y un velo como el de los botones."""
        if self.box_css is not None:
            ink = themes.get()['chat_ink']
            self.box_css.load_from_string(
                f'entry.elyares-boxsearch {{ color: {ink}; background: alpha({ink}, 0.08); border: none;'
                f' box-shadow: none; border-radius: 8px; min-height: 0; padding: 2px 10px;'
                f' font-family: "JetBrainsMono Nerd Font"; font-size: 9pt; }}')

    def boxes_type(self, on):
        """El buscador toma el teclado (solo cuando se le pulsa), o lo suelta."""
        self.box_typing = bool(on) and self.boxes_open
        self.box_keyed = time.monotonic()
        win = getattr(self, 'win', None)
        if win is not None:
            LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.ON_DEMAND if self.box_typing
                                         else LayerShell.KeyboardMode.NONE)
        if self.box_typing and self.box_entry is not None:
            self.box_entry.grab_focus()
        self.ensure_tick()

    def on_box_key(self, _ctrl, keyval, _code, _mods):
        self.box_keyed = time.monotonic()
        if keyval == Gdk.KEY_Escape:
            if self.box_entry.get_text():
                self.box_entry.set_text('')            # la primera vez borra lo escrito; la segunda suelta el teclado
            else:
                self.boxes_type(False)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.boxes_type(False)
            return True
        return False

    def on_box_search(self, entry):
        self.box_filter = entry.get_text().strip().lower()
        self.box_scroll = 0
        self.ensure_tick()

    def on_boxes_scroll(self, _ctrl, _dx, dy):
        """La rueda corre la lista de a una fila, sin pasarse del final."""
        if not (self.boxes_open and self.target() == 'boxes'):
            return False
        self.box_scroll = max(0, min(self.box_scroll + (1 if dy > 0 else -1), self.box_max_scroll()))
        self.ensure_tick()
        return True

    def boxes_tick(self, now):
        """Cada segundo: el buscador suelta el teclado si hace rato que no se teclea."""
        if self.box_typing and now - self.box_keyed > BOXES_IDLE_SECS:
            self.boxes_type(False)

    def boxes_place(self, h, x, width, alpha):
        """Pone el buscador de verdad sobre su renglón, y solo con el panel ya abierto."""
        entry = self.box_entry
        if entry is None:
            return
        show = self.target() == 'boxes' and h > BOXES_ROWS_Y + 20 and alpha > .6
        if show:
            if (entry.get_margin_start(), entry.get_margin_top()) != (int(x), BOXES_HEAD - 6):
                entry.set_margin_start(int(x))
                entry.set_margin_top(BOXES_HEAD - 6)
            entry.set_size_request(int(width), 24)
        if entry.get_visible() != show:
            entry.set_visible(show)
        if not show and self.box_typing:
            self.boxes_type(False)

    def boxes_away(self):
        """Si el panel ya no es lo que se ve (se pasó a Más, se cerró, la isla se escondió), el buscador
        se esconde y suelta el teclado. Se llama en cada cuadro, antes de dibujar nada."""
        entry = self.box_entry
        if entry is None or (self.boxes_open and self.target() == 'boxes' and not self.windowed):
            return
        if entry.get_visible():
            entry.set_visible(False)
        if self.box_typing:
            self.boxes_type(False)

    def toggle_boxes(self):
        """Abre o cierra el panel. En la ventana no hay: tiene su vista Contenedores."""
        if self.windowed:
            return
        self.boxes_open = not self.boxes_open
        if not self.boxes_open and self.box_typing:
            self.boxes_type(False)
        self.off = False
        if self.boxes_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.more_open = self.themes_open = self.gf_open = self.sp_open = self.sv_open = self.pm_open = False
            self.box_unfolded, self.box_pending = set(), {}
            self.box_scroll, self.box_filter = 0, ''
            if self.box_entry is not None:
                self.box_entry.set_text('')
            self.box_watch.refresh()
        self.ensure_tick()

    def boxes_busy(self):
        """¿Hay algo que animar? Docker aún no contesta, o una orden salió y no se refleja. Mientras
        sí, la isla sigue dibujando a todo cuadro aunque esté quieta."""
        if not self.boxes_open or self.windowed:
            return False
        return not self.box_watch.loaded or any(self.box_pending_for(key) for key in (self.box_pending or {}))

    def draw_spinner(self, cr, cx, cy, r, alpha):
        """Un aro con un hueco que gira; con movimiento reducido, quieto."""
        turn = 0.0 if self.motion_reduced() else (time.monotonic() % SPIN_SECS) / SPIN_SECS * 2 * math.pi
        cr.new_sub_path()
        cr.arc(cx, cy, r, turn, turn + math.pi * 1.5)
        cr.set_source_rgba(*themes.hot(), .9 * alpha)
        cr.set_line_width(1.6)
        cr.stroke()

    def draw_box_skeleton(self, cr, x, y, w, alpha):
        """Filas grises que laten (todas a la vez) mientras docker contesta la primera vez."""
        beat = 0.5 if self.motion_reduced() else 0.5 + 0.5 * math.sin(time.monotonic() % PULSE_SECS / PULSE_SECS * 2 * math.pi)
        for i in range(SKELETON_ROWS):
            ry = y + i * BOXES_ROW
            for bx, bw in ((x + 4, 14), (x + 26, w * (.34 - .06 * i)), (x + w - BTN_W, BTN_W)):
                mascot.box(cr, bx, ry + 6, bw, BOXES_ROW - 14, 6 if bw > 14 else 7)
                cr.set_source_rgba(*themes.glow(), (.05 + .09 * beat) * alpha)
                cr.fill()

    def box_rows(self):
        """Las filas a la vista: [('project', proyecto)] y, bajo los abiertos, [('box', contenedor)]."""
        data = self.box_watch.read()
        rows, find = [], self.box_filter
        for proj in (data or {}).get('projects', []):
            boxes = proj['containers']
            if find:
                # Con filtro, el proyecto sale si él o alguno de sus contenedores coincide; si coincide solo
                # un contenedor, sale abierto con los que coinciden.
                mine = find in proj['name'].lower()
                hits = [c for c in boxes if find in (c['service'] or '').lower() or find in c['name'].lower()]
                if not (mine or hits):
                    continue
                rows.append(('project', proj))
                if hits and not mine:
                    rows.extend(('box', c) for c in hits)
                elif proj['path'] in self.box_unfolded:
                    rows.extend(('box', c) for c in boxes)
                continue
            rows.append(('project', proj))
            if proj['path'] in self.box_unfolded:
                rows.extend(('box', c) for c in boxes)
        return rows

    def box_max_scroll(self):
        return max(0, len(self.box_rows()) - BOXES_MAX)

    def boxes_goal(self):
        shown = max(SKELETON_ROWS, min(len(self.box_rows()), BOXES_MAX))
        if not self.box_watch.loaded:
            shown = SKELETON_ROWS               # el esqueleto mide lo mismo que unas filas
        return BOXES_W, BOXES_ROWS_Y + shown * BOXES_ROW + BOXES_FOOT

    def draw_boxes(self, cr, x0, w, h, alpha):
        left, width = x0 + BOXES_PAD, w - 2 * BOXES_PAD
        soft = mascot.rgba(self.ink('text', .62))[:3]
        head = mascot.rgba(self.ink('head'))[:3]
        data = self.box_watch.read()
        self.put(cr, 'Contenedores', FONT_BOXES_TITLE, left, 14, mascot.rgba(self.ink('text'))[:3], alpha)
        if self.boxes_busy():
            self.draw_spinner(cr, left + 126, 22, 5, alpha)       # trabajando: docker contesta o una orden va en camino
        if data:
            tot = data['totals']
            self.put(cr, f'{tot["up"]}/{tot["total"]} arriba · CPU {tot["cpu"]:.0f} % · {containers.fmt_bytes(tot["mem"])}',
                     FONT_BOXES_NOTE,
                     left + 140, 18, soft, alpha, width=width - 218)
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
        if not self.box_watch.loaded:
            self.draw_box_skeleton(cr, left, BOXES_ROWS_Y, width, alpha)
            self.put(cr, 'Preguntando a docker…', FONT_BOXES_NOTE, left + 4, h - BOXES_FOOT + 6, soft, alpha * .9)
        elif not rows:
            note = ('Docker no contesta.' if data is None else
                    f'Nada coincide con «{self.box_filter}».' if self.box_filter else 'Ningún proyecto de DevHerd.')
            self.put(cr, note, FONT_BOXES, left + 4, BOXES_ROWS_Y + 4, soft, alpha)
        self.box_scroll = max(0, min(self.box_scroll, max(0, len(rows) - BOXES_MAX)))
        for i, (kind, item) in enumerate(rows[self.box_scroll:self.box_scroll + BOXES_MAX]):
            y = BOXES_ROWS_Y + i * BOXES_ROW
            if kind == 'project':
                self.draw_box_project(cr, item, left, y, width, head, soft, alpha)
            else:
                self.draw_box_container(cr, item, left, y, width, head, soft, alpha)
        if len(rows) > BOXES_MAX:
            first = self.box_scroll + 1
            self.put(cr, f'{first}–{min(first + BOXES_MAX - 1, len(rows))} de {len(rows)} · rueda del ratón para ver más',
                     FONT_BOXES_NOTE, left, h - BOXES_FOOT + 6, soft, alpha * .9, width=width)
            # La barra de avance, a la derecha de las filas.
            track = BOXES_MAX * BOXES_ROW
            thumb = max(14, track * BOXES_MAX / len(rows))
            mascot.box(cr, left + width + 6, BOXES_ROWS_Y + (track - thumb) * self.box_scroll / (len(rows) - BOXES_MAX),
                       3, thumb, 1.5)
            cr.set_source_rgba(*themes.glow(), .35 * alpha)
            cr.fill()
        self.boxes_place(h, left, width, alpha)

    def box_pending_for(self, key):
        """¿Salió esa orden hace poco y docker todavía no la refleja?"""
        return time.monotonic() - self.box_pending.get(key, -PENDING_SECS) < PENDING_SECS

    def draw_box_button(self, cr, label, x, y, w, key, alpha, pending):
        over = not pending and self.over(x, y, w, BOXES_ROW - 6)
        mascot.box(cr, x, y, w, BOXES_ROW - 6, 8)
        cr.set_source_rgba(*themes.glow(), (.18 if over else .09) * alpha)
        cr.fill()
        if pending:
            self.draw_spinner(cr, x + w / 2, y + (BOXES_ROW - 6) / 2, 5, alpha)       # la orden va en camino
        else:
            self.put(cr, label, FONT_BOXES_NOTE, x + w / 2, y + 4, mascot.rgba(self.ink('head'))[:3], alpha, align=.5)
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
