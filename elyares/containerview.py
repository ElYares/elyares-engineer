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

from . import containers, fonts, icons, responsive, themes, windowframe
from .windowframe import SPACE

LIST_W = 660
# Columnas de la tabla (ancho en px); el nombre se queda con el resto. La cabecera y las filas comparten medidas.
COLS = (('ESTADO', 120, 0), ('PUERTOS', 110, 0), ('CPU', 56, 1), ('MEMORIA', 76, 1), ('CREADO', 80, 0))
ACTIONS_W = 64
KEYS = ('state', 'ports', 'cpu', 'mem', 'created')      # las columnas de COLS, en el mismo orden
# Columnas que se ocultan en cada modo; su dato pasa a la segunda línea del nombre.
HIDDEN = {responsive.COMPACT: KEYS, responsive.MEDIUM: ('ports', 'created'), responsive.WIDE: ()}
FILTERS = (('all', 'Todos'), ('up', 'Arriba'), ('stopped', 'Parados'), ('failed', 'Fallidos'))
# Colores de aviso: no son del tema; en los temas claros van en su versión oscura para que se lean (≥ 4.5:1).
GREEN, AMBER, RED = themes.SIGNALS[False]
GREY = '#8f9ab8'
CORES = os.cpu_count() or 1
PULSE_SECS = 1.3          # lo que tarda el esqueleto en latir una vez
RESULT_SECS = 8            # cuánto se queda a la vista «Levantado» o el error de una orden
WORDS = {'up': 'Levantando', 'stop-project': 'Parando', 'stop': 'Parando', 'start': 'Iniciando'}
DONE = {'up': 'Levantado', 'stop-project': 'Parado', 'stop': 'Parado', 'start': 'Iniciado'}
HOT_CPU, WARM_CPU = 80.0, 50.0           # % de un núcleo
BIG_MEM = 1024 ** 3                       # un contenedor de más de 1 GB se marca
# Líneas de log que merecen color: lo primero que coincida manda.
LOG_TONES = ((re.compile(r'\b(error|fatal|panic|exception|critical|traceback)\b|"level":(5|6)\d', re.I), 'red'),
             (re.compile(r'\b(warn|warning)\b|"level":4\d', re.I), 'amber'))

def palette():
    """Toma del tema de ahora los colores de aviso y el gris; los lee `dot()` y los estilos."""
    global GREEN, AMBER, RED, GREY
    GREEN, AMBER, RED = themes.signal()
    GREY = windowframe.MUTED


