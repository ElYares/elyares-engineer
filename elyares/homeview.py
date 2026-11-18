"""El panel Inicio de la isla suelta: el proyecto, los agentes y el contexto del elegido.

El mismo diseño que la vista Inicio de la ventana (`homepanel.py`), dibujado en Cairo: arriba el
proyecto, a la izquierda un menú de atajos, en el centro las tarjetas de los agentes (cinco y
«+ n más», o todos en cuatro columnas) y abajo el contexto de quien está elegido, con Permitir y
Denegar si pide permiso. El orden y los datos son los de la ventana (`homepanel.ordered`,
`window_team_cards`).

Se abre con la pastilla ⌂ del pie o con `elyares-ctl home`. `HomeView` es parte de la isla
(`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

import math
import os
import time

import cairo

from . import habits, homepanel, mascot, pomodoro, themes

HOME_W = 620
HOME_PAD = 16
HOME_HEAD = 40
HOME_MENU_W = 104
CARD_H, CARD_GAP = 56, 6
CONTEXT_H = 128
HOME_PILL = 'home'                         # la pastilla ⌂ del pie
FONT_HOME = 'Sans Medium 9'
FONT_HOME_TITLE = 'Sans Semi-Bold 11'
FONT_HOME_NOTE = 'JetBrainsMono Nerd Font 8'
# (clave, texto, qué es): un panel del contexto («pane») o un atajo a otro panel de la isla («go»).
HOME_MENU = (('pomodoro', 'Pomodoro', 'pane'), ('tasks', 'Tareas', 'pane'), ('habits', 'Hábitos', 'pane'),
             ('chat', 'Chat', 'go'), ('projects', 'Proyectos', 'go'), ('boxes', 'Contenedores', 'go'))
HABIT_ROWS = 4
POMO_H = 252                               # el Pomodoro ocupa el lugar de las tarjetas: la taza y las tareas
CUP = 150
POMO_ROWS = 4
FONT_HOME_CLOCK = 'Sans Semi-Bold 26'
# La taza de `coffe` (app/src/Taza.tsx), en su viewBox de 200: fuera del tema a propósito,
# porque un tema verde daría café verde.
BONE, COFFEE, COFFEE_LIGHT, COFFEE_COLD, FROST = '#f3ece2', '#6f4e37', '#8a6247', '#5c5450', '#bcd4e6'
CUP_TOP, CUP_BOTTOM = 74, 158             # el café sube y baja entre estas dos alturas


def _cup_body(cr):
    cr.move_to(52, 70)
    cr.line_to(148, 70)
    cr.line_to(137, 150)
    mascot.quad(cr, 135, 160, 124, 160)
    cr.line_to(76, 160)
    mascot.quad(cr, 65, 160, 63, 150)
    cr.close_path()


def _ellipse(cr, cx, cy, rx, ry):
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    cr.new_sub_path()
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()


def draw_cup(cr, x, y, size, state, level, alpha, now=0.0, still=False):
    """La taza de `coffe` en (x, y), de `size` de lado. `state` y `level` son los de `pomodoro.cup`:
    el café baja en foco y sube en el descanso; en el refri va dentro de él."""
    level = min(1.0, max(0.0, level))
    cold, fridge = state == 'fria', state == 'refri'
    cr.save()
    cr.translate(x, y)
    cr.scale(size / 200, size / 200)
    cr.set_line_cap(1)                    # redondas, como en la app
    cr.set_line_join(1)
    if fridge:
        mascot.rrect(cr, 22, 14, 156, 176, 12)
        cr.move_to(22, 62)
        cr.line_to(178, 62)
        cr.move_to(158, 32)
        cr.line_to(158, 48)
        cr.move_to(158, 80)
        cr.line_to(158, 104)
        cr.set_source_rgba(*mascot.rgba(FROST, alpha))
        cr.set_line_width(5)
        cr.stroke()
    if state in ('vaciando', 'repaso', 'llenando') and level > .04:
        for i, (sx, sy) in enumerate(((82, 52), (100, 46), (118, 52))):     # tres hilos con desfase
            p = .5 if still else (now / 2.4 + i * .7 / 2.4) % 1
            sy += 6 * (1 - p)
            cr.move_to(sx, sy)
            mascot.quad(cr, sx + 7, sy - 10, sx, sy - 20)
            mascot.quad(cr, sx - 7, sy - 30, sx, sy - 40)
            cr.set_source_rgba(*mascot.rgba(BONE, (.35 if still else .5 * math.sin(p * math.pi)) * alpha))
            cr.set_line_width(4)
            cr.stroke()
    cr.move_to(148, 88)                   # el asa va detrás del cuerpo
    mascot.quad(cr, 174, 90, 174, 110)
    mascot.quad(cr, 174, 130, 148, 132)
    cr.set_source_rgba(*mascot.rgba(BONE, alpha))
    cr.set_line_width(7)
    cr.stroke()
    top = CUP_BOTTOM - (CUP_BOTTOM - CUP_TOP) * level
    cr.save()
    _cup_body(cr)
    cr.clip()
    grad = cairo.LinearGradient(0, top, 0, 162)
    grad.add_color_stop_rgba(0, *mascot.rgba(COFFEE_COLD if cold else COFFEE_LIGHT, alpha))
    grad.add_color_stop_rgba(1, *mascot.rgba('#4a4340' if cold else COFFEE, alpha))
    cr.rectangle(45, top, 110, 162 - top)
    cr.set_source(grad)
    cr.fill()
    if level > .02:
        _ellipse(cr, 100, top, 55, 5)
        cr.set_source_rgba(*mascot.rgba('#6b625d' if cold else COFFEE_LIGHT, alpha))
        cr.fill()
    cr.restore()
    _cup_body(cr)
    _ellipse(cr, 100, 70, 48, 8)
    cr.set_source_rgba(*mascot.rgba(BONE, alpha))
    cr.set_line_width(7)
    cr.stroke()
    cr.move_to(58, 172)
    cr.line_to(142, 172)
    cr.set_source_rgba(*mascot.rgba(BONE, .85 * alpha))
    cr.stroke()
    if fridge:
        mascot.rrect(cr, 22, 14, 156, 176, 12)
        cr.set_source_rgba(*mascot.rgba(FROST, .16 * alpha))
        cr.fill()
    cr.restore()


class HomeView:
    """Lo que guarda: `home_open` (el panel está a la vista), `home_picked` (rol elegido) y `home_all`."""

    home_open = False
    home_picked = ''
    home_all = False
    home_pane = 'agent'        # qué ocupa el contexto: agent, pomodoro, tasks o habits
    home_back = False          # el desglose se abrió desde el panel ⌂: «volver» lo reabre

    def home_main(self):
        """¿Inicio es lo que sale al abrir la isla a mano? Solo en la isla suelta."""
        return bool(self.settings['home_main']) and not self.windowed

    def toggle_home(self):
        """Abre o cierra el panel. En la ventana no hay: tiene su vista Inicio."""
        if self.windowed:
            return
        self.home_open = not self.home_open
        self.off = False
        if self.home_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.boxes_open = False
        self.ensure_tick()

    def home_cards(self):
        """Todos los agentes de la sesión de la pestaña, como los da la ventana."""
        from . import app
        if self.tab_session() is None:
            return []
        cards, free = self.window_team_cards(app)
        return cards + free

    def home_tiles(self, cards):
        """Las tarjetas a la vista y cuántas quedan en «+ n más»."""
        head, ranked = homepanel.ordered(cards, self.home_picked)
        return (ranked, 0) if self.home_all else (head, len(ranked) - len(head))

    def home_cols(self):
        return homepanel.COLS_ALL if self.home_all else homepanel.COLS

    def home_tasks(self):
        """(tareas pendientes del proyecto de Inicio, su nombre en `coffe`, la carpeta del proyecto).
        Sin carpeta, todas; con carpeta que `coffe` no conoce, ninguna."""
        _status, tasks = self.pomo_watch.read()
        root = self.window_editor_root()
        if not root:
            return tasks, '', ''
        return pomodoro.of_project(tasks, root), self.pomo_watch.project_of(root), root

    def home_goal(self):
        if self.home_pane == 'pomodoro':
            return HOME_W, HOME_HEAD + POMO_H + HOME_PAD
        cards = self.home_cards()
        shown, more = self.home_tiles(cards)
        tiles = len(shown) + (1 if more or self.home_all else 0)
        rows = max(1, -(-tiles // self.home_cols()))
        return HOME_W, HOME_HEAD + rows * (CARD_H + CARD_GAP) + CONTEXT_H + HOME_PAD

    def draw_home(self, cr, x0, w, h, alpha):
        left, width = x0 + HOME_PAD, w - 2 * HOME_PAD
        soft = mascot.rgba(self.ink('text', .62))[:3]
        head = mascot.rgba(self.ink('head'))[:3]
        cards = self.home_cards()
        if cards and (not self.home_picked or all(c['role'] != self.home_picked for c in cards)):
            first = next((c for c in cards if c['ask']), None) or next((c for c in cards if c['busy']), cards[0])
            self.home_picked = first['role']
        root = self.window_editor_root()
        title = (root.rstrip('/').rsplit('/', 1)[-1] if root else '') or 'Sin proyecto'
        self.put(cr, title.upper(), FONT_HOME_TITLE, x0 + w / 2, 12, (.95, .96, 1), alpha, align=.5)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        cx = left + width - lw
        over = self.over(cx - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, cx, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('home', ('close',), cx - 4, 10, lw + 8, lh + 8))
        for i, (key, label, kind) in enumerate(HOME_MENU):
            self.draw_home_entry(cr, key, label, kind, left, HOME_HEAD + 4 + i * 28, head, alpha)
        gx = left + HOME_MENU_W + 12
        gw = left + width - gx
        if self.home_pane == 'pomodoro':
            self.draw_home_pomodoro(cr, gx, HOME_HEAD, gw, title, head, soft, alpha)     # sin tarjetas: la taza
            return
        if not cards:
            self.put(cr, 'Sin sesiones de Claude.', FONT_HOME, gx, HOME_HEAD + 8, soft, alpha)
            return
        shown, more = self.home_tiles(cards)
        cols = self.home_cols()
        cw = (gw - (cols - 1) * CARD_GAP) / cols
        tiles = [('card', c) for c in shown] + ([('more', more)] if more or self.home_all else [])
        for i, (kind, item) in enumerate(tiles):
            x, y = gx + (i % cols) * (cw + CARD_GAP), HOME_HEAD + (i // cols) * (CARD_H + CARD_GAP)
            if kind == 'card':
                self.draw_home_card(cr, item, x, y, cw, head, soft, alpha)
            else:
                self.draw_home_more(cr, item, x, y, cw, soft, alpha)
        rows = -(-len(tiles) // cols)
        top = HOME_HEAD + rows * (CARD_H + CARD_GAP)
        picked = next((c for c in cards if c['role'] == self.home_picked), None)
        pane = {'tasks': self.draw_home_tasks, 'habits': self.draw_home_habits}
        if self.home_pane in pane:
            self.panel(cr, gx, top, gw, CONTEXT_H - 8, alpha)
            pane[self.home_pane](cr, gx + 12, top + 8, gw - 24, head, soft, alpha)
        else:
            self.draw_home_context(cr, picked, gx, top, gw, head, soft, alpha)

    def draw_home_entry(self, cr, key, label, kind, x, y, head, alpha):
        over = self.over(x - 4, y, HOME_MENU_W + 4, 24)
        if over or (kind == 'pane' and key == self.home_pane):
            mascot.box(cr, x - 4, y, HOME_MENU_W + 4, 24, 8)
            cr.set_source_rgba(*themes.glow(), .08 * alpha)
            cr.fill()
        self.put(cr, label, FONT_HOME, x + 4, y + 4, head, alpha)
        self.hits.append(('home', (kind, key), x - 4, y, HOME_MENU_W + 4, 24))

    def draw_home_card(self, cr, card, x, y, w, head, soft, alpha):
        picked = card['role'] == self.home_picked
        tint = 'yellow' if card['ask'] else mascot.accent(card['role']) if card['busy'] else None
        self.panel(cr, x, y, w, CARD_H, alpha, tint, picked or self.over(x, y, w, CARD_H))
        if picked:
            mascot.box(cr, x + .5, y + .5, w - 1, CARD_H - 1, 16)
            cr.set_source_rgba(*mascot.rgba(mascot.accent(card['role']), .8 * alpha))
            cr.set_line_width(1.2)
            cr.stroke()
        self.face(cr, card['role'], card['pet'], x + 26, y + CARD_H / 2 + 1, 38, alpha * (1 if card['busy'] else .45))
        color = mascot.rgba(card['color'])[:3] if card['busy'] else soft
        self.put(cr, card['name'], FONT_HOME, x + 50, y + 11, color, alpha, width=w - 58)
        self.put(cr, card['state'], FONT_HOME_NOTE, x + 50, y + 29, soft, alpha, width=w - 58)
        self.hits.append(('home', ('pick', card['role']), x, y, w, CARD_H))

    def draw_home_more(self, cr, more, x, y, w, soft, alpha):
        over = self.over(x, y, w, CARD_H)
        mascot.box(cr, x, y, w, CARD_H, 16)
        cr.set_source_rgba(*themes.glow(), (.12 if over else .06) * alpha)
        cr.set_dash([4, 3])
        cr.set_line_width(1)
        cr.stroke()
        cr.set_dash([])
        self.put(cr, 'Ver menos' if self.home_all else f'+ {more} más', FONT_HOME, x + w / 2, y + CARD_H / 2 - 8,
                 mascot.rgba(self.ink('head'))[:3], alpha, align=.5)
        self.hits.append(('home', ('all',), x, y, w, CARD_H))

    def draw_home_context(self, cr, card, x, y, w, head, soft, alpha):
        """Lo del elegido: su estado, sus últimos pasos y, si pide permiso, Permitir y Denegar."""
        self.panel(cr, x, y, w, CONTEXT_H - 8, alpha)
        if card is None:
            return
        self.put(cr, f'{card["name"]} · {card["state"]}', FONT_HOME, x + 12, y + 8,
                 mascot.rgba(card['color'])[:3], alpha, width=w - 24)
        lines = card['steps'][-3:] or ([] if card['busy'] else ['Libre: nada en curso.'])
        for i, line in enumerate(lines):
            self.put(cr, line, FONT_HOME_NOTE, x + 12, y + 28 + i * 15, soft, alpha, width=w - 24)
        bx, by = x + w - 12, y + CONTEXT_H - 8 - 28
        buttons = (('Permitir', ('decide', True)), ('Denegar', ('decide', False))) if card['ask'] else ()
        buttons += ((f'Chat de {card["name"]}', ('chat', card['role'])),)
        for label, key in reversed(buttons):
            lw = self._layout(cr, label, FONT_HOME_NOTE).get_pixel_size()[0] + 20
            bx -= lw
            over = self.over(bx, by, lw, 22)
            mascot.box(cr, bx, by, lw, 22, 8)
            cr.set_source_rgba(*themes.glow(), (.2 if over else .1) * alpha)
            cr.fill()
            self.put(cr, label, FONT_HOME_NOTE, bx + lw / 2, by + 5, head, alpha, align=.5)
            self.hits.append(('home', key, bx, by, lw, 22))
            bx -= 6

    def on_home_hit(self, key):
        """Un clic en el panel: cerrar, elegir un agente, ver todos, un atajo, permitir o abrir su chat."""
        from . import state
        what = key[0]
        if what == 'close':
            self.home_open = False
            if self.expanded:
                self.collapse()
        elif what == 'pick':
            self.home_picked, self.home_pane = key[1], 'agent'
            s = self.tab_session()
            self.focus = (s.sid, key[1]) if s is not None else None
            if self.focused():
                # Con pasos que leer: el desglose del tablero de siempre, y «volver» trae Inicio.
                self.home_back, self.home_open = self.home_open, False
            else:
                self.focus = None
        elif what == 'pane':
            self.home_pane = 'agent' if self.home_pane == key[1] else key[1]
        elif what == 'start':
            self.window_pomodoro('start', key[1])
        elif what == 'pomo':
            self.window_pomodoro(key[1])
        elif what == 'habit':
            habits.toggle(key[1])
        elif what == 'all':
            self.home_all = not self.home_all
        elif what == 'decide':
            self.window_decide(key[1])
        elif what == 'chat':
            s = self.tab_session()
            self.home_open = False
            if s is not None:
                self.open_chat(typing=True, agent=state.ROLE_AGENTS[key[1]], cwd=self.tab_place(s))
        elif what == 'go':
            self.home_open = False
            self.expanded = self.settings['pinned']         # Inicio era la vista de la isla abierta: sin ella, el panel que sigue
            {'chat': lambda: self.open_chat(typing=True), 'projects': self.toggle_projects,
             'boxes': self.toggle_boxes}[key[1]]()
        self.ensure_tick()

    def draw_home_buttons(self, cr, buttons, right, y, head, alpha):
        """Botones de texto pegados a `right`, de derecha a izquierda; cada uno es (texto, clave del clic)."""
        for label, key in reversed(buttons):
            lw = self._layout(cr, label, FONT_HOME_NOTE).get_pixel_size()[0] + 20
            right -= lw
            over = self.over(right, y, lw, 22)
            mascot.box(cr, right, y, lw, 22, 8)
            cr.set_source_rgba(*themes.glow(), (.2 if over else .1) * alpha)
            cr.fill()
            self.put(cr, label, FONT_HOME_NOTE, right + lw / 2, y + 5, head, alpha, align=.5)
            self.hits.append(('home', key, right, y, lw, 22))
            right -= 6

    def draw_home_pomodoro(self, cr, x, y, w, title, head, soft, alpha):
        """El Pomodoro en lugar de las tarjetas: la taza de `coffe`, el reloj y las tareas del proyecto."""
        status, _tasks = self.pomo_watch.read()
        self.panel(cr, x, y, w, POMO_H - 8, alpha)
        state, level = pomodoro.cup(status)
        draw_cup(cr, x + 10, y + 14, CUP, state, level, alpha, time.monotonic(), self.motion_reduced())
        rx = x + CUP + 24
        rw = x + w - 14 - rx
        if status is None:
            self.put(cr, 'El reloj de coffe no responde.', FONT_HOME, rx, y + 16, head, alpha, width=rw)
            self.put(cr, 'systemctl --user start coffe', FONT_HOME_NOTE, rx, y + 38, soft, alpha, width=rw)
            return
        clock = status['clock'] if status['running'] else '--:--'
        self.put(cr, clock, FONT_HOME_CLOCK, rx, y + 8, head, alpha)
        done = ' '.join('●' if i < status['cycle'] else '○' for i in range(status['cycle_of']))
        self.put(cr, f'{status["text"]} · hoy {status["today"]} · {done}', FONT_HOME_NOTE, rx, y + 48, soft, alpha, width=rw)
        self.put(cr, status['task'] or ('Tarea en el refri' if status['parked'] else 'Sin tarea en curso'),
                 FONT_HOME, rx, y + 66, head, alpha, width=rw)
        buttons = []
        if status['parked']:
            buttons.append(('Sacar del refri', ('pomo', 'resume')))
        if status['running']:
            buttons += [('Al refri', ('pomo', 'pause')), ('Tirar', ('pomo', 'void'))]
            if status['task']:
                buttons.append(('Tarea hecha', ('pomo', 'done')))
        self.draw_home_buttons(cr, buttons, rx + rw, y + 88, head, alpha)
        self.draw_home_task_rows(cr, rx, y + 122, rw, title, head, soft, alpha, POMO_ROWS)

    def draw_home_task_rows(self, cr, x, y, w, title, head, soft, alpha, rows):
        """Las tareas pendientes del proyecto: un clic empieza un pomodoro en esa."""
        tasks, project, root = self.home_tasks()
        if root and not project:
            self.put(cr, f'{title} no está en coffe. Dalo de alta con:', FONT_HOME_NOTE, x, y, soft, alpha, width=w, lines=2)
            home = os.path.expanduser('~')
            self.put(cr, f'coffe project add {title} --repo {root.replace(home, "~", 1)}', FONT_HOME_NOTE, x, y + 36, head, alpha, width=w, lines=3)
            return
        if not tasks:
            self.put(cr, f'Sin tareas pendientes en {title}.' if root else 'Sin tareas pendientes.', FONT_HOME, x, y, soft, alpha, width=w)
            return
        self.put(cr, f'TAREAS DE {title.upper()} · {len(tasks)}' if root else f'TAREAS PENDIENTES · {len(tasks)}',
                 FONT_HOME_NOTE, x, y, soft, alpha, width=w)
        for i, t in enumerate(tasks[:rows]):
            ry = y + 20 + i * 22
            if self.over(x - 4, ry - 2, w + 8, 22):
                mascot.box(cr, x - 4, ry - 2, w + 8, 22, 6)
                cr.set_source_rgba(*themes.glow(), .08 * alpha)
                cr.fill()
            self.put(cr, '▶', FONT_HOME_NOTE, x + 2, ry + 2, soft, alpha)
            self.put(cr, t['title'], FONT_HOME, x + 20, ry, head, alpha, width=w - 20 if root else w - 150)
            if not root:
                self.put(cr, t['project'], FONT_HOME_NOTE, x + w, ry + 2, soft, alpha * .9, width=120, align=1)
            self.hits.append(('home', ('start', t['id']), x - 4, ry - 2, w + 8, 22))
        if len(tasks) > rows:
            self.put(cr, f'+{len(tasks) - rows} más', FONT_HOME_NOTE, x + 20, y + 20 + rows * 22, soft, alpha * .9)

    def draw_home_tasks(self, cr, x, y, w, head, soft, alpha):
        root = self.window_editor_root()
        title = (root.rstrip('/').rsplit('/', 1)[-1] if root else '') or 'Sin proyecto'
        self.draw_home_task_rows(cr, x, y, w, title, head, soft, alpha, HABIT_ROWS)

    def draw_home_habits(self, cr, x, y, w, head, soft, alpha):
        """Los hábitos de hoy: una casilla y su racha; un clic la marca."""
        items = habits.items()
        if not items:
            self.put(cr, 'Sin hábitos. Agrega uno:', FONT_HOME, x, y, soft, alpha)
            self.put(cr, 'elyares-ctl habit add "Leer 20 min"', FONT_HOME_NOTE, x, y + 22, head, alpha)
            return
        done = sum(1 for h in items if h['done_today'])
        self.put(cr, f'HÁBITOS DE HOY · {done}/{len(items)}', FONT_HOME_NOTE, x, y, soft, alpha)
        cols = 2
        cw = w / cols
        for i, h in enumerate(items[:HABIT_ROWS * cols]):
            hx, hy = x + (i % cols) * cw, y + 20 + (i // cols) * 22
            over = self.over(hx - 4, hy - 2, cw - 4, 22)
            if over:
                mascot.box(cr, hx - 4, hy - 2, cw - 4, 22, 6)
                cr.set_source_rgba(*themes.glow(), .08 * alpha)
                cr.fill()
            self.put(cr, '☑' if h['done_today'] else '☐', FONT_HOME, hx, hy, mascot.rgba('green' if h['done_today'] else 'metal')[:3], alpha)
            self.put(cr, h['name'], FONT_HOME, hx + 20, hy, head if not h['done_today'] else soft, alpha, width=cw - 80)
            if h['streak']:
                self.put(cr, f'🔥{h["streak"]}', FONT_HOME_NOTE, hx + cw - 8, hy + 2, soft, alpha, align=1)
            self.hits.append(('home', ('habit', h['name']), hx - 4, hy - 2, cw - 4, 22))
        if len(items) > HABIT_ROWS * cols:
            self.put(cr, f'+{len(items) - HABIT_ROWS * cols} más: elyares-ctl habit list', FONT_HOME_NOTE, x,
                     y + 20 + HABIT_ROWS * 22, soft, alpha * .9, width=w)
