"""El panel de Pomodoro de la isla suelta: la taza con su café, el reloj y las tareas del proyecto abierto.

Se abre desde «Más → Pomodoro» o con `elyares-ctl pomodoro`. El reloj lo manda el daemon de `coffe`
(`pomodoro.py`: aquí solo se le pregunta y se le piden cosas, con `window_pomodoro`). La taza (`cup.py`) baja con el reloj en
foco, sube en el descanso y humea. Las tareas son solo las del proyecto que tienes abierto: el del chat
o, sin chat, el de la sesión de tmux en la que estás. `PomodoroView` es parte de la isla
(`app.Island` la hereda) y comparte con la ventana el lector `pomo_watch`.
"""

import time

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


class PomodoroView:
    """Lo que guarda: `pm_open` (el panel está a la vista) y `pm_root` (el proyecto cuyas tareas se ven)."""

    pm_open = False
    pm_root = ''
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

    def pomodoro_goal(self):
        rows = max(1, min(PM_ROWS, len(self.pomodoro_tasks())))
        return PM_W, PM_HEAD + PM_CUP + 34 + rows * PM_ROW + PM_FOOT

    def pomodoro_tasks(self):
        return project_tasks(self.pomo_watch.read()[1], self.pm_root)

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
        status, tasks = self.pomo_watch.read()
        if status is None:
            self.put(cr, 'El reloj de coffe no responde.', prefsview.FONT_PREFS, left + 4, PM_HEAD + 8, head, alpha)
            self.put(cr, 'Arráncalo con: systemctl --user start coffe', prefsview.FONT_PREFS_NOTE, left + 4,
                     PM_HEAD + 28, soft, alpha, width=width)
            return
        top = PM_HEAD
        cup.draw(cr, left, top, PM_CUP, cup.state_of(status), cup.level_of(status), time.monotonic(), alpha)
        tx, tw = left + PM_CUP + PM_GAP, width - PM_CUP - PM_GAP
        tone = themes.ink_for(mascot.COLORS.get({'focus': 'green', 'overlearning': 'green', 'break': 'yellow',
                                                 'break-long': 'yellow'}.get(status['phase'], 'metal'), '#8f9ab8'))
        self.put(cr, status['clock'], FONT_PM_CLOCK, tx, top, mascot.rgba(tone)[:3], alpha)
        self.put(cr, status['text'], prefsview.FONT_PREFS, tx, top + 40, head, alpha, width=tw)
        self.put(cr, status['task'] or ('Tarea en el refri' if status['parked'] else 'Sin tarea en curso'),
                 FONT_PM_TASK, tx, top + 60, soft, alpha, width=tw)
        done = ' '.join('●' if i < status['cycle'] else '○' for i in range(status['cycle_of']))
        self.put(cr, f'Hoy {status["today"]} · ciclo {done}', prefsview.FONT_PREFS_NOTE, tx, top + 80, soft, alpha * .9,
                 width=tw)
        bx = tx
        for key, label in buttons_for(status):
            bx += self.draw_pm_button(cr, key, label, bx, top + 98, alpha) + 6
        self.draw_pm_tasks(cr, tasks, left, top + PM_CUP + 8, width, status, soft, head, alpha)

    def draw_pm_button(self, cr, key, label, x, y, alpha):
        """Un botón de texto con su fondo; devuelve lo que ocupó."""
        layout = self._layout(cr, label, 'Sans Semi-Bold 8')
        lw, lh = layout.get_pixel_size()
        bw = lw + 16
        over = self.over(x, y, bw, BTN_H)
        mascot.box(cr, x, y, bw, BTN_H, 6)
        cr.set_source_rgba(*themes.glow(), (.18 if over else .09) * alpha)
        cr.fill()
        self.tip_text(cr, layout, x + 8, y + (BTN_H - lh) / 2, mascot.rgba(self.ink('head'))[:3], alpha, False)
        self.hits.append(('pomodoro', key, x, y, bw, BTN_H))
        return bw

    def draw_pm_tasks(self, cr, tasks, x, y, w, status, soft, head, alpha):
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
            self.put(cr, task['title'], prefsview.FONT_PREFS, x + 4, ry + 5, head, alpha, width=w - 40)
            self.put(cr, '▶', prefsview.FONT_PREFS_NOTE, x + w - 10, ry + 7, soft, alpha, align=1)
            self.hits.append(('pomodoro', f'start:{task["id"]}', x - 4, ry, w + 8, PM_ROW))
        if len(mine) > PM_ROWS:
            self.put(cr, f'y {len(mine) - PM_ROWS} más en la ventana.', prefsview.FONT_PREFS_NOTE, x + 4,
                     y + PM_ROWS * PM_ROW + 2, soft, alpha * .85, width=w)

    def on_pomodoro_hit(self, key):
        """Un clic: cerrar, un botón del reloj o arrancar una tarea. Todo menos cerrar va en un hilo."""
        if key == 'close':
            self.pm_open = False
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