def build_css():
    """Los estilos de la vista, con los tokens del tema. alpha() sobre el color del texto sirve igual en oscuro y claro."""
    wf = windowframe
    return f"""
.cbox-row {{ border-radius: 8px; padding: 5px 4px; transition: background 120ms ease; }}
.cbox-row:hover {{ background: alpha(currentColor, 0.06); }}
.cbox-row.picked {{ background: alpha({wf.ACCENT}, 0.16); box-shadow: inset 2px 0 {wf.ACCENT}; }}
.cbox-row:focus-within {{ outline: 2px solid {wf.ACCENT}; outline-offset: -2px; }}
.cbox-act {{ opacity: 0; transition: opacity 120ms ease; }}
.cbox-row:hover .cbox-act, .cbox-row.picked .cbox-act, .cbox-row:focus-within .cbox-act {{ opacity: 1; }}
.cbox-flat {{ background: none; border: none; box-shadow: none; padding: 4px 6px; min-height: 0; }}
.cbox-flat:hover {{ background: none; }}
.cbox-ghost {{ background: transparent; border: 1px solid alpha(currentColor, 0.16); box-shadow: none;
              border-radius: 8px; padding: 4px 12px; min-height: 28px; }}
.cbox-ghost:hover {{ background: alpha(currentColor, 0.08); }}
.cbox-ghost.go {{ color: {wf.ACCENT}; }}
.cbox-tool {{ background: none; border: none; box-shadow: none; min-width: 28px; min-height: 28px; padding: 0;
             border-radius: 8px; color: {wf.MUTED}; }}
.cbox-tool:hover {{ background: alpha(currentColor, 0.10); color: {RED}; }}
.cbox-tool.go:hover {{ color: {GREEN}; }}
.cbox-muted {{ color: {wf.MUTED}; opacity: 1; }}
.cbox-head {{ {fonts.type_rule('caption')} color: {wf.MUTED}; padding: 4px 4px;
              border-bottom: 1px solid alpha(currentColor, 0.12); }}
.cbox-group {{ background: alpha(currentColor, 0.05); border-radius: 8px; padding: 6px 8px; margin-top: 6px; }}
.cbox-tree {{ margin-left: 14px; border-left: 1px solid alpha(currentColor, 0.18); }}
.cbox-sep {{ border-bottom: 1px solid alpha(currentColor, 0.07); }}
.cbox-icon {{ background: alpha(currentColor, 0.08); border: 1px solid alpha(currentColor, 0.10);
             border-radius: 8px; min-width: 32px; min-height: 32px; }}
.cbox-icon.pad {{ background: alpha(white, 0.9); }}
.cbox-pip {{ min-width: 8px; min-height: 8px; border-radius: 99px; margin: 0; box-shadow: 0 0 0 2px {wf.SURFACE[1]};
            background: {GREY}; }}
.cbox-pip.up {{ background: {GREEN}; }}
.cbox-pip.warn {{ background: {AMBER}; }}
.cbox-pip.bad {{ background: {RED}; }}
.cbox-link {{ font-weight: 600; color: {wf.INK}; }}
.cbox-port {{ color: {wf.ACCENT}; font-feature-settings: "tnum"; }}
.cbox-chip {{ border-radius: 99px; padding: 2px 12px; min-height: 0; background: alpha(currentColor, 0.06);
             border: 1px solid alpha(currentColor, 0.14); box-shadow: none; }}
.cbox-chip:checked {{ background: alpha({wf.ACCENT}, 0.2); border-color: alpha({wf.ACCENT}, 0.7); }}
.cbox-card {{ border-left: 3px solid {GREY}; }}
.cbox-badge {{ border-radius: 99px; padding: 0 8px; {fonts.type_rule('caption')} letter-spacing: 0;
              background: alpha({wf.MUTED}, 0.2); color: {wf.MUTED}; }}
.cbox-badge.all {{ background: alpha({GREEN}, 0.18); color: {GREEN}; }}
.cbox-badge.part {{ background: alpha({AMBER}, 0.18); color: {AMBER}; }}
.cbox-num {{ font-feature-settings: "tnum"; }}
.cbox-num.warm {{ color: {AMBER}; }}
.cbox-num.hot {{ color: {RED}; }}
.cbox-tile {{ background: alpha(currentColor, 0.06); border-radius: 8px; padding: 8px 12px; }}
.cbox-big {{ {fonts.type_rule('figure')} }}
.cbox-bar trough {{ min-height: 5px; border-radius: 99px; background: alpha(currentColor, 0.12); }}
.cbox-bar progress {{ min-height: 5px; border-radius: 99px; background: {GREEN}; }}
.cbox-bar.warm progress {{ background: {AMBER}; }}
.cbox-bar.hot progress {{ background: {RED}; }}
.cbox-job {{ border-radius: 8px; padding: 6px 8px; background: alpha({AMBER}, 0.14); }}
.cbox-job.ok {{ background: alpha({GREEN}, 0.16); }}
.cbox-job.bad {{ background: alpha({RED}, 0.18); }}
.cbox-skel {{ background: rgba(128, 128, 128, 0.28); border-radius: 8px; color: transparent; }}
.cbox-logs {{ background: alpha(currentColor, 0.06); color: {wf.INK}; border-radius: 8px; {fonts.type_rule('small')} }}
.cbox-logs text {{ background: none; }}
"""


_css = None


def load_css():
    global _css
    if _css is None:
        palette()
        _css = Gtk.CssProvider()
        _css.load_from_string(build_css())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), _css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        windowframe.HOOKS.append(retheme)


