"""El panel de Pomodoro de la isla suelta: la taza con su café, el reloj y las tareas del proyecto abierto.

Se abre desde «Más → Pomodoro» o con `elyares-ctl pomodoro`. El reloj lo manda el daemon de `coffe`
(`pomodoro.py`: aquí solo se le pregunta y se le piden cosas, con `window_pomodoro`). La taza (`cup.py`) baja con el reloj en
foco, sube en el descanso y humea. Las tareas son solo las del proyecto que tienes abierto: el del chat
o, sin chat, el de la sesión de tmux en la que estás. `PomodoroView` es parte de la isla
(`app.Island` la hereda) y comparte con la ventana el lector `pomo_watch`.
"""

import time

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk  # noqa: E402

from . import cup, mascot, pomodoro, prefsview, state, themes

PM_W = prefsview.PREFS_W
PM_PAD = prefsview.PREFS_PAD
PM_HEAD = prefsview.PREFS_HEAD
PM_CUP = 124
PM_GAP = 14                              # entre la taza y el texto
PM_ROW = 26
PM_ROWS = 5                              # las tareas que caben; las demás se cuentan al pie
PM_FOOT = 24
FONT_PM_CLOCK = 'Sans Bold 24'
FONT_PM_TASK = 'Sans Medium 10'
BTN_H = 24
BTN_GAP = 6
BTN_CHAR = 6.4                           # lo que mide una letra de 'Sans Semi-Bold 8': el reparto en filas no mide con Cairo
BTN_PAD = 16
INFO_W = 22                              # el hueco del «ⓘ» de una tarea
TEXT_TOP, TEXT_BTN = 56, 108             # dónde empiezan, bajo el reloj, la tarea y los botones
DETAIL_CHARS = 56                        # letras por línea que se cuentan en la burbuja (de menos: sobra sitio, no falta)
DETAIL_LINE = 13                         # lo que mide una línea de su descripción
DETAIL_MIN_LINES, DETAIL_MAX_LINES = 5, 24   # lo que se ve de la descripción: nunca menos ni más; lo demás, con la rueda
DETAIL_SCREEN = .8                       # la burbuja no pasa de esta parte de lo que queda de pantalla debajo de ella
SCROLL_STEP = 39                         # px por vuelta de rueda (tres líneas)
DETAIL_HEAD = 8 + 36 + 18                # su aire de arriba, el título (dos líneas) y el proyecto
PHASE_TONES = {'focus': 'green', 'overlearning': 'green', 'break': 'yellow', 'short_break': 'yellow',
               'long_break': 'yellow', 'break-long': 'yellow'}


def project_tasks(tasks, root):
    """Las tareas de `tasks` cuyo repo es el de `root`. Sin proyecto abierto, ninguna: no se mezclan los de todos."""
    if not root:
        return []
    return [t for t in tasks if t.get('repo') and state.project_root(t['repo']) == state.project_root(root)]


def buttons_for(status):
    """Los botones que valen ahora: [(clave, texto)]. Sacar del refri, o con un pomodoro en curso, pausar, tirar y cerrar la tarea."""
    if status is None:
        return []
    out = []
    if status['parked']:
        out.append(('resume', 'Sacar del refri'))
    if status['running']:
        out.append(('pause', 'Al refri'))
        out.append(('void', 'Tirar'))
        if status['task']:
            out.append(('done', 'Hecha'))
    return out


def button_width(label):
    return int(len(label) * BTN_CHAR) + BTN_PAD


def button_rows(buttons, room):
    """Reparte los botones en filas que caben en `room` px: [(clave, texto, x, fila, ancho)].
    Uno que no cabe baja a la fila siguiente; uno solo, aunque sea más ancho, se queda en su fila."""
    placed, x, row = [], 0, 0
    for key, label in buttons:
        bw = button_width(label)
        if x and x + bw > room:
            x, row = 0, row + 1
        placed.append((key, label, x, row, bw))
        x += bw + BTN_GAP
    return placed


def header_height(buttons, room):
    """Lo que mide el bloque de arriba: la taza, o el texto con sus botones si son más de una fila."""
    rows = 1 + max((row for _k, _l, _x, row, _w in button_rows(buttons, room)), default=-1) if buttons else 0
    return max(PM_CUP, TEXT_BTN + rows * (BTN_H + BTN_GAP) - BTN_GAP)


