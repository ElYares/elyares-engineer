"""El panel Tareas de la isla suelta: las tareas de `coffe` como un ToDo por proyectos.

Una cabecera por proyecto (un clic la abre o la cierra; abre el proyecto de la carpeta activa y el
que tiene algo en curso) y una fila por tarea: casilla para darla por hecha, prioridad, título,
pomodoros y ▶ para empezar uno. Filtros Pendientes, Hechas, Todas y «Este proyecto»; la rueda
recorre la lista. Los datos son los de `pomodoro.Watcher` (el mismo de Inicio y de la ventana) y
las órdenes, `window_pomodoro`.

Se abre con «Tareas» del menú de Inicio o con `elyares-ctl tasks`. `TasksView` es parte de la
isla (`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

from gi.repository import Gtk

from . import mascot, pomodoro, themes

TASKS_W = 620
TASKS_PAD = 16
TASKS_HEAD = 44
TASKS_CHIPS = 30
TASKS_ROW = 24
TASKS_MAX_ROWS = 12                       # filas a la vista; las demás, con la rueda
TASKS_FOOT = 20
FONT_TASKS = 'Sans Medium 9'
FONT_TASKS_NOTE = 'JetBrainsMono Nerd Font 8'
FONT_TASKS_TITLE = 'Sans Semi-Bold 11'
FILTERS = (('open', 'Pendientes'), ('done', 'Hechas'), ('all', 'Todas'), ('here', 'Este proyecto'))
STATES = {'open': pomodoro.OPEN_STATES, 'done': (pomodoro.DONE,), 'here': pomodoro.OPEN_STATES,
          'all': pomodoro.ALL_STATES}
MARKS = pomodoro.MARKS
EMPTY = {'open': 'Nada pendiente.', 'done': 'Todavía no hay tareas hechas.', 'all': pomodoro.EMPTY_ALL}


class TasksView:
    """Lo que guarda: `tasks_open` (el panel está a la vista), `tasks_mode` (el filtro), `tasks_shut`
    (proyectos cerrados o abiertos a mano: nombre → si está abierto) y `tasks_top` (primera fila a la vista)."""

    tasks_open = False
    tasks_mode = 'open'
    tasks_shut = None
    tasks_top = 0
    tasks_ctl = None

    def toggle_tasks(self):
        """Abre o cierra el panel. En la ventana no hay: tiene su vista Tareas."""
        if self.windowed:
            return
        self.tasks_open = not self.tasks_open
        self.off = False
        if self.tasks_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.boxes_open = self.home_open = False
            self.tasks_shut, self.tasks_top = {}, 0
            self.pomo_watch.refresh()
            if self.tasks_ctl is None:                       # la rueda: un controlador, la primera vez
                self.tasks_ctl = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
                self.tasks_ctl.connect('scroll', self.on_tasks_scroll)
                self.da.add_controller(self.tasks_ctl)
        self.ensure_tick()

    def tasks_here(self):
        """El nombre en `coffe` del proyecto de la carpeta activa, o ''."""
        root = self.window_editor_root()
        return self.pomo_watch.project_of(root) if root else ''

    def tasks_rows(self):
        """Las filas del panel: ('head', proyecto, cuántas, abierto) y ('task', tarea)."""
        tasks = self.pomo_watch.read_all()                   # ya pregunta a coffe (`read`) si toca
        here = self.tasks_here()
        groups = pomodoro.by_project(tasks, STATES[self.tasks_mode])
        if self.tasks_mode == 'here':
            groups = [g for g in groups if g[0] == here]
        rows = []
        for name, items in groups:
            live = any(t['state'] == 'en curso' for t in items)
            opened = self.tasks_shut.get(name, name == here or live or self.tasks_mode == 'here')
            rows.append(('head', name, len(items), opened))
            if opened:
                rows.extend(('task', t) for t in items)
        return rows

    def tasks_goal(self):
        shown = max(1, min(len(self.tasks_rows()), TASKS_MAX_ROWS))
        return TASKS_W, TASKS_HEAD + TASKS_CHIPS + shown * TASKS_ROW + TASKS_FOOT

    def on_tasks_scroll(self, _ctrl, _dx, dy):
        if not (self.tasks_open and self.target() == 'tasks'):
            return False
        room = max(0, len(self.tasks_rows()) - TASKS_MAX_ROWS)
        self.tasks_top = int(min(room, max(0, self.tasks_top + (1 if dy > 0 else -1) * 3)))
        self.ensure_tick()
        return True

    def draw_tasks(self, cr, x0, w, h, alpha):
        left, width = x0 + TASKS_PAD, w - 2 * TASKS_PAD
        soft = mascot.rgba(self.ink('text', .62))[:3]
        head = mascot.rgba(self.ink('head'))[:3]
        rows = self.tasks_rows()
        projects = sum(1 for r in rows if r[0] == 'head')
        total = sum(r[2] for r in rows if r[0] == 'head')
        tw = self.put(cr, 'Tareas', FONT_TASKS_TITLE, left, 14, themes.tuple_of(themes.get()['ink']), alpha)
        load, why = self.pomo_watch.tasks_state()
        if load == 'ok':
            self.put(cr, f'{total} {"tarea" if total == 1 else "tareas"} en {projects} '
                         f'{"proyecto" if projects == 1 else "proyectos"}', FONT_TASKS_NOTE, left + tw + 12, 18, soft, alpha)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        cx = left + width - lw
        over = self.over(cx - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, cx, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('tasks', ('close',), cx - 4, 10, lw + 8, lh + 8))
        x = left
        for key, label in FILTERS:
            cw = self._layout(cr, label, FONT_TASKS_NOTE).get_pixel_size()[0] + 20
            on = key == self.tasks_mode
            hover = self.over(x, TASKS_HEAD - 5, cw, 24)
            mascot.box(cr, x, TASKS_HEAD - 4, cw, 22, 10)
            cr.set_source_rgba(*themes.glow(), (.2 if on else .12 if hover else .06) * alpha)
            cr.fill()
            self.put(cr, label, FONT_TASKS_NOTE, x + cw / 2, TASKS_HEAD, head if on else soft, alpha, align=.5)
            self.hits.append(('tasks', ('mode', key), x, TASKS_HEAD - 5, cw, 24))      # la zona de clic, de 24
            x += cw + 6
        top0 = TASKS_HEAD + TASKS_CHIPS
        if load != 'ok':
            self.draw_tasks_status(cr, load, why, left, top0, head, soft, alpha)
            return
        if not rows:
            self.put(cr, self.tasks_empty(), FONT_TASKS, left + 4, top0 + 4, soft, alpha, width=width - 8)
            return
        self.tasks_top = min(self.tasks_top, max(0, len(rows) - TASKS_MAX_ROWS))
        for i, row in enumerate(rows[self.tasks_top:self.tasks_top + TASKS_MAX_ROWS]):
            y = top0 + i * TASKS_ROW
            if row[0] == 'head':
                self.draw_tasks_head(cr, row, left, y, width, head, soft, alpha)
            else:
                self.draw_tasks_row(cr, row[1], left, y, width, head, soft, alpha)
        if len(rows) > TASKS_MAX_ROWS:
            self.put(cr, f'{self.tasks_top + 1}–{min(len(rows), self.tasks_top + TASKS_MAX_ROWS)} de {len(rows)} · rueda',
                     FONT_TASKS_NOTE, left + width, h - TASKS_FOOT, soft, alpha * .8, align=1)

    def tasks_empty(self):
        """El vacío dice por qué y qué hacer."""
        if self.tasks_mode != 'here':
            return EMPTY[self.tasks_mode]
        if not self.window_editor_root():
            return 'No hay proyecto activo: abre un chat o elige una sesión.'
        if not self.tasks_here():
            return 'Esta carpeta no es un proyecto de coffe: coffe project add'
        return 'Este proyecto no tiene tareas pendientes en coffe.'

    def draw_tasks_status(self, cr, load, why, x, y, head, soft, alpha):
        """Mientras coffe no contesta, o si falló: qué pasa y, si falló, «Reintentar»."""
        if load == 'loading':
            self.put(cr, 'Preguntando a coffe…', FONT_TASKS, x + 4, y + 4, soft, alpha)
            return
        if 'No está instalado' in why:
            self.put(cr, 'No está instalado coffe, el pomodoro.', FONT_TASKS, x + 4, y + 4, soft, alpha)
            return
        self.put(cr, 'coffe no contesta. Arráncalo con: systemctl --user start coffe', FONT_TASKS, x + 4, y + 4,
                 soft, alpha)
        bw = self._layout(cr, 'Reintentar', FONT_TASKS_NOTE).get_pixel_size()[0] + 20
        by = y + 26
        over = self.over(x + 4, by, bw, 24)
        mascot.box(cr, x + 4, by, bw, 24, 8)
        cr.set_source_rgba(*themes.glow(), (.2 if over else .1) * alpha)
        cr.fill()
        self.put(cr, 'Reintentar', FONT_TASKS_NOTE, x + 4 + bw / 2, by + 5, head, alpha, align=.5)
        self.hits.append(('tasks', ('retry',), x + 4, by, bw, 24))

    def draw_tasks_head(self, cr, row, x, y, w, head, soft, alpha):
        _kind, name, count, opened = row
        if self.over(x - 4, y, w + 8, TASKS_ROW):
            mascot.box(cr, x - 4, y, w + 8, TASKS_ROW - 2, 6)
            cr.set_source_rgba(*themes.glow(), .08 * alpha)
            cr.fill()
        self.put(cr, '▾' if opened else '▸', FONT_TASKS, x + 2, y + 4, soft, alpha)
        tw = self.put(cr, name, FONT_TASKS, x + 20, y + 4, head, alpha, width=w - 80)
        self.put(cr, str(count), FONT_TASKS_NOTE, x + 28 + tw, y + 6, soft, alpha)
        self.hits.append(('tasks', ('fold', name, opened), x - 4, y, w + 8, TASKS_ROW))

    def draw_tasks_row(self, cr, task, x, y, w, head, soft, alpha):
        done, live = task['state'] == pomodoro.DONE, task['state'] == pomodoro.LIVE
        if self.over(x - 4, y, w + 8, TASKS_ROW):
            mascot.box(cr, x - 4, y, w + 8, TASKS_ROW - 2, 6)
            cr.set_source_rgba(*themes.glow(), .06 * alpha)
            cr.fill()
        ink = soft if done else head
        green, amber, _red = (themes.tuple_of(c) for c in themes.signal())     # aviso legible en claro y en oscuro
        self.put(cr, '☑' if done else '☐', FONT_TASKS, x + 18, y + 4, green if done else soft, alpha)
        self.hits.append(('tasks', ('check', task['id'], done), x + 12, y, 24, TASKS_ROW))
        self.put(cr, MARKS.get(task['priority'], '·'), FONT_TASKS_NOTE, x + 42, y + 6, soft, alpha)
        right = x + w
        bx = right - 26
        if not done and not live:
            over = self.over(bx, y + 1, 24, TASKS_ROW - 4)
            mascot.box(cr, bx, y + 1, 24, TASKS_ROW - 4, 8)
            cr.set_source_rgba(*themes.glow(), (.2 if over else .1) * alpha)
            cr.fill()
            self.put(cr, '▶', FONT_TASKS_NOTE, bx + 12, y + 5, head, alpha, align=.5)
            self.hits.append(('tasks', ('start', task['id']), bx, y, 24, TASKS_ROW))
        right = bx - 6                                       # la columna de ▶ se reserva siempre: los pomodoros no bailan
        pomos = f'{task["done"]}/{task["estimate"]}' if task['estimate'] else str(task['done'])
        self.put(cr, pomos, FONT_TASKS_NOTE, right, y + 6, soft, alpha, align=1)
        right -= 44
        if live or task['state'] == pomodoro.PARKED:
            tag = '● en curso' if live else '❄ refri'
            right -= self.put(cr, tag, FONT_TASKS_NOTE, right, y + 6, green if live else amber, alpha, align=1) + 10
        self.put(cr, task['title'], FONT_TASKS, x + 58, y + 4, ink, alpha, width=right - (x + 58))

    def on_tasks_hit(self, key):
        """Un clic en el panel: cerrar, cambiar el filtro, abrir un proyecto, dar por hecha o empezar una tarea."""
        what = key[0]
        if what == 'close':
            self.tasks_open = False
        elif what == 'mode':
            self.tasks_mode, self.tasks_top = key[1], 0
        elif what == 'fold':
            self.tasks_shut[key[1]] = not key[2]
        elif what == 'check':
            self.window_pomodoro('task', 'reopen' if key[2] else 'done', key[1])
        elif what == 'start':
            self.window_pomodoro('start', key[1])
        elif what == 'retry':
            self.pomo_watch.refresh()
        self.ensure_tick()
