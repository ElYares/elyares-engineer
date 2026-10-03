"""El panel de workflows: armar una cadena de agentes, guardarla y lanzarla
sobre un proyecto sin salir de la isla.

Es un modo más de la isla, como el chat y el panel de proyectos: se abre con
la pastilla «Flujos» del pie o con `elyares-ctl workflows`, la isla crece
hasta su tamaño y lo dibuja ella, con sus enlaces, sus botones y sus caras.
Otra vez, se cierra. Abrir el chat o los proyectos lo quita de la vista; lo
que se estaba editando no se pierde, y al volver ahí sigue.

Tiene tres pantallas:

- la lista de los guardados, con «lanzar ›», «editar» y «borrar» en cada uno;
- el editor: nombre, proyecto (uno fijo o, por defecto, cualquiera: aquel
  en el que estés al lanzarlo), los pasos —agente e instrucción, que se ordenan con ↑ ↓ y se quitan
  con ✕— y qué pasa si un paso falla;
- la ejecución: los mismos pasos con cómo va cada uno (✓ ● ✗) y lo que tardó.

Los campos de texto usan la caja del chat, que es una sola (`entry`): un clic
en un campo la pone encima de él con su texto (`wf_focus`) y la isla toma el
teclado, como en el chat. Tab y Enter pasan al campo que sigue; Shift+Tab, al
anterior; Esc suelta el teclado. El agente de un paso y el proyecto se eligen
en un menú, como el de «con quién hablas» del chat.

Quién ejecuta la cadena es la isla: cada paso se le manda al chat de ese
agente en el proyecto (`chat_for`), como si se lo escribieras tú, y cuando
ese turno acaba (`workflow_event`, que llama `on_chat`) sale el siguiente con
lo que contestó el anterior. Por eso cada paso corre con los permisos de ese
chat, ni más ni menos, y se ve trabajar en el tablero como cualquier otro.
Solo corre un workflow a la vez, y no sobrevive a un reinicio de la isla.

Lo que no necesita pantalla (el workflow, el borrador, la marcha de una
ejecución) está en `workflows`. `WorkflowView` es parte de la isla
(`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

import errno
import os

import gi

gi.require_version('Gdk', '4.0')
from gi.repository import Gdk  # noqa: E402

from . import mascot, projects, state, workflows  # noqa: E402

WF_W = 600                    # el panel: el ancho del chat y del tablero
WF_PAD = 16
WF_HEAD = 48                  # su cabecera: título, nota y enlaces
WF_ROW = 32                   # una fila: un guardado, un campo, un paso
WF_LINE = 22                  # una línea de texto suelta: un título de sección, por qué no se lanza
WF_FIELD_H = 26               # la caja de un campo
WF_FIELD_INSET = 8            # dónde empieza su texto
WF_LABEL_W = 74               # el sitio de «Nombre» y «Proyecto», a la izquierda de su campo
WF_AGENT_W = 152              # el sitio del agente de un paso
WF_FACE = 22                  # la mascota de cada paso
WF_FOOT = 44                  # el pie: los botones
WF_BAR = 46                   # la barra que pregunta antes de perder algo, o dice qué no se guardó
WF_EMPTY_H = 92               # la lista vacía: qué es esto y su botón
WF_TROUBLE_H = 40             # lo que le pasó al paso que falló
WF_LIST_MOST = 12             # guardados que se ven a la vez; los demás, con la rueda
WF_MAX_STEPS = 10             # pasos que caben en la isla
WF_MENU_ROW, WF_MENU_MOST = 24, 9     # los menús: alto de cada opción y cuántas se ven
WF_PILL = 'workflows'         # la pastilla del pie que lo abre
WF_ALERT_SECS = 900           # lo que dura el aviso de que un workflow acabó
BUTTON_H = 26                 # el alto de un botón de la isla (`draw_button`)
FONT_WF_TITLE = 'Sans Semi-Bold 11'
FONT_WF_HEAD = 'Sans Semi-Bold 9'
FONT_WF = 'Sans Medium 9'
FONT_WF_NOTE = 'JetBrainsMono Nerd Font 8'
FONT_WF_FIELD = 'JetBrainsMono Nerd Font 10'      # el de la caja de texto de verdad
FONT_WF_MARK = 'Sans Semi-Bold 11'
FONT_WF_ICON = 'Sans Semi-Bold 12'           # ↑ ↓ ✕ de un paso y el ▾ de un menú: que se vean
TITLE = (.95, .96, 1)
AGENTS = tuple(state.ROLE_AGENTS[role] for role in state.TEAM)
# Cómo va un paso: (su marca, papel de su color).
MARKS = {workflows.WAIT: ('○', 'text'), workflows.RUNNING: ('●', 'cmd'),
         workflows.OK: ('✓', 'pass'), workflows.BAD: ('✗', 'bad')}


def took(secs):
    """Lo que tardó un paso, para leerlo de un vistazo."""
    if secs is None:
        return ''
    return f'{int(secs)} s' if secs < 60 else state.elapsed(secs)


def rgb(color):
    return mascot.rgba(color)[:3]


class WorkflowView:
    """Lo que guarda: `workflows` (los guardados), `wf_open`, `wf_screen`
    ('list', 'edit' o 'run'), `wf_draft` (lo que se edita), `wf_run` (la
    ejecución, en curso o la última) con `wf_chat` (el chat del paso que
    corre), `wf_field` (el campo en el que se escribe: 'name' o el número de
    un paso), `wf_menu` (el menú abierto: ('agent', paso) o ('project',)),
    `wf_confirm` (lo que se pregunta antes de perder algo) y `wf_error` (lo
    que no se pudo guardar)."""

    def workflows_init(self):
        self.workflows = workflows.load()
        self.wf_open, self.wf_screen = False, 'list'
        self.wf_draft = self.wf_run = self.wf_chat = None
        self.wf_field = self.wf_menu = None
        self.wf_loading = False       # la caja se está llenando con el texto de un campo
        self.wf_scroll = 0            # desde cuál se ve, en la lista o en el menú abierto
        self.wf_confirm = None        # ('discard', None) o ('delete', nombre)
        self.wf_menu_at = None        # dónde sale el menú abierto, del último dibujo
        self.wf_error = None          # (texto, referencia, cómo reintentar)

    # ── la ejecución: un paso tras otro, cada uno en el chat de su agente ───

    def workflow_launch(self, workflow, at=0):
        """Lanza un workflow desde su paso `at`. Con otro en curso no hace nada."""
        if self.wf_run is not None and self.wf_run.running:
            return
        self.wf_run = workflows.Run(workflow)
        if not workflow.project:
            self.wf_run.w.project = self.wf_here()      # el de cualquier proyecto corre donde estás
        self.wf_screen = 'run'
        self.workflow_step(at)

    def workflow_step(self, i):
        """Le manda al agente del paso `i` lo suyo. Si no puede ni empezar,
        sigue o se queda ahí según diga el workflow."""
        run = self.wf_run
        while i is not None:
            step, why = run.w.steps[i], ''
            if not run.w.project:
                why = 'no estás en ningún proyecto; entra a uno en tmux o abre su chat'
            elif not os.path.isdir(run.w.project):
                why = 'la carpeta del proyecto ya no existe'
            else:
                c = self.chat_for(workflows.chat_agent(step.agent), run.w.project)
                if c.busy:
                    why = 'está ocupado con otro turno'
                elif not c.send(run.prompt(i)):
                    why = 'no se pudo hablar con Claude'
            if not why:
                run.begin(i)
                self.wf_chat = c
                break
            i = run.refuse(i, why)
        else:
            self.workflow_ended()
        self.ensure_tick()

    def workflow_event(self, c, event, cut=False):
        """Lo que llega del chat del paso en curso: cuando su turno acaba, el
        paso acabó. True si con eso salió el paso siguiente."""
        run = self.wf_run
        if run is None or not run.running or c is not self.wf_chat or event.get('type') not in ('result', 'exit'):
            return False
        if event.get('type') == 'exit':
            ok, why = False, 'se quedó a medias: Claude se cerró'
        elif cut:
            ok, why = False, 'se quedó a medias: el turno se cortó'
        elif event.get('is_error'):
            ok, why = False, f"falló: {str(event.get('result') or event.get('subtype') or 'algo salió mal')[:160]}"
        else:
            # El turno acabó bien, pero el agente puede decir que su paso no salió.
            said = workflows.verdict(c.reply())
            ok, why = not said, f'no salió: {said}' if said else ''
        self.wf_chat = None
        following = run.finish(ok, c.reply(), why)
        if following is None:
            self.workflow_ended()
            self.ensure_tick()
            return False
        self.workflow_step(following)
        return run.running

    def workflow_stop(self):
        """«Detener»: corta el turno del paso en curso y no sigue."""
        run = self.wf_run
        if run is None or not run.running:
            return
        run.stopped = True
        if self.wf_chat is not None:
            self.wf_chat.interrupt()
        self.ensure_tick()

    def workflow_ended(self):
        """La ejecución se quedó ahí. Con el panel sin verla, un aviso."""
        run = self.wf_run
        if run.stopped or (self.wf_open and self.wf_screen == 'run'):
            return
        bad = run.failed
        self.model.handle({'event': 'alert', 'session_id': f'workflow:{run.w.name}',
                           'name': state.project_name(run.w.project), 'where': 'workflow',
                           'message': f'Workflow «{run.w.name}»: {run.status().lower()}',
                           'tone': 'ok' if bad is None else 'bad', 'ttl': WF_ALERT_SECS,
                           'lines': [self.workflow_trouble(bad)] if bad is not None else [],
                           'actions': [{'label': 'Ver workflow', 'workflows': True, 'after': 'clear'}]})
        self.refresh()

    def workflow_trouble(self, i):
        """Lo que le pasó al paso `i`, que falló."""
        run = self.wf_run
        return f'El paso {i + 1} ({run.w.steps[i].agent}) {run.why[i]}.'

    # ── abrir y cerrar ──────────────────────────────────────────────────────

    def toggle_workflows(self):
        if self.wf_open:
            self.close_workflows()
        else:
            self.open_workflows()

    def open_workflows(self, screen=None):
        """Abre el panel donde se dejó; con una ejecución en curso, en ella."""
        if screen is not None:
            self.wf_screen = screen
        elif self.wf_run is not None and self.wf_run.running and self.wf_draft is None:
            self.wf_screen = 'run'
        if self.wf_screen == 'edit' and self.wf_draft is None:
            self.wf_screen = 'list'
        if self.wf_screen == 'run' and self.wf_run is None:
            self.wf_screen = 'list'
        self.close_chat()
        self.projects_open, self.off = False, False
        self.wf_open, self.wf_menu, self.wf_scroll = True, None, 0
        if not self.projects:
            self.projects = projects.listing()
        self.ensure_tick()

    def close_workflows(self):
        """Quita el panel de la vista. Lo que se editaba sigue ahí al volver."""
        self.wf_focus(None)
        self.wf_open, self.wf_menu, self.wf_confirm = False, None, None
        self.ensure_tick()

    def workflows_tick(self):
        """Cada segundo, con una ejecución a la vista: lo que lleva el paso que corre."""
        run = self.wf_run
        if self.wf_open and self.wf_screen == 'run' and run is not None and run.running:
            self.ensure_tick()

    def workflows_goal(self):
        """Lo que mide la isla con el panel: según la pantalla y lo que tenga."""
        if self.wf_screen == 'edit' and self.wf_draft is not None:
            steps = len(self.wf_draft.w.steps)
            body = 2 * WF_ROW + WF_LINE + max(steps, 1) * WF_ROW + 2 * WF_ROW + WF_LINE + WF_FOOT
        elif self.wf_screen == 'run' and self.wf_run is not None:
            run = self.wf_run
            body = len(run.w.steps) * WF_ROW + (WF_TROUBLE_H if run.failed is not None else 0) + WF_FOOT
        elif self.workflows:
            body = min(len(self.workflows), WF_LIST_MOST) * WF_ROW + WF_PAD
        else:
            body = WF_EMPTY_H
        bars = sum(WF_BAR + 8 for bar in (self.wf_error, self.wf_confirm) if bar is not None)
        return WF_W, WF_HEAD + body + bars + 6

    # ── los campos de texto: la caja del chat, encima del que se escribe ────

    def wf_fields(self):
        """Los campos del editor, en su orden: el nombre y el texto de cada paso."""
        return ['name', *range(len(self.wf_draft.w.steps))] if self.wf_draft is not None else []

    def wf_text(self, field):
        w = self.wf_draft.w
        return w.name if field == 'name' else w.steps[field].text

    def wf_focus(self, field):
        """Pone la caja de texto en ese campo, con lo que ya tiene, y toma el
        teclado. Con None, lo suelta."""
        self.wf_field, self.wf_menu = field, None
        if field is None:
            if self.chat_typing and self.wf_open:
                self.chat_type(False)
            return
        self.chat_whom = ('workflow', field)      # lo escrito ya no es para el chat
        self.wf_loading = True
        self.chat_set_text(self.wf_text(field))
        self.wf_loading = False
        self.chat_type(True)

    def wf_typed(self, text):
        """Lo que se va escribiendo en la caja, a su campo. Va en una línea."""
        if self.wf_loading or self.wf_field is None or self.wf_draft is None:
            return
        text = text.replace('\n', ' ')
        if self.wf_field == 'name':
            self.wf_draft.w.name = text
        elif self.wf_field < len(self.wf_draft.w.steps):
            self.wf_draft.w.steps[self.wf_field].text = text

    def on_wf_key(self, keyval, shift):
        """Las teclas con el panel abierto: Tab y Enter, al campo que sigue;
        Shift+Tab, al anterior; Esc suelta lo que haya."""
        if keyval == Gdk.KEY_Escape:
            if self.wf_menu is not None or self.wf_confirm is not None:
                self.wf_menu = self.wf_confirm = None
            else:
                self.wf_focus(None)
            self.ensure_tick()
            return True
        back = keyval == Gdk.KEY_ISO_Left_Tab or (keyval == Gdk.KEY_Tab and shift)
        if not back and keyval not in (Gdk.KEY_Tab, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        fields = self.wf_fields()
        if self.wf_field in fields:
            at = fields.index(self.wf_field) + (-1 if back else 1)
            enter = keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
            # Enter en el último campo suelta el teclado; Tab da la vuelta.
            self.wf_focus(None if enter and at >= len(fields) else fields[at % len(fields)])
        self.ensure_tick()
        return True

    def on_wf_scroll(self, dy):
        """La rueda: la lista de guardados o, con un menú abierto, sus opciones."""
        self.wf_scroll = max(0, self.wf_scroll + (1 if dy > 0 else -1))
        self.ensure_tick()

    # ── lo que se hace desde el panel ───────────────────────────────────────

    def on_wf_hit(self, key):
        """Un clic en el panel: un enlace, un botón, un campo o una opción de un menú."""
        menu, self.wf_menu = self.wf_menu, None
        what, _, arg = key.partition(':')
        index = int(arg) if arg.isdigit() else None
        draft, run = self.wf_draft, self.wf_run
        if what == 'close':
            self.close_workflows()
        elif what == 'new':
            self.workflows_new()
        elif what == 'edit' and index < len(self.workflows):
            self.wf_draft, self.wf_screen = workflows.Draft(self.workflows[index]), 'edit'
        elif what == 'launch' and index < len(self.workflows):
            self.workflow_launch(self.workflows[index])
        elif what == 'delete' and index < len(self.workflows):
            self.wf_confirm = ('delete', self.workflows[index].name)
        elif what == 'view' or what == 'back':
            self.wf_focus(None)
            self.wf_screen, self.wf_scroll = ('run' if what == 'view' else 'list'), 0
        elif what == 'field' and draft is not None:
            self.wf_focus('name' if arg == 'name' else index)
        elif what in ('project', 'agent') and draft is not None:
            self.wf_focus(None)
            opened = ('project',) if what == 'project' else ('agent', index)
            self.wf_menu, self.wf_scroll = (None if menu == opened else opened), 0
        elif what == 'pick' and menu is not None and draft is not None:
            if menu[0] == 'agent' and menu[1] < len(draft.w.steps) and index < len(AGENTS):
                draft.w.steps[menu[1]].agent = AGENTS[index]
            elif menu[0] == 'project' and index < len(self.wf_projects()):
                draft.w.project = self.wf_projects()[index]
        elif what in ('up', 'down', 'drop', 'add') and draft is not None:
            self.wf_focus(None)
            if what == 'add':
                if len(draft.w.steps) < WF_MAX_STEPS:
                    draft.add()
                    self.wf_focus(len(draft.w.steps) - 1)
            elif what == 'drop':
                draft.remove(index)
            else:
                draft.move(index, -1 if what == 'up' else 1)
        elif what == 'fail' and draft is not None:
            draft.w.on_fail = workflows.GO if arg == workflows.GO else workflows.STOP
        elif what == 'cancel':
            self.workflows_cancel()
        elif what == 'save':
            self.workflows_save()
        elif what == 'save-launch':
            self.workflows_save(launch=True)
        elif what == 'keep':
            self.wf_confirm = None
        elif what == 'confirm' and self.wf_confirm is not None:
            self.workflows_confirmed()
        elif what == 'again' and self.wf_error is not None:
            self.wf_error[2]()
        elif what == 'chat' and run is not None:
            self.workflows_chat(self.wf_step_at())
        elif what == 'stop':
            self.workflow_stop()
        elif what == 'retry' and run is not None and not run.running:
            if run.done and run.failed is None:
                self.workflow_launch(run.w)
            else:
                self.workflow_step(self.wf_step_at())
        self.ensure_tick()

    def wf_step_at(self):
        """El paso del que se habla en la ejecución: el que corre, el que
        falló o, si no, el siguiente que falta (el último si no falta ninguno)."""
        run = self.wf_run
        if run.running:
            return run.index
        if run.failed is not None:
            return run.failed
        return next((i for i, s in enumerate(run.states) if s == workflows.WAIT), len(run.w.steps) - 1)

    def workflows_new(self):
        # Sin proyecto fijo: vale para cualquiera, y corre donde estés al lanzarlo.
        self.wf_draft = workflows.Draft()
        self.wf_screen = 'edit'
        self.wf_focus('name')

    def workflows_cancel(self):
        """«Cancelar» en el editor: a la lista, preguntando si hay cambios."""
        self.wf_focus(None)
        if self.wf_draft is not None and self.wf_draft.dirty:
            self.wf_confirm = ('discard', None)
        else:
            self.wf_draft, self.wf_screen = None, 'list'
        self.ensure_tick()

    def workflows_confirmed(self):
        """Se dijo que sí a lo que se preguntaba."""
        what, arg = self.wf_confirm
        self.wf_confirm = None
        if what == 'discard':
            self.wf_draft, self.wf_screen = None, 'list'
        elif what == 'delete':
            self.workflows_delete(arg)
        self.ensure_tick()

    def workflows_write(self, found, what, again):
        """Guarda la lista. Si no se puede, lo dice en el panel, con cómo
        reintentar, y devuelve False: lo que había en pantalla sigue ahí."""
        try:
            workflows.save(found)
        except OSError as e:
            self.wf_error = (what, errno.errorcode.get(e.errno, 'desconocido'), again)
            self.ensure_tick()
            return False
        self.workflows, self.wf_error = found, None
        return True

    def workflows_save(self, launch=False):
        """«Guardar» o «Guardar y lanzar» en el editor."""
        draft = self.wf_draft
        if draft is None or draft.name_problem(self.workflows) or (launch and self.wf_blocker()):
            return
        self.wf_focus(None)
        what = f'No pudimos guardar «{draft.w.name.strip()}». Tus pasos siguen aquí; vuelve a intentarlo.'
        if not self.workflows_write(draft.store(self.workflows), what, lambda: self.workflows_save(launch)):
            return
        draft.kept()
        saved = next(w for w in self.workflows if w.name == draft.w.name)
        self.wf_draft, self.wf_screen = None, 'list'
        if launch:
            self.workflow_launch(saved)
        self.ensure_tick()

    def workflows_delete(self, name):
        what = f'No pudimos borrar «{name}». Vuelve a intentarlo.'
        self.workflows_write([w for w in self.workflows if w.name != name], what,
                             lambda: self.workflows_delete(name))
        self.ensure_tick()

    def workflows_chat(self, i):
        """«ver su chat ›»: el del agente del paso `i`, en el proyecto del workflow."""
        run = self.wf_run
        self.open_chat(typing=True, agent=workflows.chat_agent(run.w.steps[i].agent), cwd=run.w.project)

    def wf_blocker(self):
        """Por qué no se puede guardar y lanzar todavía, o ''."""
        blocker = self.wf_draft.blocker(self.workflows)
        if not blocker and self.wf_run is not None and self.wf_run.running:
            return f'Ya corre «{self.wf_run.w.name}»: espera a que acabe o detenlo'
        return blocker

    def wf_here(self):
        """El proyecto en el que estás ahora: el de la sesión de tmux o, sin
        tmux, el del chat que se tenía a la vista. '' si no hay ninguno."""
        here = self.project_here()
        if here is not None:
            return here.path
        return state.project_root(self.chat.cwd) if self.chat is not None else ''

    def wf_projects(self):
        """Entre lo que se elige el proyecto: primero '' (cualquiera: donde
        estés al lanzarlo), luego donde estás, los abiertos en tmux y los demás."""
        paths = [p.path for p in sorted(self.projects, key=lambda p: (not p.here, not p.open, -p.activity))]
        mine = self.wf_draft.w.project if self.wf_draft is not None else ''
        return ['', *([] if not mine or mine in paths else [mine]), *paths]

    def project_label(self, path):
        p = next((p for p in self.projects if p.path == path), None)
        return p.key if p is not None else state.project_name(path) if path else 'cualquiera: donde estés al lanzarlo'

    # ── dibujo ──────────────────────────────────────────────────────────────

    def wf_link(self, cr, key, label, x, y, alpha, right=False, tone=None, on=True, font=FONT_WF_HEAD):
        """Un enlace del panel, con su clic. Con `right`, pegado a x por la
        derecha. Apagado (`on` False) se ve tenue y no hace nada. Devuelve su ancho."""
        layout = self._layout(cr, label, font)
        lw, lh = layout.get_pixel_size()
        if right:
            x -= lw
        over = on and self.over(x - 4, y - 4, lw + 8, lh + 8)
        color = (1, 1, 1) if over else tone or rgb(self.ink('text', .7))
        self.tip_text(cr, layout, x, y, color, alpha * (1 if on else .35), False)
        if on:
            self.hits.append(('wf', key, x - 4, y - 4, lw + 8, lh + 8))
        return lw

    def wf_button(self, cr, key, label, right, y, primary, alpha, on=True):
        """Un botón de la isla, tan ancho como su texto y pegado a `right`.
        Apagado se ve tenue. Devuelve dónde empieza."""
        bw = self._layout(cr, label, 'Sans Semi-Bold 10').get_pixel_size()[0] + 28
        self.draw_button(cr, f'wf-{key}', label, right - bw, y, primary, alpha * (1 if on else .35), bw)
        return right - bw

    def draw_workflows(self, cr, x0, w, h, alpha):
        left, width = x0 + WF_PAD, w - 2 * WF_PAD
        soft = rgb(self.ink('text', .62))
        draft, run = self.wf_draft, self.wf_run
        screen, self.wf_menu_at = self.wf_screen, None
        if screen == 'edit' and draft is not None:
            title, note = ('Nuevo workflow' if draft.saved_as is None else 'Editar workflow'), ''
        elif screen == 'run' and run is not None:
            title, note = run.w.name, self.project_label(run.w.project)
        else:
            screen, count = 'list', len(self.workflows)
            title, note = 'Workflows', '' if not count else '1 guardado' if count == 1 else f'{count} guardados'
        x = left + width
        x -= self.wf_link(cr, 'close', 'Cerrar', x, 14, alpha, right=True) + 14
        if screen == 'list' and self.workflows:
            x -= self.wf_link(cr, 'new', 'Nuevo', x, 14, alpha, right=True) + 14
        elif screen == 'run':
            x -= self.wf_link(cr, 'back', '‹ todos', x, 14, alpha, right=True) + 14
        tw = self.put(cr, title, FONT_WF_TITLE, left, 14, TITLE, alpha, width=x - left - 120)
        if note:
            self.put(cr, note, FONT_WF_NOTE, left + tw + 12, 17, soft, alpha, width=x - left - tw - 24)
        cr.set_source_rgba(1, 1, 1, .07 * alpha)
        cr.rectangle(left, WF_HEAD - 8, width, 1)
        cr.fill()
        draw = {'edit': self.draw_wf_editor, 'run': self.draw_wf_run, 'list': self.draw_wf_list}[screen]
        y = draw(cr, left, WF_HEAD, width, alpha)
        if self.wf_error is not None:
            what, ref, _ = self.wf_error
            y = self.draw_wf_bar(cr, left, y, width, alpha, what, f'Ref. {ref}', [('again', 'Reintentar', True)], True)
        if self.wf_confirm is not None:
            self.draw_wf_bar(cr, left, y, width, alpha, *self.wf_question())
        if self.wf_menu is not None:
            self.draw_wf_menu(cr, h, alpha)

    def draw_wf_list(self, cr, left, y, width, alpha):
        found, run = self.workflows, self.wf_run
        soft = rgb(self.ink('text', .62))
        if not found:
            self.put(cr, 'Todavía no guardaste ningún workflow. Crea uno para repetir una cadena de agentes '
                     'sin escribirla cada vez.', FONT_WF, left, y + 4, rgb(self.ink('arg')), alpha,
                     width=width, lines=2)
            bw = self._layout(cr, 'Crear workflow', 'Sans Semi-Bold 10').get_pixel_size()[0] + 28
            self.wf_button(cr, 'new', 'Crear workflow', left + bw, y + 46, True, alpha)
            return y + WF_EMPTY_H
        busy = run is not None and run.running
        self.wf_scroll = min(self.wf_scroll, max(0, len(found) - WF_LIST_MOST))
        shown = found[self.wf_scroll:self.wf_scroll + WF_LIST_MOST]
        for n, w in enumerate(shown):
            i, ry = self.wf_scroll + n, y + n * WF_ROW
            mine = run is not None and run.w.name == w.name
            if self.over(left - 4, ry, width + 8, WF_ROW - 2):
                mascot.rrect(cr, left - 4, ry, width + 8, WF_ROW - 2, 8)
                cr.set_source_rgba(1, 1, 1, .05 * alpha)
                cr.fill()
            x = left + width - 4
            x -= self.wf_link(cr, f'delete:{i}', 'borrar', x, ry + 8, alpha, right=True,
                              tone=rgb(self.ink('bad')), on=not (mine and busy)) + 14
            x -= self.wf_link(cr, f'edit:{i}', 'editar', x, ry + 8, alpha, right=True) + 14
            x -= self.wf_link(cr, f'launch:{i}', 'lanzar ›', x, ry + 8, alpha, right=True,
                              tone=rgb(self.ink('cmd')), on=bool(w.steps) and not busy) + 14
            if mine:
                x -= self.wf_link(cr, 'view', 'ver ›', x, ry + 8, alpha, right=True) + 14
            nw = self.put(cr, w.name, FONT_WF, left + 4, ry + 8, TITLE, alpha, width=(x - left) * .55)
            steps = '1 paso' if len(w.steps) == 1 else f'{len(w.steps)} pasos'
            here = self.wf_here()
            place = (self.project_label(w.project) if w.project
                     else f'donde estés (ahora {self.project_label(here)})' if here else 'donde estés')
            note = f'{steps} · {place}'       # si no cabe, se corta el sitio, no cuántos pasos
            tone = soft
            if mine:
                note += f' · {run.status().rstrip(".…").lower()}'
                tone = rgb(self.ink('cmd' if busy else 'bad' if run.failed is not None else 'pass'))
            self.put(cr, note, FONT_WF_NOTE, left + nw + 16, ry + 10, tone, alpha, width=x - left - nw - 24)
        rest = len(found) - self.wf_scroll - len(shown)
        if rest > 0:
            self.put(cr, f'↓ {rest} más', FONT_WF_NOTE, left + width, y + len(shown) * WF_ROW, soft, alpha, align=1.0)
        return y + len(shown) * WF_ROW + WF_PAD

    def draw_wf_field(self, cr, field, text, hint, x, y, width, alpha, bad=False):
        """Un campo de texto: su caja y lo que tiene. Si es en el que se
        escribe, deja su sitio (`chat_box`) para la caja de texto de verdad,
        que es la que enseña el texto."""
        active = self.wf_field == field
        mascot.rrect(cr, x, y, width, WF_FIELD_H, 8)
        cr.set_source_rgba(1, 1, 1, (.10 if active else .06) * alpha)
        cr.fill()
        if active or bad:
            mascot.rrect(cr, x + .5, y + .5, width - 1, WF_FIELD_H - 1, 8)
            cr.set_source_rgba(*rgb(self.ink('bad') if bad else mascot.accent(state.MAIN_ROLE)), .8 * alpha)
            cr.set_line_width(1)
            cr.stroke()
        line = self._layout(cr, 'X', FONT_WF_FIELD).get_pixel_size()[1]
        tx, ty, tw = x + WF_FIELD_INSET, y + (WF_FIELD_H - line) / 2, width - 2 * WF_FIELD_INSET
        if not text:
            self.put(cr, hint, FONT_WF, tx, ty + 1, (1, 1, 1), .34 * alpha, width=tw)
        elif not active:
            self.put(cr, text, FONT_WF_FIELD, tx, ty, rgb(self.ink('arg')), alpha, width=tw)
        if active:
            self.chat_box = (int(tx), int(ty), int(tw), int(line))
        name = 'name' if field == 'name' else field
        self.hits.append(('wf', f'field:{name}', x, y, width, WF_FIELD_H))

    def draw_wf_pick(self, cr, key, text, x, y, width, alpha, color=None, opened=False):
        """Lo que se elige de un menú: su texto y su ▾, con su clic. Deja
        anotado dónde sale el menú si es el abierto."""
        over = self.over(x, y, width, WF_FIELD_H)
        mascot.rrect(cr, x, y, width, WF_FIELD_H, 8)
        cr.set_source_rgba(1, 1, 1, (.11 if over or opened else .06) * alpha)
        cr.fill()
        line = self._layout(cr, 'X', FONT_WF).get_pixel_size()[1]
        self.put(cr, text, FONT_WF, x + WF_FIELD_INSET, y + (WF_FIELD_H - line) / 2,
                 color or rgb(self.ink('arg')), alpha, width=width - 2 * WF_FIELD_INSET - 12)
        self.put(cr, '▾', FONT_WF_ICON, x + width - WF_FIELD_INSET, y + (WF_FIELD_H - line) / 2 - 3,
                 rgb(self.ink('text', .62)), alpha, align=1.0)
        self.hits.append(('wf', key, x, y, width, WF_FIELD_H))
        if opened:
            self.wf_menu_at = (x, y + WF_FIELD_H + 4, y - 4, width)

    def draw_wf_editor(self, cr, left, y, width, alpha):
        draft = self.wf_draft
        head, soft = rgb(self.ink('head')), rgb(self.ink('text', .62))
        inset = (WF_ROW - WF_FIELD_H) / 2
        problem = draft.name_problem(self.workflows) if draft.w.name.strip() else ''
        self.put(cr, 'Nombre', FONT_WF_HEAD, left, y + 9, head, alpha)
        self.draw_wf_field(cr, 'name', draft.w.name, 'Cómo se llama', left + WF_LABEL_W, y + inset,
                           width - WF_LABEL_W, alpha, bad=bool(problem))
        y += WF_ROW
        self.put(cr, 'Proyecto', FONT_WF_HEAD, left, y + 9, head, alpha)
        self.draw_wf_pick(cr, 'project', self.project_label(draft.w.project), left + WF_LABEL_W, y + inset,
                          width - WF_LABEL_W, alpha, opened=self.wf_menu == ('project',))
        y += WF_ROW
        self.put(cr, 'Pasos', FONT_WF_HEAD, left, y + 5, head, alpha)
        y += WF_LINE
        if not draft.w.steps:
            self.put(cr, 'Este workflow aún no tiene pasos. Añade el primero para elegir qué agente empieza.',
                     FONT_WF, left, y + 8, rgb(self.ink('arg')), alpha, width=width)
            y += WF_ROW
        count = len(draft.w.steps)
        for i, step in enumerate(draft.w.steps):
            self.draw_wf_step(cr, i, step, count, left, y, width, alpha)
            y += WF_ROW
        add = '+ Añadir paso' if count else 'Añadir primer paso'
        self.wf_link(cr, 'add', add, left, y + 8, alpha, tone=rgb(self.ink('cmd')), on=count < WF_MAX_STEPS)
        y += WF_ROW
        x = left + self.put(cr, 'Si un paso falla', FONT_WF_HEAD, left, y + 9, head, alpha) + 14
        for value, label in ((workflows.STOP, 'parar ahí'), (workflows.GO, 'seguir con el siguiente')):
            chosen = draft.w.on_fail == value
            layout = self._layout(cr, label, FONT_WF_HEAD)
            lw, lh = layout.get_pixel_size()
            over = self.over(x, y + 4, lw + 20, WF_FIELD_H - 2)
            mascot.rrect(cr, x, y + 4, lw + 20, WF_FIELD_H - 2, (WF_FIELD_H - 2) / 2)
            tint = rgb(mascot.accent(state.MAIN_ROLE)) if chosen else (1, 1, 1)
            cr.set_source_rgba(*tint, (.24 if chosen else .11 if over else .06) * alpha)
            cr.fill()
            self.tip_text(cr, layout, x + 10, y + 4 + (WF_FIELD_H - 2 - lh) / 2, TITLE if chosen else soft, alpha, False)
            self.hits.append(('wf', f'fail:{value}', x, y + 4, lw + 20, WF_FIELD_H - 2))
            x += lw + 20 + 8
        y += WF_ROW
        # Por qué no se puede lanzar todavía, encima de los botones.
        blocker = self.wf_blocker()
        if problem or blocker:
            self.put(cr, problem or blocker, FONT_WF_NOTE, left, y + 4, rgb(self.ink('bad')) if problem else soft,
                     alpha, width=width)
        y += WF_LINE
        cr.set_source_rgba(1, 1, 1, .07 * alpha)
        cr.rectangle(left, y, width, 1)
        cr.fill()
        by = y + (WF_FOOT - BUTTON_H) / 2 + 2
        if draft.dirty:
            self.put(cr, 'Sin guardar', FONT_WF_NOTE, left, by + 7, rgb(self.ink('flag')), alpha)
        x = self.wf_button(cr, 'save-launch', 'Guardar y lanzar', left + width, by, True, alpha, on=not blocker)
        x = self.wf_button(cr, 'save', 'Guardar', x - 8, by, False, alpha,
                           on=not draft.name_problem(self.workflows))
        self.wf_link(cr, 'cancel', 'Cancelar', x - 14, by + 6, alpha, right=True)
        return y + WF_FOOT

    def draw_wf_step(self, cr, i, step, count, left, y, width, alpha):
        """Un paso del editor: su número, su mascota, su agente, lo que se le
        pide y los enlaces que lo suben, lo bajan y lo quitan."""
        inset = (WF_ROW - WF_FIELD_H) / 2
        role = state.AGENT_ROLES.get(step.agent, state.MAIN_ROLE)
        self.put(cr, str(i + 1), FONT_WF_NOTE, left + 2, y + 10, rgb(self.ink('text', .62)), alpha)
        self.face(cr, role, 'idle', left + 16 + WF_FACE / 2, y + WF_ROW / 2, WF_FACE, alpha)
        ax = left + 16 + WF_FACE + 8
        self.draw_wf_pick(cr, f'agent:{i}', step.agent, ax, y + inset, WF_AGENT_W, alpha,
                          color=rgb(mascot.accent(role)), opened=self.wf_menu == ('agent', i))
        x = left + width - 2
        for key, icon, on in (('drop', '✕', True), ('down', '↓', i + 1 < count), ('up', '↑', i > 0)):
            x -= self.wf_link(cr, f'{key}:{i}', icon, x, y + 6, alpha, right=True, on=on, font=FONT_WF_ICON) + 12
        fx = ax + WF_AGENT_W + 8
        self.draw_wf_field(cr, i, step.text, 'Qué hace en este paso', fx, y + inset, x - fx, alpha)

    def draw_wf_run(self, cr, left, y, width, alpha):
        run = self.wf_run
        soft = rgb(self.ink('text', .62))
        for i, step in enumerate(run.w.steps):
            mark, tone = MARKS[run.states[i]]
            role = state.AGENT_ROLES.get(step.agent, state.MAIN_ROLE)
            self.put(cr, mark, FONT_WF_MARK, left + 2, y + 6, soft if tone == 'text' else rgb(self.ink(tone)), alpha)
            pet = 'working' if run.states[i] == workflows.RUNNING else 'idle'
            self.face(cr, role, pet, left + 24 + WF_FACE / 2, y + WF_ROW / 2, WF_FACE, alpha)
            tw = self.put(cr, took(run.seconds(i)), FONT_WF_NOTE, left + width, y + 10, soft, alpha, align=1.0)
            ax = left + 24 + WF_FACE + 8
            aw = self.put(cr, step.agent, FONT_WF_HEAD, ax, y + 9, rgb(mascot.accent(role)), alpha, width=WF_AGENT_W)
            self.put(cr, step.text, FONT_WF, ax + aw + 10, y + 9, rgb(self.ink('arg')), alpha,
                     width=width - (ax - left) - aw - tw - 24)
            y += WF_ROW
        bad = run.failed
        if bad is not None:
            self.put(cr, self.workflow_trouble(bad) + ' Ábrelo y reintenta desde ese paso.', FONT_WF, left, y + 4,
                     rgb(self.ink('bad')), alpha, width=width, lines=2)
            y += WF_TROUBLE_H
        cr.set_source_rgba(1, 1, 1, .07 * alpha)
        cr.rectangle(left, y, width, 1)
        cr.fill()
        by = y + (WF_FOOT - BUTTON_H) / 2 + 2
        tone = 'cmd' if run.running else 'bad' if bad is not None or run.stopped else 'pass'
        if run.running:
            x = self.wf_button(cr, 'stop', 'Detener', left + width, by, False, alpha, on=not run.stopped)
        elif run.done and bad is None:
            x = self.wf_button(cr, 'retry', 'Lanzar otra vez', left + width, by, True, alpha)
        else:
            x = self.wf_button(cr, 'retry', f'Reintentar paso {self.wf_step_at() + 1}', left + width, by, True, alpha)
        x -= 14
        x -= self.wf_link(cr, 'chat', 'ver su chat ›', x, by + 6, alpha, right=True) + 14
        self.put(cr, run.status(), FONT_WF_NOTE, left, by + 7, rgb(self.ink(tone)), alpha, width=x - left)
        return y + WF_FOOT

    def wf_question(self):
        """Lo que se pregunta antes de perder algo: (texto, nota, botones, es grave)."""
        what, arg = self.wf_confirm
        if what == 'delete':
            w = next((w for w in self.workflows if w.name == arg), None)
            steps = len(w.steps) if w is not None else 0
            count = 'su paso' if steps == 1 else f'sus {steps} pasos'
            return (f'¿Borrar el workflow «{arg}» y {count}? No se puede deshacer.', '',
                    [('confirm', 'Borrar workflow', False), ('keep', 'Cancelar', True)], False)
        name = self.wf_draft.w.name.strip() if self.wf_draft is not None else ''
        where = f' en «{name}»' if name else ''
        return (f'Tienes cambios sin guardar{where}. ¿Los descartas?', '',
                [('confirm', 'Descartar cambios', False), ('keep', 'Seguir editando', True)], False)

    def draw_wf_bar(self, cr, left, y, width, alpha, text, note, buttons, bad):
        """Una barra al pie del panel: una pregunta, o lo que no se pudo
        guardar con su referencia, y sus botones. Devuelve dónde acaba."""
        mascot.rrect(cr, left, y, width, WF_BAR, 12)
        cr.set_source_rgba(*(rgb(self.ink('bad')) if bad else (1, 1, 1)), (.13 if bad else .07) * alpha)
        cr.fill()
        x = left + width - 10
        for key, label, primary in reversed(buttons):
            x = self.wf_button(cr, key, label, x, y + (WF_BAR - BUTTON_H) / 2, primary, alpha) - 8
        room = x - left - 16
        if note:
            self.put(cr, text, FONT_WF, left + 12, y + 7, rgb(self.ink('arg')), alpha, width=room)
            self.put(cr, note, FONT_WF_NOTE, left + 12, y + 26, rgb(self.ink('text', .62)), alpha, width=room)
        else:
            layout = self._layout(cr, text, FONT_WF, room, 2)
            self.tip_text(cr, layout, left + 12, y + (WF_BAR - layout.get_pixel_size()[1]) / 2,
                          rgb(self.ink('arg')), alpha, False)
        return y + WF_BAR + 8

    def draw_wf_menu(self, cr, h, alpha):
        """El menú abierto (los agentes de un paso, o los proyectos), debajo
        de lo que lo abre o encima si abajo no cabe. Sus opciones van por
        delante de lo que tapan."""
        at = self.wf_menu_at
        draft = self.wf_draft
        if at is None or draft is None:
            return
        x, below, above, width = at
        faces = self.wf_menu[0] == 'agent'
        if faces:
            step = draft.w.steps[self.wf_menu[1]] if self.wf_menu[1] < len(draft.w.steps) else None
            items = [(name, step is not None and name == step.agent) for name in AGENTS]
            width = max(width, 190)
        else:
            items = [(self.project_label(path), path == draft.w.project) for path in self.wf_projects()]
        self.wf_scroll = min(self.wf_scroll, max(0, len(items) - WF_MENU_MOST))
        shown = items[self.wf_scroll:self.wf_scroll + WF_MENU_MOST]
        mh = len(shown) * WF_MENU_ROW + 8
        y = below if below + mh <= h - 6 else max(6, above - mh)
        y = max(6, min(y, h - mh - 6))
        mascot.rrect(cr, x, y, width, mh, 10)
        cr.set_source_rgba(.07, .08, .10, .98 * alpha)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, .12 * alpha)
        cr.set_line_width(1)
        cr.stroke()
        for n, (label, chosen) in enumerate(shown):
            ry = y + 4 + n * WF_MENU_ROW
            if self.over(x + 4, ry, width - 8, WF_MENU_ROW):
                mascot.rrect(cr, x + 4, ry, width - 8, WF_MENU_ROW, 7)
                cr.set_source_rgba(1, 1, 1, .08 * alpha)
                cr.fill()
            tx, color = x + 10, TITLE if chosen else rgb(self.ink('arg'))
            if faces:
                role = state.AGENT_ROLES.get(label, state.MAIN_ROLE)
                self.face(cr, role, 'idle', x + 8 + 9, ry + WF_MENU_ROW / 2, 18, alpha)
                tx, color = x + 34, rgb(mascot.accent(role)) if chosen else color
            self.put(cr, ('✓ ' if chosen else '') + label, FONT_WF, tx, ry + 5, color, alpha, width=width - (tx - x) - 10)
            self.hits.insert(0, ('wf', f'pick:{self.wf_scroll + n}', x + 4, ry, width - 8, WF_MENU_ROW))
        if len(items) > len(shown):
            more = len(items) - self.wf_scroll - len(shown)
            self.put(cr, f'↓ {more}' if more > 0 else '↑', FONT_WF_NOTE, x + width - 8, y + mh - 16,
                     rgb(self.ink('text', .62)), alpha, align=1.0)
        # Un botón tapado por el menú no se pulsa a través de él.
        self.buttons = {key: box for key, box in self.buttons.items()
                        if not (x < box[0] + box[2] and box[0] < x + width and y < box[1] + box[3] and box[1] < y + mh)}
        self.hits.insert(len(shown), ('wf', 'menu', x, y, width, mh))     # un clic en su borde lo cierra, nada más
