"""La vista Contenedores: los proyectos de DevHerd con sus contenedores, arriba o caídos.

Una tarjeta por proyecto (con «Levantar todo» y «Parar todo») y una fila por contenedor
(estado, CPU, memoria, «Parar» o «Iniciar»). Al elegir uno, a la derecha salen sus recursos y
su log en vivo. Arriba, lo que gastan todos juntos. Sin estado de Docker propio: la llena la ventana
(`set_data`) y los botones llaman a los `handlers`.
"""

import gi

gi.require_version('Gtk', '4.0')

import os
import math
import re
import time

from gi.repository import Gdk, GLib, Gtk, Pango

from . import containers
from .windowframe import SPACE

LIST_W = 470
GREEN, GREY, RED, AMBER = '#4ade80', '#8f9ab8', '#ff6b6b', '#f5c542'
CORES = os.cpu_count() or 1
PULSE_SECS = 1.3          # lo que tarda el esqueleto en latir una vez
RESULT_SECS = 8            # cuánto se queda a la vista «Levantado» o el error de una orden
WORDS = {'up': 'Levantando', 'stop-project': 'Parando', 'stop': 'Parando', 'start': 'Iniciando'}
DONE = {'up': 'Levantado', 'stop-project': 'Parado', 'stop': 'Parado', 'start': 'Iniciado'}
HOT_CPU, WARM_CPU = 80.0, 50.0           # % de un núcleo
BIG_MEM = 1024 ** 3                       # un contenedor de más de 1 GB se marca
# Líneas de log que merecen color: lo primero que coincida manda.
LOG_TONES = ((re.compile(r'\b(error|fatal|panic|exception|critical|traceback)\b', re.I), RED),
             (re.compile(r'\b(warn|warning)\b', re.I), AMBER))

# Con alpha() sobre el color del texto: sirve igual en los temas oscuros y en los claros.
CSS = f"""
.cbox-row {{ border-radius: 6px; padding: 2px 4px; }}
.cbox-row:hover {{ background: alpha(currentColor, 0.07); }}
.cbox-row.picked {{ background: alpha({GREEN}, 0.14); }}
.cbox-flat {{ background: none; border: none; box-shadow: none; padding: 4px 6px; min-height: 0; }}
.cbox-flat:hover {{ background: none; }}
.cbox-card {{ border-left: 3px solid {GREY}; }}
.cbox-card.all {{ border-left-color: {GREEN}; }}
.cbox-card.part {{ border-left-color: {AMBER}; }}
.cbox-badge {{ border-radius: 99px; padding: 0 8px; font-size: 11px; font-weight: 700;
              background: alpha({GREY}, 0.2); color: {GREY}; }}
.cbox-badge.all {{ background: alpha({GREEN}, 0.18); color: {GREEN}; }}
.cbox-badge.part {{ background: alpha({AMBER}, 0.18); color: {AMBER}; }}
.cbox-num {{ font-feature-settings: "tnum"; }}
.cbox-num.warm {{ color: {AMBER}; }}
.cbox-num.hot {{ color: {RED}; }}
.cbox-tile {{ background: alpha(currentColor, 0.06); border-radius: 8px; padding: 8px 12px; }}
.cbox-big {{ font-size: 22px; font-weight: 700; }}
.cbox-bar trough {{ min-height: 5px; border-radius: 99px; background: alpha(currentColor, 0.12); }}
.cbox-bar progress {{ min-height: 5px; border-radius: 99px; background: {GREEN}; }}
.cbox-bar.warm progress {{ background: {AMBER}; }}
.cbox-bar.hot progress {{ background: {RED}; }}
.cbox-job {{ border-radius: 6px; padding: 6px 8px; background: alpha({AMBER}, 0.14); }}
.cbox-job.ok {{ background: alpha({GREEN}, 0.16); }}
.cbox-job.bad {{ background: alpha({RED}, 0.18); }}
.cbox-skel {{ background: rgba(128, 128, 128, 0.28); border-radius: 6px; color: transparent; }}
.cbox-logs {{ background: alpha(black, 0.35); border-radius: 8px; font-size: 12px; }}
.cbox-logs text {{ background: none; }}
"""
_css = None


def load_css():
    global _css
    if _css is None:
        _css = Gtk.CssProvider()
        _css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), _css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)


CLEAN_EXITS = ('Exited (0)', 'Exited (137)', 'Exited (143)')     # los que paró alguien: no son una caída