def retheme():
    """Cambió el tema: colores de aviso y estilos de la vista, en caliente."""
    palette()
    _css.load_from_string(build_css())


CLEAN_EXITS = ('Exited (0)', 'Exited (137)', 'Exited (143)')     # los que paró alguien: no son una caída


def dot(box):
    """El punto de un contenedor: verde arriba, rojo si se cayó con error o no está sano, gris si solo está parado."""
    if box['state'] == 'running':
        return RED if box.get('health') == 'unhealthy' else GREEN
    if box['state'] in ('created', 'restarting'):
        return AMBER
    return RED if box['state'] == 'exited' and not box['status'].startswith(CLEAN_EXITS) else GREY


def kind(box):
    """'failed' (cayó con error o no está sano) | 'up' | 'stopped': a qué chip pertenece."""
    if dot(box) == RED:
        return 'failed'
    return 'up' if box['state'] == 'running' else 'stopped'


def state_text(box):
    """Lo que dice la columna ESTADO: «Arriba 8 h», «No sano», «Parado», «Falló»."""
    if box['state'] == 'running':
        return 'No sano' if box.get('health') == 'unhealthy' else f'Arriba {containers.span(box["status"])}'.strip()
    if box['state'] in ('created', 'restarting'):
        return 'Reiniciando' if box['state'] == 'restarting' else 'Creado'
    return 'Falló' if dot(box) == RED else 'Parado'


