"""La vista Tareas de la ventana: las tareas de `coffe` como un ToDo por proyectos.

Una sección por proyecto (se pliega con un clic) y una fila por tarea: casilla para darla por
hecha, prioridad, título, pomodoros y ▶ para empezar uno (o «Empezar con agente», que además abre
el chat en la carpeta del proyecto). Filtros Pendientes / Hechas / Todas y un buscador. Sin estado
de `coffe` propio: la llena la ventana con `set_tasks` y los botones llaman a los `handlers`.
Mientras `coffe` no contesta dice «Preguntando a coffe…», y si falla lo dice con «Reintentar».
"""

from gi.repository import GLib, Gtk, Pango

from . import pomodoro, themes, windowframe
from .windowframe import SPACE, load_css

FILTERS = (('open', 'Pendientes'), ('done', 'Hechas'), ('all', 'Todas'))
STATES = {'open': pomodoro.OPEN_STATES, 'done': (pomodoro.DONE,), 'all': pomodoro.ALL_STATES}
MARKS = pomodoro.MARKS
EMPTY = {'open': 'Nada pendiente. 🎉', 'done': 'Todavía no hay tareas hechas.', 'all': pomodoro.EMPTY_ALL}
LOADING = 'Preguntando a coffe…'


class TasksPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        load_css()
        self.add_css_class('elyares-sources')
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self, f'set_margin_{side}')(SPACE[2])
        self.mode = 'open'
        self.query = ''
        self.collapsed = set()          # proyectos con la sección cerrada
        self.signature = None
        self.last = None
        self.focusables = {}            # clave → control de la lista: el foco vuelve a él al rehacerla
        title = Gtk.Label(label='Tareas', xalign=0)
        title.add_css_class('elyares-title')
        self.summary = Gtk.Label(xalign=0)
        self.summary.add_css_class('elyares-muted')
        top = Gtk.Box(spacing=SPACE[1])
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        head.set_hexpand(True)
        head.append(title)
        head.append(self.summary)
        top.append(head)
        chips = Gtk.Box(spacing=2)
        chips.add_css_class('elyares-segments')
        first = None
        for key, text in FILTERS:
            btn = Gtk.ToggleButton(label=text)
            if first is None:
                first = btn
            else:
                btn.set_group(first)
            btn.set_active(key == self.mode)
            btn.connect('toggled', self._filter, key)
            chips.append(btn)
        top.append(chips)
        self.search = Gtk.SearchEntry(placeholder_text='Buscar tarea o proyecto')
        self.search.connect('search-changed', self._search)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[1])
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(self.page)
        self.append(top)
        self.append(self.search)
        self.append(scroll)
        self.set_visible(False)

    def _filter(self, btn, key):
        if btn.get_active():
            self.mode = key
            self._again()

    def _search(self, entry):
        self.query = entry.get_text()
        self._again()

    def _again(self):
        self.signature = None
        if self.last is not None:
            self.set_tasks(*self.last)

    def set_tasks(self, tasks, handlers, load=('ok', '')):
        """`tasks`: lo de `Watcher.read_all` (con `repo`). `handlers`: act(orden, *args), agent(id, repo),
        retry() para «Reintentar». `load`: lo de `Watcher.tasks_state()`, (loading|error|ok, por qué)."""
        self.last = (tasks, handlers, load)
        sig = (self.mode, self.query, tuple(sorted(self.collapsed)), load, themes.current,
               tuple(tuple(sorted(t.items())) for t in tasks))        # todo lo que se pinta: repo, prioridad, estimado…
        if sig == self.signature:
            return
        self.signature = sig
        held = windowframe.focused_key(self.focusables)
        self.focusables = {}
        while (child := self.page.get_first_child()) is not None:
            self.page.remove(child)
        if load[0] != 'ok':
            self._status(load, handlers)
            windowframe.refocus(self.focusables, held)
            return
        groups = pomodoro.by_project(tasks, STATES[self.mode], self.query)
        total = sum(len(items) for _name, items in groups)
        self.summary.set_label(f'{total} {"tarea" if total == 1 else "tareas"} en {len(groups)} '
                               f'{"proyecto" if len(groups) == 1 else "proyectos"}')
        if not groups:
            note = Gtk.Label(label='Nada coincide con la búsqueda.' if self.query.strip() else EMPTY[self.mode],
                             xalign=0, wrap=True, selectable=True)
            note.add_css_class('elyares-muted')
            self.page.append(note)
            return
        for name, items in groups:
            self.page.append(self._group(name, items, handlers))
        windowframe.refocus(self.focusables, held)

    def _status(self, load, handlers):
        """Cargando o error: qué pasa y, si falló, cómo arrancarlo y un «Reintentar»."""
        state, why = load
        self.summary.set_label('' if state == 'loading' else 'coffe no contesta')
        if state == 'loading':
            text = LOADING
        elif 'No está instalado' in why:
            text = 'No está instalado coffe, el pomodoro: sin él no hay tareas.'
        else:
            text = f'coffe no contesta ({why}). Arráncalo con: systemctl --user start coffe'
        note = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True)
        note.add_css_class('elyares-muted')
        self.page.append(note)
        if state == 'error' and 'retry' in handlers:
            again = Gtk.Button(label='Reintentar')
            again.add_css_class('elyares-btn')
            again.set_halign(Gtk.Align.START)
            again.connect('clicked', lambda _b: handlers['retry']())
            self.focusables['retry'] = again
            self.page.append(again)

    def _group(self, name, items, handlers):
        shut = name in self.collapsed
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        head = Gtk.Button()
        head.add_css_class('elyares-pill')
        label = Gtk.Label(xalign=0)
        label.set_markup(f'{"▸" if shut else "▾"}  <b>{GLib.markup_escape_text(name)}</b>'
                         f'  <span foreground="{windowframe.MUTED}">{len(items)}</span>')     # el del tema de ahora
        head.set_child(label)
        head.update_state([Gtk.AccessibleState.EXPANDED], [int(not shut)])     # «boolean o indefinido»: va como int
        head.connect('clicked', lambda _b, n=name: self._fold(n))
        self.focusables[('fold', name)] = head
        box.append(head)
        if not shut:
            for task in items:
                box.append(self._row(task, handlers))
        return box

    def _fold(self, name):
        self.collapsed ^= {name}
        self._again()

    def _row(self, task, handlers):
        done, live = task['state'] == pomodoro.DONE, task['state'] == pomodoro.LIVE
        row = Gtk.Box(spacing=SPACE[1])
        row.add_css_class('elyares-card')
        check = Gtk.CheckButton()
        check.set_active(done)
        check.update_property([Gtk.AccessibleProperty.LABEL],
                              [f'{"Reabrir" if done else "Dar por hecha"}: {task["title"]}'])
        check.connect('toggled', self._check, task, handlers)
        self.focusables[('check', task['id'])] = check
        row.append(check)
        mark = Gtk.Label(label=MARKS.get(task['priority'], '·'))
        mark.set_tooltip_text(f'Prioridad {task["priority"]}')
        mark.update_property([Gtk.AccessibleProperty.LABEL], [f'Prioridad {task["priority"]}'])
        mark.add_css_class('elyares-muted')
        row.append(mark)
        title = Gtk.Label(label=task['title'], xalign=0, ellipsize=Pango.EllipsizeMode.END)
        title.set_hexpand(True)
        if done:
            title.add_css_class('elyares-muted')
        row.append(title)
        if live or task['state'] == pomodoro.PARKED:
            green, amber, _red = themes.signal()            # aviso: no del tema, pero legible en claro y oscuro
            state = Gtk.Label()
            state.set_markup(f'<span foreground="{green if live else amber}">'
                             f'{"● en curso" if live else "❄ en el refri"}</span>')
            row.append(state)
        pomos = Gtk.Label(label=f'{task["done"]}/{task["estimate"]}' if task['estimate'] else str(task['done']))
        pomos.add_css_class('elyares-muted')
        pomos.set_tooltip_text('Pomodoros hechos / estimados')
        row.append(pomos)
        if not done and not live:
            start = Gtk.Button(label='▶')
            start.add_css_class('elyares-btn')
            start.add_css_class('compact')
            start.set_tooltip_text('Empezar un pomodoro en esta tarea')
            start.update_property([Gtk.AccessibleProperty.LABEL], [f'Empezar un pomodoro en {task["title"]}'])
            start.connect('clicked', lambda _b, t=task: handlers['act']('start', t['id']))
            self.focusables[('start', task['id'])] = start
            row.append(start)
            if task.get('repo') and 'agent' in handlers:
                agent = Gtk.Button(label='Empezar con agente')
                agent.add_css_class('elyares-btn')
                agent.add_css_class('compact')
                agent.set_tooltip_text('Empieza un pomodoro y abre el chat en la carpeta del proyecto')
                agent.update_property([Gtk.AccessibleProperty.LABEL], [f'Empezar {task["title"]} con un agente'])
                agent.connect('clicked', lambda _b, t=task: handlers['agent'](t['id'], t['repo']))
                self.focusables[('agent', task['id'])] = agent
                row.append(agent)
        return row

    def _check(self, box, task, handlers):
        """Dar por hecha o reabrir. La casilla ya cambió en pantalla antes que `coffe`: se olvida la
        firma para que la próxima lectura la rehaga con lo que `coffe` diga (si se negó, vuelve atrás)."""
        handlers['act']('task', 'done' if box.get_active() else 'reopen', task['id'])
        self.signature = None