def dot(box):
    """El punto de un contenedor: verde arriba, rojo si se cayó con error o no está sano, gris si solo está parado."""
    if box['state'] == 'running':
        return RED if box.get('health') == 'unhealthy' else GREEN
    if box['state'] in ('created', 'restarting'):
        return AMBER
    return RED if box['state'] == 'exited' and not box['status'].startswith(CLEAN_EXITS) else GREY


def _button(text, tip, call, danger=False):
    btn = Gtk.Button(label=text)
    btn.add_css_class('elyares-btn')
    btn.add_css_class('compact')
    btn.set_tooltip_text(tip)
    btn.update_property([Gtk.AccessibleProperty.LABEL], [tip])
    btn.connect('clicked', lambda _b: call())
    return btn


def level(fraction):
    """'' | 'warm' | 'hot' según qué tan lleno está algo (0 a 1)."""
    return 'hot' if fraction >= 0.8 else 'warm' if fraction >= 0.5 else ''


def _num(width):
    label = Gtk.Label(xalign=1, width_chars=width)
    label.add_css_class('cbox-num')
    return label


def _tone(label, tone):
    for cls in ('warm', 'hot'):
        label.remove_css_class(cls)
    if tone:
        label.add_css_class(tone)


def _bar(fraction=0.0, tone=''):
    bar = Gtk.ProgressBar()
    bar.add_css_class('cbox-bar')
    set_bar(bar, fraction, tone)
    return bar


def set_bar(bar, fraction, tone):
    bar.set_fraction(max(0.0, min(1.0, fraction)))
    for cls in ('warm', 'hot'):
        bar.remove_css_class(cls)
    if tone:
        bar.add_css_class(tone)


