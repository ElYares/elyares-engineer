"""El panel de proyectos de la isla: empezar a trabajar en cualquiera sin
abrir `claude` en una terminal.

Es el sidebar de tmux (`tmux-workspace`, Alt+b) dentro de la isla: tus
proyectos de `~/develop` agrupados por workspace, con la misma marca —un rombo
donde estás, un punto lleno si está abierto en tmux y uno hueco si está
cerrado— y, a la derecha, cómo va su Claude si tiene. Por defecto salen solo
los abiertos; «todos ›» los enseña todos, como ctrl-t allá. Un clic en uno abre
el chat en ese proyecto, listo para escribir.

Se abre con la pastilla «+» del pie o con `elyares-ctl projects`. Además, la
isla ofrece empezar en el proyecto en el que estás en tmux cuando ese no tiene
ningún Claude: en el tablero, con una pestaña fantasma (`+ proyecto`) al final
de las pestañas; sin ninguna sesión, en la cabecera («Estás en … · empezar ›»).

La lista la da `projects.listing` y se refresca sola cada PROJECTS_SECS, en un
hilo: preguntarle a tmux no frena la isla. `ProjectView` es parte de la isla
(`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

import math
import threading

from gi.repository import GLib

from . import mascot, projects, themes

PROJECTS_SECS = 3             # cada cuánto se vuelve a mirar tmux y ~/develop
PROJ_W = 600                  # el panel: el ancho del tablero
PROJ_MAX_H = 620
PROJ_PAD = 16
PROJ_HEAD = 48                # su cabecera: título, cuenta y enlaces
PROJ_FOOT = 30                # la leyenda de las marcas
PROJ_ROW = 20
PROJ_COLS = 3
PROJ_GAP = 12                 # entre columnas
PROJECTS_PILL = 'projects'    # la pastilla «+» del pie
FONT_PROJ = 'Sans Medium 9'
FONT_PROJ_HEAD = 'Sans Semi-Bold 9'
FONT_PROJ_NOTE = 'JetBrainsMono Nerd Font 8'
FONT_PROJ_TITLE = 'Sans Semi-Bold 11'
AMBER = (.96, .76, .36)       # donde estás: el mismo ámbar del sidebar
# Cómo va el Claude de un proyecto: (lo que se lee, papel de su color).
CLAUDE_NOTES = {'permission': ('permiso', 'bad'), 'working': ('trabaja', 'cmd'), 'done': ('listo', 'pass'),
                'waiting': ('espera', 'flag')}
CLAUDE_RANK = ('permission', 'working', 'waiting', 'done')


class ProjectView:
    """Lo que guarda: `projects` (la lista, de `projects.listing`),
    `projects_open` (el panel está a la vista), `projects_all` (enseña también
    los cerrados) y `projects_due` (cuándo toca volver a mirar)."""

    def projects_init(self):
        self.projects = []
        self.projects_open = self.projects_all = False
        self.projects_due = 0

    # ── la lista ────────────────────────────────────────────────────────────

    def projects_tick(self, seconds):
        """Cada segundo: si toca, vuelve a mirar tmux y `~/develop` en un hilo."""
        if seconds >= self.projects_due:
            self.projects_due = seconds + PROJECTS_SECS
            threading.Thread(target=lambda: GLib.idle_add(self.on_projects, projects.listing()),
                             daemon=True, name='proyectos').start()

    def on_projects(self, found):
        if found != self.projects:
            self.projects = found
            self.refresh()
            self.ensure_tick()
        return GLib.SOURCE_REMOVE

    def project_here(self):
        """El proyecto de la sesión de tmux en la que estás, o None."""
        return next((p for p in self.projects if p.here), None)

    def project_of(self, cwd):
        """El proyecto de una carpeta: el más concreto que la contiene. Una
        sesión de tmux abierta en tu carpeta personal no se queda con lo de
        los proyectos que cuelgan de ella."""
        return max((p for p in self.projects if p.holds(cwd)), key=lambda p: len(p.path), default=None)

    def project_sessions(self, p):
        """Las sesiones de Claude de ese proyecto. La de un chat es del
        proyecto en el que se empezó, ande por donde ande ahora."""
        return [s for s in self.claude() if self.project_of(self.tab_place(s)) is p]

    def project_claude(self, p):
        """Cómo va el Claude de un proyecto, como (texto, papel de su color),
        o None si no tiene ni sesión ni conversación."""
        states = {s.state for s in self.project_sessions(p)}
        for name in CLAUDE_RANK:
            if name in states:
                return CLAUDE_NOTES[name]
        chats = [c for c in self.all_chats() if self.project_of(c.cwd) is p]
        if any(c.busy for c in chats):
            return CLAUDE_NOTES['working']
        if states or any(c.session or c.entries for c in chats):
            return 'chat' if not states else 'reposo', 'text'
        return None

    def project_start(self):
        """El proyecto en el que estás en tmux, si aún no tiene ningún Claude:
        es el que la isla ofrece para empezar. None si no hay o ya tiene."""
        here = self.project_here()
        if here is None or self.project_sessions(here):
            return None
        return here

    def start_in(self, path):
        """Empieza a trabajar en ese proyecto: su chat, listo para escribir."""
        self.projects_open = False
        self.open_chat(typing=True, cwd=path)

    def toggle_projects(self):
        self.projects_open = not self.projects_open
        self.off = False
        if self.projects_open:
            self.close_chat()
            self.projects_due = 0       # al abrirlo, lo de ahora
        self.ensure_tick()

    # ── el panel ────────────────────────────────────────────────────────────

    def project_items(self):
        """Las filas del panel, en el orden del sidebar: ('h', workspace,
        «abiertos/total») y ('p', proyecto). Sin `projects_all`, solo los
        abiertos en tmux o con un Claude, y solo los workspaces con alguno."""
        groups = {}
        for p in self.projects:
            groups.setdefault(p.ws or projects.LOOSE, []).append(p)
        items = []
        for ws, members in groups.items():
            shown = [p for p in members if self.projects_all or p.open or self.project_claude(p)]
            if not shown:
                continue
            count = '' if ws == projects.LOOSE else f'{sum(p.open for p in members)}/{len(members)}'
            items.append(('h', ws, count))
            items += [('p', p, None) for p in shown]
        return items

    def project_columns(self, items=None):
        """Las filas repartidas en columnas, sin dejar una cabecera sola al
        pie de una: ([columnas], filas de la más larga)."""
        items = self.project_items() if items is None else items
        most = (PROJ_MAX_H - PROJ_HEAD - PROJ_FOOT) // PROJ_ROW
        cols = PROJ_COLS
        while True:
            per = max(1, math.ceil(len(items) / cols))
            while per <= most:
                columns = [[]]
                for item in items:
                    full = len(columns[-1]) >= per
                    orphan = item[0] == 'h' and len(columns[-1]) == per - 1
                    if columns[-1] and (full or orphan):
                        columns.append([])
                    columns[-1].append(item)
                if len(columns) <= cols:
                    return columns, max(len(c) for c in columns)
                per += 1
            cols += 1                   # no caben: más columnas, más estrechas

    def projects_goal(self):
        columns, per = self.project_columns()
        return PROJ_W, PROJ_HEAD + max(per, 3) * PROJ_ROW + PROJ_FOOT

    def draw_projects(self, cr, x0, w, h, alpha):
        left, width = x0 + PROJ_PAD, w - 2 * PROJ_PAD
        items = self.project_items()
        soft = mascot.rgba(self.ink('text', .62))[:3]
        opened, total = sum(p.open for p in self.projects), len(self.projects)
        tw = self.put(cr, 'Proyectos', FONT_PROJ_TITLE, left, 14, (.95, .96, 1), alpha)
        self.put(cr, f'{opened} abiertos en tmux, de {total}', FONT_PROJ_NOTE, left + tw + 12, 17, soft, alpha)
        x = left + width
        for key, label in (('close', 'Cerrar'), ('all', 'solo abiertos ›' if self.projects_all else 'todos ›')):
            layout = self._layout(cr, label, 'Sans Semi-Bold 9')
            lw, lh = layout.get_pixel_size()
            x -= lw
            over = self.over(x - 4, 10, lw + 8, lh + 8)
            self.tip_text(cr, layout, x, 14, (1, 1, 1) if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
            self.hits.append(('projects', key, x - 4, 10, lw + 8, lh + 8))
            x -= 14
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, PROJ_HEAD - 8, width, 1)
        cr.fill()
        if not items:
            text = 'Sin proyectos abiertos en tmux · «todos ›» los enseña todos' if self.projects else 'Buscando…'
            self.put(cr, text, FONT_PROJ, left, PROJ_HEAD + 8, soft, alpha, width=width)
        columns, _ = self.project_columns(items)
        cw = (width - PROJ_GAP * (len(columns) - 1)) / len(columns)
        for n, column in enumerate(columns):
            cx = left + n * (cw + PROJ_GAP)
            for i, (kind, value, count) in enumerate(column):
                y = PROJ_HEAD + i * PROJ_ROW
                if kind == 'h':
                    hw = self.put(cr, value, FONT_PROJ_HEAD, cx, y + 3, mascot.rgba(self.ink('head'))[:3], alpha,
                                  width=cw - 40)
                    if count:
                        self.put(cr, count, FONT_PROJ_NOTE, cx + hw + 8, y + 5, soft, alpha)
                else:
                    self.draw_project(cr, value, cx, y, cw, alpha)
        self.draw_project_legend(cr, left, h - PROJ_FOOT + 9, width, alpha * .9)

    def draw_project(self, cr, p, x, y, w, alpha):
        """Un proyecto: su marca, su nombre y, a la derecha, cómo va su Claude."""
        if self.over(x - 4, y, w + 8, PROJ_ROW):
            mascot.rrect(cr, x - 4, y, w + 8, PROJ_ROW, 6)
            cr.set_source_rgba(*themes.glow(), .08 * alpha)
            cr.fill()
        self.project_mark(cr, p, x + 10, y + PROJ_ROW / 2, alpha)
        note = self.project_claude(p)
        nw = 0
        if note:
            nw = self.put(cr, note[0], FONT_PROJ_NOTE, x + w, y + 4, mascot.rgba(self.ink(note[1]))[:3], alpha,
                          align=1.0) + 8
        color = (1, 1, 1) if p.here else (.86, .88, .94) if p.open else (.5, .54, .66)
        self.put(cr, p.name, FONT_PROJ, x + 22, y + 3, color, alpha, width=w - 22 - nw)
        self.hits.append(('project', p.path, x - 4, y, w + 8, PROJ_ROW))

    @staticmethod
    def project_mark(cr, p, cx, cy, alpha):
        """La marca del sidebar: rombo donde estás, punto lleno si está
        abierto en tmux, hueco si está cerrado."""
        cr.new_sub_path()
        if p.here:
            cr.move_to(cx, cy - 4.5)
            for dx, dy in ((4.5, 0), (0, 4.5), (-4.5, 0)):
                cr.line_to(cx + dx, cy + dy)
            cr.close_path()
            cr.set_source_rgba(*AMBER, alpha)
            cr.fill()
        elif p.open:
            cr.arc(cx, cy, 3.2, 0, 2 * math.pi)
            cr.set_source_rgba(*mascot.rgba('green', alpha))
            cr.fill()
        else:
            cr.arc(cx, cy, 3, 0, 2 * math.pi)
            cr.set_source_rgba(*mascot.rgba('metal', .6 * alpha))
            cr.set_line_width(1.3)
            cr.stroke()

    def draw_project_legend(self, cr, left, y, width, alpha):
        soft = mascot.rgba(self.ink('text', .55))[:3]
        x = left + 4
        for sample, label in ((projects.Project('', '', here=True, session='x'), 'donde estás en tmux'),
                              (projects.Project('', '', session='x'), 'abierto'),
                              (projects.Project('', ''), 'cerrado')):
            self.project_mark(cr, sample, x + 5, y + 7, alpha)
            x += 14 + self.put(cr, label, FONT_PROJ_NOTE, x + 14, y, soft, alpha) + 16
        self.put(cr, 'clic: su chat, listo para escribir', FONT_PROJ_NOTE, left + width, y, soft, alpha, align=1.0)

    def on_project_hit(self, kind, key):
        """Un clic en el panel, en la pestaña fantasma o en «empezar ›»."""
        if kind == 'projects':
            if key == 'all':
                self.projects_all = not self.projects_all
            elif key == 'close':
                self.projects_open = False
            else:
                self.toggle_projects()
        elif kind in ('project', 'start'):
            self.start_in(key)
        self.ensure_tick()

    # ── empezar donde estás ─────────────────────────────────────────────────

    def start_text(self):
        """Lo que dice la cabecera cuando no hay ninguna sesión y estás en un
        proyecto en tmux; '' si no hay nada que ofrecer."""
        here = self.project_start()
        return f'Estás en {here.name} · empezar ›' if here is not None else ''