def _button(text, tip, call, ghost=None):
    """`ghost`: None = botón de siempre; '' = botón fantasma; 'go' = fantasma con el color de acento;
    'tool' / 'tool go' = icono plano de 28 px (el ■ se pone rojo al pasar el ratón, el ▶ verde)."""
    btn = Gtk.Button(label=text)
    if ghost is None:
        btn.add_css_class('elyares-btn')
        btn.add_css_class('compact')
    else:
        btn.add_css_class('cbox-tool' if ghost.startswith('tool') else 'cbox-ghost')
        for extra in ghost.split():
            if extra != 'tool':
                btn.add_css_class(extra)
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
        self.mode = 'all'           # qué chip está puesto: all, up, stopped o failed
        self.query = ''
        self.collapsed = set()      # carpetas de proyectos con la fila cerrada
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
        self.layout_mode = None     # compact | medium | wide (ver responsive.py)
        self.head_cells = {}        # columna → su título en la cabecera
        self.cells = {key: [] for key in KEYS}          # columna → sus celdas en las filas
        self.subs = []              # (segunda línea del nombre, contenedor)

        # Arriba: lo que gastan todos juntos y el filtro.
        up_tile, self.up_big, self.up_bar, self.up_note = _tile('ARRIBA')
        cpu_tile, self.cpu_big, self.cpu_bar, self.cpu_note = _tile('CPU')
        mem_tile, self.mem_big, self.mem_bar, self.mem_note = _tile('MEMORIA')
        tiles = self.tiles = Gtk.Box(spacing=SPACE[1], homogeneous=True)
        for tile in (up_tile, cpu_tile, mem_tile):
            tiles.append(tile)
        title = Gtk.Label(label='Contenedores', xalign=0)
        title.add_css_class('elyares-title')
        self.chips = {}
        first = None
        top = Gtk.Box(spacing=SPACE[1])
        top.append(title)
        for key, text in FILTERS:
            chip = Gtk.ToggleButton(label=text)
            chip.add_css_class('cbox-chip')
            if first is None:
                first = chip
            else:
                chip.set_group(first)
            chip.connect('toggled', self._filter, key)
            self.chips[key] = chip
            top.append(chip)
        first.set_active(True)
        top.append(Gtk.Box(hexpand=True))
        self.search = Gtk.SearchEntry(placeholder_text='Buscar contenedores…')
        self.search.connect('search-changed', self._search)
        top.append(self.search)
        self.append(top)
        self.append(tiles)

        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        scroll = self.list_scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.page)
        scroll.set_size_request(300, -1)
        scroll.set_vexpand(True)
        scroll.set_min_content_height(200)
        table = self.table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        table.append(self._column_head())
        table.append(scroll)

        # A la derecha: el contenedor elegido, con su consumo y su log.
        self.detail_head = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.detail_head.add_css_class('title-3')
        self.detail_note = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.detail_note.add_css_class('dim-label')
        d_cpu, self.d_cpu_big, self.d_cpu_bar, self.d_cpu_note = _tile('CPU')
        d_mem, self.d_mem_big, self.d_mem_bar, self.d_mem_note = _tile('MEMORIA')
        d_net, self.d_net_big, self.d_net_bar, self.d_net_note = _tile('RED')
        self.d_net_bar.set_visible(False)
        self.back = Gtk.Button(label='‹ Volver', halign=Gtk.Align.START)
        self.back.add_css_class('elyares-btn')
        self.back.connect('clicked', lambda _b: self._pick(''))
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
        self.tags = {name: buf.create_tag(None) for _rx, name in LOG_TONES}
        self._retint()
        windowframe.HOOKS.append(self._retint)
        self.log_scroll = Gtk.ScrolledWindow()
        self.log_scroll.set_vexpand(True)
        self.log_scroll.set_child(self.logs)
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        self.detail.set_margin_start(SPACE[1])
        for w in (self.back, self.detail_head, self.detail_note, self.d_tiles, logs_title, self.log_scroll):
            self.detail.append(w)
        self.empty = Gtk.Label(label='Elige un contenedor para ver su consumo y su log.', xalign=0.5, yalign=0.4,
                               vexpand=True, hexpand=True)
        self.empty.add_css_class('dim-label')
        stack = self.side = Gtk.Overlay()
        stack.set_child(self.detail)
        stack.add_overlay(self.empty)

        body = self.body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_start_child(table)
        body.set_end_child(stack)
        body.set_position(LIST_W)
        body.set_resize_start_child(True)
        body.set_shrink_start_child(True)
        body.set_shrink_end_child(True)
        body.set_vexpand(True)
        self.append(body)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._key)
        self.add_controller(keys)
        self.add_tick_callback(self._measure)
        self._pick('')
        self.set_visible(False)

    def _retint(self):
        """Los colores del log y de la lista siguen al tema."""
        for name, color in (('red', RED), ('amber', AMBER)):
            self.tags[name].set_property('foreground', color)
        if self.data is not None:
            self._refresh()

    def _key(self, _ctl, keyval, _code, _state):
        """Esc cierra el detalle cuando ocupa el lugar de la lista."""
        if keyval == Gdk.KEY_Escape and self.picked and self.layout_mode != responsive.WIDE:
            self._pick('')
            return True
        return False

    def _measure(self, _widget, _clock):
        width = self.get_width()
        new = responsive.mode(width, self.layout_mode, fonts.view_scale()) if width else self.layout_mode
        if new != self.layout_mode:
            self.layout_mode = new
            self._apply_mode()
        return GLib.SOURCE_CONTINUE

    def _apply_mode(self):
        """Muestra u oculta columnas según el ancho; lo oculto pasa a la segunda línea del nombre."""
        hidden = HIDDEN.get(self.layout_mode, ())
        for key in KEYS:
            for cell in [self.head_cells.get(key), *self.cells[key]]:
                if cell is not None:
                    cell.set_visible(key not in hidden)
        for label, box in self.subs:
            label.set_text(self._subtitle(box, hidden))
        self._layout()

    @staticmethod
    def _subtitle(box, hidden):
        parts = [box.get('image') or box['name']]
        if 'state' in hidden:
            parts.append(state_text(box))
        if 'ports' in hidden and box.get('ports'):
            parts.append(box['ports'][0])
        if 'created' in hidden and box.get('created'):
            parts.append(f'hace {box["created"]}')
        return ' · '.join(parts)

    def _layout(self):
        """Lista y detalle: lado a lado si cabe; si no, el detalle ocupa el lugar de la lista (con «Volver»)."""
        mode, picked = self.layout_mode, bool(self.picked)
        wide = mode == responsive.WIDE
        flat = Gtk.Orientation.VERTICAL if mode == responsive.COMPACT else Gtk.Orientation.HORIZONTAL
        self.tiles.set_orientation(flat)
        self.d_tiles.set_orientation(flat)
        self.tiles.set_visible(wide or not picked)
        self.table.set_visible(wide or not picked)
        self.side.set_visible(picked)
        self.empty.set_visible(not picked)
        self.back.set_visible(picked and not wide)
        if wide and picked and self.body.get_width() and self.body.get_position() > self.body.get_width() - 320:
            self.body.set_position(max(480, int(self.body.get_width() * 0.56)))

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
        if not self.pulse_id and Gtk.Settings.get_default().props.gtk_enable_animations:
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
        for widget in self.skeleton:
            widget.set_opacity(1.0)
            widget.remove_css_class('cbox-skel')
        self.skeleton = []
        self.empty.set_label('Elige un contenedor para ver su consumo y su log.')

    def _filter(self, btn, key):
        if not btn.get_active():
            return
        self.mode = key
        self._refresh()

    def _search(self, entry):
        self.query = entry.get_text().strip().lower()
        self._refresh()

    def _refresh(self):
        self.sig = None
        if self.data is not None:
            self.set_data(self.data, self.handlers)

    def _kept(self, box):
        """¿Entra este contenedor con el chip y la búsqueda puestos?"""
        if self.mode != 'all' and kind(box) != self.mode:
            return False
        text = f'{box["name"]} {box["service"]} {box.get("image", "")}'.lower()
        return self.query in text

    def _column_head(self):
        head = Gtk.Box(spacing=SPACE[1])
        head.add_css_class('cbox-head')
        head.append(Gtk.Label(label='NOMBRE', xalign=0, hexpand=True))
        for key, (text, width, right) in zip(KEYS, COLS):
            self.head_cells[key] = Gtk.Label(label=text, xalign=1 if right else 0, width_request=width)
            head.append(self.head_cells[key])
        head.append(Gtk.Label(label='ACCIONES', xalign=1, width_request=ACTIONS_W))
        return head

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
        filtering = self.mode != 'all' or bool(self.query)
        projects = [dict(p, containers=[c for c in p['containers'] if self._kept(c)]) for p in data['projects']]
        projects = [p for p in projects if p['containers'] or not filtering]
        self._counts(data['projects'])
        sig = repr([sorted((k, j['done']) for k, j in self.jobs.items()), sorted(self.collapsed),
                    [(p['path'], [(c['name'], c['state'], c.get('health'), c['status'] if c['state'] != 'running' else '')
                                  for c in p['containers']]) for p in projects]])
        if sig != self.sig:
            self.sig = sig
            self._rebuild(projects)
        for box in (c for p in data['projects'] for c in p['containers']):
            if box['name'] in self.rows:
                self._usage(box)
        self._jobs_tick()
        self._detail()

    def _counts(self, projects):
        """El número de cada chip, siempre sobre todo lo que hay (no sobre lo ya filtrado)."""
        boxes = [c for p in projects for c in p['containers']]
        counts = {key: sum(kind(c) == key for c in boxes) for key, _t in FILTERS[1:]}
        counts['all'] = len(boxes)
        for key, text in FILTERS:
            self.chips[key].set_label(f'{text} {counts[key]}')

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
        cpu.set_text(f'{box["cpu"]:.1f}%' if live else '—')
        mem.set_text(containers.fmt_bytes(box['mem']) if live else '—')
        _tone(cpu, 'hot' if live and box['cpu'] >= HOT_CPU else 'warm' if live and box['cpu'] >= WARM_CPU else '')
        _tone(mem, 'warm' if live and box['mem'] >= BIG_MEM else '')

    def _rebuild(self, projects):
        adj = self.list_scroll.get_vadjustment()
        keep = adj.get_value()
        self.rows, self.cards = {}, {}
        self.cells, self.subs = {key: [] for key in KEYS}, []
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        if not projects:
            note = Gtk.Label(label='Nada coincide con el filtro.' if self.mode != 'all' or self.query else 'Sin datos todavía: se vuelve a intentar solo.' if self.data is None else 'No hay proyectos de DevHerd.',
                             xalign=0)
            note.add_css_class('dim-label')
            self.page.append(note)
        for proj in projects:
            self.page.append(self._card(proj))
        if self.layout_mode:
            self._apply_mode()
        GLib.idle_add(adj.set_value, keep)      # rehacer la lista no devuelve el scroll arriba

    def _card(self, proj):
        """La fila del proyecto (se cierra con ▾/▸, trae «Levantar todo» y «Parar todo»), su franja de
        avance y, con una línea de árbol a la izquierda, sus contenedores."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        path = proj['path']
        shut = path in self.collapsed
        arrow = Gtk.Button()
        arrow.set_child(Gtk.Image.new_from_paintable(
            icons.load('lucide', 'chevron-right' if shut else 'chevron-down', 16, windowframe.MUTED)))
        arrow.add_css_class('cbox-flat')
        arrow.set_tooltip_text('Abrir' if shut else 'Cerrar')
        arrow.update_property([Gtk.AccessibleProperty.LABEL], [f'{"Abrir" if shut else "Cerrar"} {proj["name"]}'])
        arrow.connect('clicked', lambda _b: self._fold(path))
        title = Gtk.Label(label=proj['name'], xalign=0, ellipsize=Pango.EllipsizeMode.END)
        title.add_css_class('heading')
        sub = Gtk.Label(label='Compose' if proj['total'] else 'sin contenedores', xalign=0,
                        ellipsize=Pango.EllipsizeMode.END)
        sub.add_css_class('cbox-muted')
        tone = 'all' if proj['total'] and proj['running'] == proj['total'] else 'part' if proj['running'] else ''
        badge = Gtk.Label(label=f'{proj["running"]}/{proj["total"]}', valign=Gtk.Align.CENTER)
        badge.add_css_class('cbox-badge')
        if tone:
            badge.add_css_class(tone)
        badge.set_visible(bool(proj['total']))
        badge.set_tooltip_text(f'{proj["running"]} de {proj["total"]} arriba')
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        names.append(title)
        names.append(sub)
        icon = Gtk.Image.new_from_paintable(icons.load('lucide', 'layers', 18, windowframe.MUTED))
        icon.set_pixel_size(18)
        icon.add_css_class('cbox-icon')
        head = Gtk.Box(spacing=SPACE[1])
        head.add_css_class('cbox-group')
        for w in (arrow, icon, names, badge):
            head.append(w)
        buttons = []
        if path:
            if proj['running'] < proj['total'] or not proj['total']:
                up = _button('▶ Levantar', f'Levantar {proj["name"]} con devherd up',
                             lambda p=path: self._start('up', p), ghost='go')
                head.append(up)
                buttons.append(up)
            if proj['running']:
                stop = _button('■ Parar', f'Parar todo {proj["name"]} con devherd stop',
                               lambda p=path: self._start('stop-project', p), ghost='')
                head.append(stop)
                buttons.append(stop)
        busy = self._project_job(path)
        for btn in buttons:
            btn.set_sensitive(busy is None)
        card.append(head)
        card.append(self._strip(path, busy))
        if not shut:
            tree = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            tree.add_css_class('cbox-tree')
            for box in proj['containers']:
                tree.append(self._row(box))
            card.append(tree)
        return card

    @staticmethod
    def _logo(box):
        """El icono de la imagen (o una caja gris si no se reconoce) con el color del estado en la esquina."""
        art = icons.for_image(box.get('image'), box['service'], box.get('path', ''))
        image = Gtk.Image.new_from_paintable(art or icons.load('lucide', 'box', 18, GREY))
        image.set_pixel_size(22 if art else 18)
        image.add_css_class('cbox-icon')
        if art and not themes.is_light() and icons.find(box.get('image'), box['service'], where=box.get('path', '')) in icons.DARK_LOGOS:
            image.add_css_class('pad')
        pip = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.END)
        pip.add_css_class('cbox-pip')
        tone = {GREEN: 'up', AMBER: 'warn', RED: 'bad'}.get(dot(box))
        if tone:
            pip.add_css_class(tone)
        over = Gtk.Overlay()
        over.set_child(image)
        over.add_overlay(pip)
        return over

    def _fold(self, path):
        self.collapsed ^= {path}
        self._refresh()

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
        """Una fila de la tabla: nombre con su imagen debajo, estado, puertos, CPU, memoria, antigüedad y acción."""
        up = box['state'] == 'running'
        row = Gtk.Box(spacing=SPACE[1])
        row.add_css_class('cbox-row')
        row.add_css_class('cbox-sep')
        if box['name'] == self.picked:
            row.add_css_class('picked')
        pick = Gtk.Button()
        pick.add_css_class('cbox-flat')
        pick.set_hexpand(True)
        name = Gtk.Label(label=box['service'] or box['name'], xalign=0, ellipsize=Pango.EllipsizeMode.END)
        name.add_css_class('cbox-link')
        image = Gtk.Label(label=box.get('image') or box['name'], xalign=0, ellipsize=Pango.EllipsizeMode.END)
        image.add_css_class('cbox-muted')
        lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        lines.append(name)
        lines.append(image)
        inner = Gtk.Box(spacing=SPACE[1])
        inner.append(self._logo(box))
        inner.append(lines)
        pick.set_child(inner)
        pick.connect('clicked', lambda _b, n=box['name']: self._pick(n))
        click = Gtk.GestureClick()
        click.connect('released', lambda *_a, n=box['name']: self._pick(n))
        row.add_controller(click)
        state = Gtk.Label(label=state_text(box), xalign=0, width_request=COLS[0][1], ellipsize=Pango.EllipsizeMode.END)
        state.set_tooltip_text(f'{state_text(box)} · {box["name"]}')
        ports = Gtk.Label(label=' '.join(box.get('ports', [])[:2]) or '—', xalign=0, width_request=COLS[1][1],
                          ellipsize=Pango.EllipsizeMode.END)
        ports.add_css_class('cbox-port' if box.get('ports') else 'cbox-muted')
        ports.set_tooltip_text(', '.join(box.get('ports', [])))
        cpu, mem = _num(6), _num(8)
        cpu.set_size_request(COLS[2][1], -1)
        mem.set_size_request(COLS[3][1], -1)
        created = Gtk.Label(label=f'hace {box["created"]}' if box.get('created') else '', xalign=0,
                            width_request=COLS[4][1])
        created.add_css_class('cbox-muted')
        self.rows[box['name']] = (row, cpu, mem)
        for key, cell in zip(KEYS, (state, ports, cpu, mem, created)):
            self.cells[key].append(cell)
        self.subs.append((image, box))
        for w in (pick, state, ports, cpu, mem, created):
            row.append(w)
        job = self.jobs.get(('stop' if up else 'start', box['name'])) or self.jobs.get(('start' if up else 'stop', box['name']))
        actions = Gtk.Box(halign=Gtk.Align.END, width_request=ACTIONS_W)
        actions.add_css_class('cbox-act')
        if job is not None and not job['done']:
            spin = Gtk.Spinner()
            spin.start()
            spin.set_tooltip_text('Esperando a docker…')
            actions.append(spin)
            row.set_opacity(0.6)
        elif up:
            actions.append(_button('■', f'Parar {box["name"]}', lambda n=box['name']: self._start('stop', n), ghost='tool'))
        else:
            actions.append(_button('▶', f'Iniciar {box["name"]}', lambda n=box['name']: self._start('start', n), ghost='tool go'))
        row.append(actions)
        return row

    def _pick(self, name):
        """Elige un contenedor: su log se sigue en vivo; sin elegir, no corre ningún `docker logs`."""
        if name and name == self.picked:
            return
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
        self._layout()
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
            tags = next(([self.tags[name]] for rx, name in LOG_TONES if rx.search(line)), [])
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