def estimated_text_height(text):
    """Lo que medirá la descripción antes de dibujarla (cuenta letras por línea; después manda lo medido)."""
    lines = sum(max(1, -(-len(par) // DETAIL_CHARS)) for par in (text or 'Sin descripción.').split('\n'))
    return lines * DETAIL_LINE


def detail_view_max(screen_h, top):
    """Cuánto alto de descripción se ve a la vez: lo que deja la pantalla debajo de `top` (el borde de arriba de
    la burbuja, ya contando el margen de la isla), entre `DETAIL_MIN_LINES` y `DETAIL_MAX_LINES` líneas."""
    most, least = DETAIL_MAX_LINES * DETAIL_LINE, DETAIL_MIN_LINES * DETAIL_LINE
    if not screen_h:
        return 12 * DETAIL_LINE
    room = (screen_h - top - DETAIL_HEAD - 10 - PM_FOOT) * DETAIL_SCREEN
    return int(max(least, min(most, room)))


def detail_height(info, text_h=None, view_max=None):
    """Lo que mide la burbuja: su cabeza, la descripción (medida, o estimada si aún no se dibujó) hasta
    `view_max`, y un poco de aire. Lo que sobre se ve con la rueda."""
    text_h = estimated_text_height(info['text']) if text_h is None else text_h
    view_max = DETAIL_MAX_LINES * DETAIL_LINE if view_max is None else view_max
    return DETAIL_HEAD + min(text_h, view_max) + 10


class PomodoroView:
    """Lo que guarda: `pm_open` (el panel está a la vista) y `pm_root` (el proyecto cuyas tareas se ven)."""

    pm_open = False
    pm_root = ''
    pm_detail = None                 # la burbuja abierta: lo que da `pomodoro.task_info`, o None
    pm_scroll = 0.0                  # cuánto se ha corrido su descripción, en px
    pm_text = (None, 0)              # (tarea, alto medido de su descripción): lo deja el último dibujo
    pm_rects = {}                    # {en la isla de al lado: (x, y, ancho, alto) de la burbuja}, del último dibujo
    pm_shown = (None, 0.0)          # (nivel que se pinta, cuándo): lo suaviza `pomodoro_level`
    pm_side = False                  # se está dibujando en la isla de al lado (`pomoisland.py`): «Ocultar» en vez de «Cerrar»

    def toggle_pomodoro(self):
        """Abre o cierra el panel. En la ventana no hay: tiene su vista Pomodoro."""
        if self.windowed:
            return
        self.pm_open = not self.pm_open
        self.off = False
        if self.pm_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.more_open = self.boxes_open = False
            self.themes_open = self.gf_open = self.sp_open = self.sv_open = False
            self.pm_root = self.pomodoro_root()
            self.pm_detail = None
            self.pomo_watch.refresh()
        self.ensure_tick()

    def pomodoro_root(self):
        """La carpeta del proyecto abierto: la del chat, o la de la sesión de tmux en la que estás."""
        if self.chat is not None and self.chat.cwd:
            return state.project_root(self.chat.cwd)
        here = self.project_here()
        return state.project_root(here.path) if here is not None else ''

    def pomodoro_busy(self):
        """¿Hay algo que mover? La taza humea mientras el reloj corre (si el movimiento no está reducido)."""
        if not self.pm_open or self.windowed or self.motion_reduced():
            return False
        return cup.state_of(pomodoro.describe(self.pomo_watch.status)) in ('vaciando', 'repaso', 'llenando')

    def pomodoro_tone(self, status):
        """El color del cronómetro: verde en foco, ámbar en descanso, neutro parado."""
        phase = status['phase'] if status else 'idle'
        return themes.ink_for(mascot.COLORS.get(PHASE_TONES.get(phase, 'metal'), '#8f9ab8'))

    def pomodoro_level(self, status):
        """El café que se pinta: el nivel de `coffe` (llega una vez por segundo) suavizado, para que la
        taza baje o suba de corrido y no a saltos. Un cambio grande (otra fase) salta de una vez."""
        target = cup.level_of(status)
        now = time.monotonic()
        shown, at = self.pm_shown
        if shown is None or abs(target - shown) > .3 or now - at > 1.5:
            shown = target
        else:
            shown += (target - shown) * min(1.0, (now - at) * 4)
        self.pm_shown = (shown, now)
        return shown

    def pomodoro_goal(self):
        status = pomodoro.describe(self.pomo_watch.status)
        room = PM_W - 2 * PM_PAD - PM_CUP - PM_GAP
        top = PM_HEAD + header_height(buttons_for(status), room)
        if self.pm_detail is not None:
            return PM_W, top + 8 + self.detail_box(self.pm_detail, top + 8) + PM_FOOT
        rows = max(1, min(PM_ROWS, len(self.pomodoro_tasks())))
        return PM_W, top + 34 + rows * PM_ROW + PM_FOOT

    def detail_box(self, info, y):
        """El alto de la burbuja de `info` si empieza en `y` de la isla: con lo medido en el último dibujo."""
        measured = self.pm_text[1] if self.pm_text[0] == info['id'] else None
        return detail_height(info, measured, detail_view_max(self.screen_h, self.top() + y))

    def pomodoro_tasks(self):
        return project_tasks(self.pomo_watch.read(None)[1], self.pm_root)

    def draw_pomodoro(self, cr, x0, w, h, alpha):
        left, width = x0 + PM_PAD, w - 2 * PM_PAD
        soft = mascot.rgba(self.ink('text', .62))[:3]
        head = mascot.rgba(self.ink('head'))[:3]
        self.put(cr, 'Pomodoro', prefsview.FONT_PREFS_TITLE, left, 14, mascot.rgba(self.ink('text'))[:3], alpha)
        if self.pm_side:
            links = (('hide', 'Ocultar'), ('island', 'Quitar'))
        else:
            links = (('close', 'Cerrar'), ('island', 'Quitar isla' if self.pi_open else 'Isla aparte'))
        x = left + width
        for key, label in links:                 # de derecha a izquierda
            layout = self._layout(cr, label, 'Sans Semi-Bold 9')
            lw, lh = layout.get_pixel_size()
            x -= lw
            over = self.over(x - 4, 10, lw + 8, lh + 8)
            self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
            self.hits.append(('pomodoro', key, x - 4, 10, lw + 8, lh + 8))
            x -= 16
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, PM_HEAD - 8, width, 1)
        cr.fill()
        status, tasks = self.pomo_watch.read(None)          # todas: se filtran por proyecto después
        if status is None:
            self.put(cr, 'El reloj de coffe no responde.', prefsview.FONT_PREFS, left + 4, PM_HEAD + 8, head, alpha)
            self.put(cr, 'Arráncalo con: systemctl --user start coffe', prefsview.FONT_PREFS_NOTE, left + 4,
                     PM_HEAD + 28, soft, alpha, width=width)
            return
        top = PM_HEAD
        cup.draw(cr, left, top, PM_CUP, cup.state_of(status), self.pomodoro_level(status), time.monotonic(), alpha)
        tx, tw = left + PM_CUP + PM_GAP, width - PM_CUP - PM_GAP
        tone = self.pomodoro_tone(status)
        self.put(cr, status['clock'], FONT_PM_CLOCK, tx, top, mascot.rgba(tone)[:3], alpha)
        self.put(cr, status['text'], prefsview.FONT_PREFS, tx, top + 36, head, alpha, width=tw)
        self.draw_pm_task(cr, status, tx, top + TEXT_TOP, tw, soft, alpha)
        done = ' '.join('●' if i < status['cycle'] else '○' for i in range(status['cycle_of']))
        self.put(cr, f'Hoy {status["today"]} · ciclo {done}', prefsview.FONT_PREFS_NOTE, tx, top + TEXT_BTN - 20, soft,
                 alpha * .9, width=tw)
        buttons = buttons_for(status)
        for key, label, bx, row, bw in button_rows(buttons, tw):
            self.draw_pm_button(cr, key, label, tx + bx, top + TEXT_BTN + row * (BTN_H + BTN_GAP), bw, alpha)
        self.draw_pm_lower(cr, tasks, left, top + header_height(buttons, tw) + 8, width, soft, head, alpha)

    def draw_pm_task(self, cr, status, x, y, w, soft, alpha):
        """La tarea en curso, hasta en dos líneas. Con tarea, un clic en su texto abre su burbuja."""
        text = status['task'] or ('Tarea en el refri' if status['parked'] else 'Sin tarea en curso')
        layout = self._layout(cr, text, FONT_PM_TASK, w, 2)
        lw, lh = layout.get_pixel_size()
        clickable = bool(status['task'] and status['task_id'])
        over = clickable and self.over(x, y, w, lh)
        self.tip_text(cr, layout, x, y, themes.hot() if over else soft, alpha, False)
        if clickable:
            self.hits.append(('pomodoro', f'info:{status["task_id"]}', x, y, w, lh))

    def draw_pm_lower(self, cr, tasks, x, y, w, soft, head, alpha):
        """Debajo del reloj: las tareas del proyecto, o la burbuja de la que se abrió."""
        if self.pm_detail is not None:
            self.draw_pm_detail(cr, x, y, w, soft, head, alpha)
        else:
            self.draw_pm_tasks(cr, tasks, x, y, w, soft, head, alpha)

    def draw_pm_detail(self, cr, x, y, w, soft, head, alpha):
        """La burbuja: título completo, proyecto, estimación y la descripción, que se corre con la rueda si no
        cabe. Un clic en ella la cierra."""
        info = self.pm_detail
        height = self.detail_box(info, y)
        self.pm_rects = {**self.pm_rects, self.pm_side: (x - 4, y, w + 8, height)}
        over = self.over(x - 4, y, w + 8, height)
        mascot.box(cr, x - 4, y, w + 8, height, 10)
        cr.set_source_rgba(*themes.glow(), (.16 if over else .11) * alpha)
        cr.fill_preserve()
        cr.set_source_rgba(*themes.glow(), .22 * alpha)
        cr.set_line_width(1)
        cr.stroke()
        inner, ix, iy = w - 24, x + 8, y + 8
        title = self._layout(cr, info['title'], prefsview.FONT_PREFS, inner, 2)
        self.tip_text(cr, title, ix, iy, head, alpha, False)
        iy += title.get_pixel_size()[1] + 4
        meta = info['project'] + (f' · {info["estimate"]} pomodoros' if info['estimate'] else '')
        self.put(cr, meta, prefsview.FONT_PREFS_NOTE, ix, iy, soft, alpha * .9, width=inner)
        iy += 18
        body = self._layout(cr, info['text'] or 'Sin descripción.', prefsview.FONT_PREFS_NOTE, inner, 200)
        text_h = body.get_pixel_size()[1]
        self.pm_text = (info['id'], text_h)
        view = max(1, y + height - 10 - iy)
        self.pm_scroll = max(0.0, min(self.pm_scroll, text_h - view))
        cr.save()
        cr.rectangle(ix, iy, inner + 4, view)
        cr.clip()
        self.tip_text(cr, body, ix, iy - self.pm_scroll, soft, alpha, False)
        cr.restore()
        if text_h > view:                                  # la barra de la rueda, a la derecha
            track = view
            thumb = max(14, track * view / text_h)
            ty = iy + (track - thumb) * self.pm_scroll / max(1, text_h - view)
            mascot.box(cr, x + w - 6, ty, 3, thumb, 1.5)
            cr.set_source_rgba(*themes.glow(), .45 * alpha)
            cr.fill()
        self.hits.append(('pomodoro', 'info-close', x - 4, y, w + 8, height))

    def on_pomodoro_scroll(self, dy, pointer, side=False):
        """La rueda sobre la burbuja corre la descripción. True si la atendió."""
        rect = self.pm_rects.get(side)
        if self.pm_detail is None or rect is None or pointer is None:
            return False
        x, y, w, h = rect
        if not (x <= pointer[0] <= x + w and y <= pointer[1] <= y + h):
            return False
        self.pm_scroll = max(0.0, self.pm_scroll + (SCROLL_STEP if dy > 0 else -SCROLL_STEP))    # el dibujo la recorta al final
        self.ensure_tick()
        if self.pi_da is not None:
            self.pi_redraw()
        return True

    def pomodoro_widgets(self):
        """La rueda de la isla de siempre: enchufada al lienzo, una vez."""
        wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.connect('scroll', lambda _c, _dx, dy: self.on_pomodoro_scroll(dy, self.pointer))
        self.da.add_controller(wheel)

    def draw_pm_button(self, cr, key, label, x, y, bw, alpha):
        """Un botón de texto con su fondo, de ancho `bw` (el reparto en filas lo calculó)."""
        layout = self._layout(cr, label, 'Sans Semi-Bold 8')
        lw, lh = layout.get_pixel_size()
        over = self.over(x, y, bw, BTN_H)
        mascot.box(cr, x, y, bw, BTN_H, 6)
        cr.set_source_rgba(*themes.glow(), (.18 if over else .09) * alpha)
        cr.fill()
        self.tip_text(cr, layout, x + (bw - lw) / 2, y + (BTN_H - lh) / 2, mascot.rgba(self.ink('head'))[:3], alpha, False)
        self.hits.append(('pomodoro', key, x, y, bw, BTN_H))

    def draw_pm_tasks(self, cr, tasks, x, y, w, soft, head, alpha):
        """Las tareas del proyecto abierto; un clic arranca el pomodoro de esa tarea."""
        mine = project_tasks(tasks, self.pm_root)
        name = state.project_name(self.pm_root) if self.pm_root else ''
        self.put(cr, f'TAREAS DE {name.upper()}' if name else 'TAREAS', prefsview.FONT_PREFS_NOTE, x + 4, y, soft,
                 alpha * .9, width=w)
        y += 20
        if not mine:
            note = 'Sin tareas pendientes en este proyecto.' if name else 'Abre un proyecto para ver sus tareas.'
            self.put(cr, note, prefsview.FONT_PREFS_NOTE, x + 4, y + 4, soft, alpha, width=w)
            return
        for i, task in enumerate(mine[:PM_ROWS]):
            ry = y + i * PM_ROW
            if self.over(x - 4, ry, w + 8, PM_ROW):
                mascot.box(cr, x - 4, ry, w + 8, PM_ROW, 6)
                cr.set_source_rgba(*themes.glow(), .08 * alpha)
                cr.fill()
            self.put(cr, task['title'], prefsview.FONT_PREFS, x + 4, ry + 5, head, alpha, width=w - 40 - INFO_W)
            self.put(cr, '▶', prefsview.FONT_PREFS_NOTE, x + w - 10, ry + 7, soft, alpha, align=1)
            self.hits.append(('pomodoro', f'start:{task["id"]}', x - 4, ry, w + 8 - 28 - INFO_W, PM_ROW))
            ix = x + w - 28 - INFO_W
            info_over = self.over(ix, ry, INFO_W, PM_ROW)
            self.put(cr, 'ⓘ', prefsview.FONT_PREFS, ix + INFO_W / 2, ry + 4, themes.hot() if info_over else soft, alpha,
                     align=.5)
            self.hits.append(('pomodoro', f'info:{task["id"]}', ix, ry, INFO_W, PM_ROW))
        if len(mine) > PM_ROWS:
            self.put(cr, f'y {len(mine) - PM_ROWS} más en la ventana.', prefsview.FONT_PREFS_NOTE, x + 4,
                     y + PM_ROWS * PM_ROW + 2, soft, alpha * .85, width=w)

    def on_pomodoro_hit(self, key):
        """Un clic: cerrar, un botón del reloj o arrancar una tarea. Todo menos cerrar va en un hilo."""
        if key == 'close':
            self.pm_open = False
            self.pm_detail = None
        elif key == 'info-close':
            self.pm_detail = None
        elif key.startswith('info:'):
            same = self.pm_detail is not None and self.pm_detail['id'] == key[5:]
            self.pm_detail = None if same else pomodoro.task_info(key[5:])
            self.pm_scroll = 0.0
        elif key == 'island':
            self.toggle_pomoisland()
        elif key == 'hide':
            self.pi_collapse(True)
        elif key.startswith('start:'):
            task = key[6:]
            if any(t['id'] == task for t in self.pomodoro_tasks()):          # solo las que se ven
                self.window_pomodoro('start', task)
        elif key in ('resume', 'pause', 'void', 'done'):
            self.window_pomodoro(key)
        self.ensure_tick()