def _tile(title):
    """Un recuadro con título, cifra grande, barra y una línea de detalle: (caja, cifra, barra, detalle)."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    box.add_css_class('cbox-tile')
    head = Gtk.Label(label=title, xalign=0)
    head.add_css_class('elyares-section')
    big = Gtk.Label(xalign=0)
    big.add_css_class('cbox-big')
    bar = _bar()
    note = Gtk.Label(xalign=0)
    note.add_css_class('dim-label')
    for w in (head, big, bar, note):
        box.append(w)
    return box, big, bar, note


class ContainersPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        load_css()
        self.add_css_class('elyares-sources')
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self, f'set_margin_{side}')(SPACE[2])
        self.handlers = {}
        self.only_down = False
        self.picked = ''            # nombre del contenedor elegido
        self.sig = None
        self.skeleton = []          # lo que late mientras carga: bloques sueltos, textos y barras
        self.pulse_id = 0
        self.jobs = {}              # (orden, destino) → lo que va de una orden en curso o recién acabada
        self.cards = {}             # carpeta del proyecto → su franja de avance
        self.rows = {}              # nombre → (fila, cpu, memoria): el consumo se pone sin rehacer la lista
        self.tail = None
        self.tail_stamp = -1
        self.data = None

        # Arriba: lo que gastan todos juntos y el filtro.
        up_tile, self.up_big, self.up_bar, self.up_note = _tile('ARRIBA')
        cpu_tile, self.cpu_big, self.cpu_bar, self.cpu_note = _tile('CPU')
        mem_tile, self.mem_big, self.mem_bar, self.mem_note = _tile('MEMORIA')
        tiles = Gtk.Box(spacing=SPACE[1], homogeneous=True)
        for tile in (up_tile, cpu_tile, mem_tile):
            tiles.append(tile)
        self.filter_btn = Gtk.ToggleButton(label='Solo caídos')
        self.filter_btn.add_css_class('elyares-btn')
        self.filter_btn.set_valign(Gtk.Align.START)
        self.filter_btn.connect('toggled', self._filter)
        top = Gtk.Box(spacing=SPACE[1])
        tiles.set_hexpand(True)
        top.append(tiles)
        top.append(self.filter_btn)
        self.append(top)

        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        scroll = self.list_scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.page)
        scroll.set_size_request(LIST_W, -1)
        scroll.set_vexpand(True)
        scroll.set_min_content_height(200)

        # A la derecha: el contenedor elegido, con su consumo y su log.
        self.detail_head = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.detail_head.add_css_class('title-3')
        self.detail_note = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.detail_note.add_css_class('dim-label')
        d_cpu, self.d_cpu_big, self.d_cpu_bar, self.d_cpu_note = _tile('CPU')
        d_mem, self.d_mem_big, self.d_mem_bar, self.d_mem_note = _tile('MEMORIA')
        d_net, self.d_net_big, self.d_net_bar, self.d_net_note = _tile('RED')
        self.d_net_bar.set_visible(False)
        self.d_tiles = Gtk.Box(spacing=SPACE[1], homogeneous=True)
        for tile in (d_cpu, d_mem, d_net):
            self.d_tiles.append(tile)
        logs_title = Gtk.Label(label='LOG', xalign=0)
        logs_title.add_css_class('elyares-section')
        self.logs = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.logs.add_css_class('cbox-logs')
        for margin in ('left', 'right', 'top', 'bottom'):
            getattr(self.logs, f'set_{margin}_margin')(SPACE[1])
        buf = self.logs.get_buffer()
        self.tags = {color: buf.create_tag(None, foreground=color) for _rx, color in LOG_TONES}
        self.log_scroll = Gtk.ScrolledWindow()
        self.log_scroll.set_vexpand(True)
        self.log_scroll.set_child(self.logs)
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        self.detail.set_margin_start(SPACE[1])
        for w in (self.detail_head, self.detail_note, self.d_tiles, logs_title, self.log_scroll):
            self.detail.append(w)
        self.empty = Gtk.Label(label='Elige un contenedor para ver su consumo y su log.', xalign=0.5, yalign=0.4,
                               vexpand=True, hexpand=True)
        self.empty.add_css_class('dim-label')
        stack = Gtk.Overlay()
        stack.set_child(self.detail)
        stack.add_overlay(self.empty)

        body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_start_child(scroll)
        body.set_end_child(stack)
        body.set_position(LIST_W)
        body.set_resize_start_child(False)
        body.set_shrink_start_child(False)
        body.set_shrink_end_child(False)
        body.set_vexpand(True)
        self.append(body)
        self._pick('')
        self.set_visible(False)

    def _start(self, order, target):
        """Un botón de acción: deja ver de inmediato que la orden salió y le da al hilo con qué avisar."""
        key = (order, target)
        if key in self.jobs and not self.jobs[key]['done']:
            return
        job = self.jobs[key] = dict(at=time.monotonic(), line='', done=False, ok=None, said='', until=0.0)
        self.sig = None
        self.handlers['act'](order, target,
                             lambda line: GLib.idle_add(self._line, job, line),
                             lambda ok, said: GLib.idle_add(self._done, job, ok, said))
        if self.data is not None:
            self.set_data(self.data, self.handlers)

    @staticmethod
    def _line(job, line):
        job['line'] = line

    def _done(self, job, ok, said):
        job.update(done=True, ok=ok, said=said, until=time.monotonic() + RESULT_SECS,
                   took=time.monotonic() - job['at'])
        self.sig = None

    def _jobs_tick(self):
        """Pone al día los segundos de las órdenes en curso y quita las ya vistas."""
        now = time.monotonic()
        for key in [k for k, j in self.jobs.items() if j['done'] and j['until'] < now]:
            del self.jobs[key]
            self.sig = None
        for key, job in self.jobs.items():
            card = self.cards.get(key[1])
            if card is None or job['done']:
                continue
            box, spin, label, bar = card
            seconds = int(now - job['at'])
            tail = f' · {job["line"]}' if job['line'] else ''
            label.set_text(f'{WORDS[key[0]]}… {seconds} s{tail}')
            bar.pulse()

    def _block(self, width, height):
        block = Gtk.Box()
        block.add_css_class('cbox-skel')
        block.set_size_request(width, height)
        self.skeleton.append(block)
        return block

    def _show_skeleton(self):
        """Antes de la primera respuesta: tres recuadros y varias tarjetas grises que laten, con la forma
        de lo que va a llegar. Se pone una sola vez."""
        if self.sig == 'skeleton':
            return
        self.sig = 'skeleton'
        self.skeleton = []
        self.filter_btn.set_sensitive(False)
        for big, note, bar in ((self.up_big, self.up_note, self.up_bar), (self.cpu_big, self.cpu_note, self.cpu_bar),
                               (self.mem_big, self.mem_note, self.mem_bar)):
            big.set_text('0000')
            note.set_text('cargando…')
            set_bar(bar, 0.0, '')
            for label in (big, note):
                label.add_css_class('cbox-skel')
                self.skeleton.append(label)
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        for rows, widths in ((6, (90, 140, 110, 160, 120, 100)), (3, (130, 100, 150)), (4, (110, 150, 90, 130))):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
            card.add_css_class('elyares-card')
            card.add_css_class('cbox-card')
            head = Gtk.Box(spacing=SPACE[1])
            head.append(self._block(150, 18))
            head.append(self._block(36, 18))
            card.append(head)
            for i in range(rows):
                row = Gtk.Box(spacing=SPACE[1])
                row.set_margin_end(SPACE[0])
                row.append(self._block(10, 10))
                row.append(self._block(widths[i % len(widths)], 14))
                spacer = Gtk.Box(hexpand=True)
                row.append(spacer)
                row.append(self._block(44, 14))
                row.append(self._block(60, 14))
                row.append(self._block(26, 26))
                card.append(row)
            self.page.append(card)
        self.empty.set_label('Cargando contenedores…')
        if not self.pulse_id:
            self.pulse_id = GLib.timeout_add(50, self._pulse)

    def _pulse(self):
        """El latido: la opacidad de lo gris sube y baja. Se apaga sola al salir del esqueleto."""
        if self.sig != 'skeleton':
            self.pulse_id = 0
            return GLib.SOURCE_REMOVE
        level = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(time.monotonic() * 2 * math.pi / PULSE_SECS))
        for widget in self.skeleton:
            widget.set_opacity(level)
        return GLib.SOURCE_CONTINUE

    def _hide_skeleton(self):
        if self.sig != 'skeleton':
            return
        self.sig = None                 # fuerza rehacer la lista con lo de verdad
        self.filter_btn.set_sensitive(True)
        for widget in self.skeleton:
            widget.set_opacity(1.0)
            widget.remove_css_class('cbox-skel')
        self.skeleton = []
        self.empty.set_label('Elige un contenedor para ver su consumo y su log.')

    def _filter(self, btn):
        self.only_down = btn.get_active()
        self.sig = None
        if self.data is not None:
            self.set_data(self.data, self.handlers)

    def set_data(self, data, handlers, loading=False):
        """`data`: lo que da `containers.snapshot()` (None si docker no contesta). `loading`: docker aún no
        ha contestado ni una vez: se muestra un esqueleto que late. Rehace la lista solo si cambió la
        estructura; el consumo se pone en su sitio."""
        self.handlers, self.data = handlers, data
        if loading and data is None:
            self._show_skeleton()
            return
        self._hide_skeleton()
        if data is None:
            for big, note in ((self.up_big, self.up_note), (self.cpu_big, self.cpu_note), (self.mem_big, self.mem_note)):
                big.set_text('—')
                note.set_text('')
            self.up_note.set_text('Docker no contesta (¿está corriendo?)')
            if self.sig != 'down':
                self.sig = 'down'
                self._rebuild([])
            return
        self._summary(data['totals'])
        projects = [p for p in data['projects'] if not self.only_down or p['running'] < max(p['total'], 1)]
        sig = repr([sorted((k, j['done']) for k, j in self.jobs.items()), [(p['path'], [(c['name'], c['state'], c.get('health'))
                                 for c in p['containers']]) for p in projects]])
        if sig != self.sig:
            self.sig = sig
            self._rebuild(projects)
        for box in (c for p in data['projects'] for c in p['containers']):
            if box['name'] in self.rows:
                self._usage(box)
        self._jobs_tick()
        self._detail()

    def _summary(self, tot):
        self.up_big.set_markup(f'{tot["up"]}<span size="small" alpha="60%"> de {tot["total"]}</span>')
        set_bar(self.up_bar, tot['up'] / tot['total'] if tot['total'] else 0, '')
        self.up_note.set_text(f'{tot["total"] - tot["up"]} parados')
        cpu = tot['cpu'] / (CORES * 100)
        self.cpu_big.set_text(f'{tot["cpu"]:.1f}%')
        set_bar(self.cpu_bar, cpu, level(cpu))
        self.cpu_note.set_text(f'de {CORES} núcleos')
        host = tot['host_mem']
        mem = tot['mem'] / host if host else 0
        self.mem_big.set_text(containers.fmt_bytes(tot['mem']))
        set_bar(self.mem_bar, mem, level(mem))
        self.mem_note.set_text(f'{mem * 100:.0f}% de {containers.fmt_bytes(host)}' if host else '')

    def _usage(self, box):
        _row, cpu, mem = self.rows[box['name']]
        live = box['state'] == 'running' and 'cpu' in box
        cpu.set_text(f'{box["cpu"]:.1f}%' if live else '')
        mem.set_text(containers.fmt_bytes(box['mem']) if live else '')
        _tone(cpu, 'hot' if live and box['cpu'] >= HOT_CPU else 'warm' if live and box['cpu'] >= WARM_CPU else '')
        _tone(mem, 'warm' if live and box['mem'] >= BIG_MEM else '')

    def _rebuild(self, projects):
        adj = self.list_scroll.get_vadjustment()
        keep = adj.get_value()
        self.rows, self.cards = {}, {}
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        if not projects:
            note = Gtk.Label(label='Todo está arriba.' if self.only_down else 'Sin datos todavía: se vuelve a intentar solo.' if self.data is None else 'No hay proyectos de DevHerd.',
                             xalign=0)
            note.add_css_class('dim-label')
            self.page.append(note)
        for proj in projects:
            self.page.append(self._card(proj))
        GLib.idle_add(adj.set_value, keep)      # rehacer la lista no devuelve el scroll arriba

    def _card(self, proj):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        card.add_css_class('elyares-card')
        card.add_css_class('cbox-card')
        tone = 'all' if proj['total'] and proj['running'] == proj['total'] else 'part' if proj['running'] else ''
        if tone:
            card.add_css_class(tone)
        title = Gtk.Label(label=proj['name'], xalign=0, ellipsize=Pango.EllipsizeMode.END)
        title.add_css_class('heading')
        badge = Gtk.Label(label=f'{proj["running"]}/{proj["total"]}' if proj['total'] else 'sin contenedores')
        badge.add_css_class('cbox-badge')
        if tone:
            badge.add_css_class(tone)
        spacer = Gtk.Box(hexpand=True)
        row = Gtk.Box(spacing=SPACE[1])
        for w in (title, badge, spacer):
            row.append(w)
        buttons = []
        if proj['path']:
            if proj['running'] < proj['total'] or not proj['total']:
                up = _button('▶ Levantar todo', f'Levantar {proj["name"]} con devherd up',
                             lambda p=proj['path']: self._start('up', p))
                up.add_css_class('primary')
                row.append(up)
                buttons.append(up)
            if proj['running']:
                stop = _button('■ Parar todo', f'Parar todo {proj["name"]} con devherd stop',
                               lambda p=proj['path']: self._start('stop-project', p))
                row.append(stop)
                buttons.append(stop)
        busy = self._project_job(proj['path'])
        for btn in buttons:
            btn.set_sensitive(busy is None)
        card.append(row)
        card.append(self._strip(proj['path'], busy))
        for box in proj['containers']:
            card.append(self._row(box))
        return card

    def _project_job(self, path):
        """La orden de proyecto que corre o acaba de acabar en esa carpeta, o None."""
        return next((j for (order, target), j in self.jobs.items()
                     if target == path and order in ('up', 'stop-project')), None)

    def _strip(self, path, job):
        """La franja bajo el título: «Levantando… 12 s», o cómo acabó. Oculta si no hay orden."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        box.add_css_class('cbox-job')
        spin = Gtk.Spinner()
        label = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        line = Gtk.Box(spacing=SPACE[1])
        line.append(spin)
        line.append(label)
        bar = Gtk.ProgressBar()
        bar.add_css_class('cbox-bar')
        box.append(line)
        box.append(bar)
        box.set_visible(job is not None)
        if job is not None:
            order = next(o for (o, t), j in self.jobs.items() if j is job)
            if not job['done']:
                spin.start()
            elif job['ok']:
                box.add_css_class('ok')
                label.set_text(f'✓ {DONE[order]} en {job["took"]:.0f} s')
                spin.set_visible(False)
                bar.set_visible(False)
            else:
                box.add_css_class('bad')
                label.set_text('✗ Falló: ' + (job['said'].splitlines() or ['sin detalle'])[-1])
                label.set_tooltip_text(job['said'])
                spin.set_visible(False)
                bar.set_visible(False)
        self.cards[path] = (box, spin, label, bar)
        return box

    def _row(self, box):
        up = box['state'] == 'running'
        row = Gtk.Box(spacing=SPACE[1])
        row.add_css_class('cbox-row')
        if box['name'] == self.picked:
            row.add_css_class('picked')
        pick = Gtk.Button()
        pick.add_css_class('cbox-flat')
        pick.set_hexpand(True)
        label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        extra = ''
        if box.get('health') == 'unhealthy':
            extra = '  <span foreground="%s">no sano</span>' % RED
        elif not up:
            extra = f'  <span alpha="55%" size="small">{GLib.markup_escape_text(box["status"])}</span>'
        label.set_markup(f'<span foreground="{dot(box)}">●</span>  '
                         f'{GLib.markup_escape_text(box["service"] or box["name"])}{extra}')
        pick.set_child(label)
        pick.connect('clicked', lambda _b, n=box['name']: self._pick(n))
        cpu, mem = _num(6), _num(8)
        cpu.set_visible(up)         # parado: su estado ocupa ese sitio
        mem.set_visible(up)
        self.rows[box['name']] = (row, cpu, mem)
        for w in (pick, cpu, mem):
            row.append(w)
        job = self.jobs.get(('stop' if up else 'start', box['name'])) or self.jobs.get(('start' if up else 'stop', box['name']))
        if job is not None and not job['done']:
            spin = Gtk.Spinner()
            spin.start()
            spin.set_tooltip_text('Esperando a docker…')
            row.append(spin)
            row.set_opacity(0.6)
        elif up:
            row.append(_button('■', f'Parar {box["name"]}', lambda n=box['name']: self._start('stop', n)))
        else:
            row.append(_button('▶', f'Iniciar {box["name"]}', lambda n=box['name']: self._start('start', n)))
        return row

    def _pick(self, name):
        """Elige un contenedor: su log se sigue en vivo; sin elegir, no corre ningún `docker logs`."""
        if self.tail is not None:
            self.tail.close()
            self.tail = None
        for key, (row, _c, _m) in self.rows.items():
            (row.add_css_class if key == name else row.remove_css_class)('picked')
        self.picked = name
        self.tail_stamp = -1
        self.logs.get_buffer().set_text('')
        if name:
            self.tail = containers.LogTail(name)
        self._detail()

    def _detail(self):
        self.detail.set_visible(bool(self.picked))
        self.empty.set_visible(not self.picked)
        if not self.picked:
            return
        box = next((c for p in (self.data or {'projects': []})['projects'] for c in p['containers']
                    if c['name'] == self.picked), None)
        if box is None:
            self._pick('')
            return
        self.detail_head.set_text(box['service'] or box['name'])
        self.detail_note.set_text(f'{box["name"]}  ·  {box["status"]}')
        live = box['state'] == 'running' and 'cpu' in box
        self.d_tiles.set_visible(live)
        if live:
            cpu = box['cpu'] / 100
            self.d_cpu_big.set_text(f'{box["cpu"]:.1f}%')
            set_bar(self.d_cpu_bar, cpu, level(cpu))
            self.d_cpu_note.set_text('de un núcleo')
            mem = box['mem_pct'] / 100
            self.d_mem_big.set_text(containers.fmt_bytes(box['mem']))
            set_bar(self.d_mem_bar, mem, level(mem))
            self.d_mem_note.set_text(f'{box["mem_pct"]:.1f}% de {containers.fmt_bytes(box["mem_limit"])}')
            self.d_net_big.set_text(f'↓{containers.fmt_bytes(box["net_rx"])}')
            self.d_net_note.set_text(f'↑ {containers.fmt_bytes(box["net_tx"])} enviados')
        if self.tail is not None and self.tail.stamp != self.tail_stamp:
            self._show_log(self.tail.stamp)

    def _show_log(self, stamp):
        """Primera vez: todo el log. Después, solo las líneas nuevas: no se toca lo que ya está, así el
        scroll no salta; solo sigue al final si ya estaba ahí."""
        adj = self.log_scroll.get_vadjustment()
        at_end = adj.get_value() >= adj.get_upper() - adj.get_page_size() - 24
        buf = self.logs.get_buffer()
        lines = list(self.tail.lines)
        new = stamp - self.tail_stamp if self.tail_stamp >= 0 else len(lines)
        if new >= len(lines):
            buf.set_text('')
            at_end = True
        else:
            lines = lines[-new:]
        for line in lines:
            tags = next(([self.tags[color]] for rx, color in LOG_TONES if rx.search(line)), [])
            buf.insert_with_tags(buf.get_end_iter(), line + '\n', *tags)
        extra = buf.get_line_count() - containers.LOG_LINES - 50
        if extra > 0:
            buf.delete(buf.get_start_iter(), buf.get_iter_at_line(extra))
        self.tail_stamp = stamp
        if at_end:
            GLib.idle_add(lambda: adj.set_value(adj.get_upper() - adj.get_page_size()) and False)

    def leave(self):
        """La vista se cierra: se suelta el log (un `docker logs -f` menos)."""
        if self.picked:
            self._pick('')
