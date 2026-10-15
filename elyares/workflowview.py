"""El panel de workflows: armar una cadena de agentes, guardarla y lanzarla
sobre un proyecto sin salir de la isla.

Es una isla aparte, junto a la de siempre: se abre con la pastilla «Flujos»
del pie o con `elyares-ctl workflows`, y sale pegada a la isla, a su
izquierda, con su misma forma, su fondo (translúcido en modo vidrio), sus
enlaces, sus botones y sus caras. La isla de siempre sigue a lo suyo: el
tablero y el chat no se mueven. Otra vez la orden, o «Cerrar», la quita.

- **Del lado contrario si no cabe.** Sale a la izquierda de la isla; si esa
  está corrida hasta el tope izquierdo de la pantalla y no hay sitio, sale a
  la derecha (`flows_side`). Sigue a la isla mientras se mueve o cambia de
  tamaño.
- **Se puede colapsar.** «colapsar» la deja en una pastilla (`Flujos` y cómo
  va lo que corre), y un clic en ella la abre otra vez. Se acuerda
  (`flows_collapsed` en `settings.json`).

Es una ventana de layer-shell que cruza la pantalla de lado a lado, transparente
como la de la isla, con una región de entrada que sigue solo a la isla de los
flujos: fuera de ella los clics pasan a las ventanas de abajo. Se crea la
primera vez que se abre (`flows_window`).

Tiene tres pantallas:

- la lista de los guardados, con «lanzar ›», «editar» y «borrar» en cada uno;
- el editor: nombre, proyecto (uno fijo o, por defecto, cualquiera: aquel
  en el que estés al lanzarlo), los pasos —agente e instrucción, que se
  ordenan con ↑ ↓ y se quitan con ✕— y qué pasa si un paso falla;
- la ejecución: los mismos pasos con cómo va cada uno (✓ ● ✗) y lo que tardó.

Los campos de texto usan una caja propia (`wf_entry`, una sola línea) que se
pone encima del campo en el que se escribe (`wf_focus`); la ventana toma
entonces el teclado, como el chat. Tab y Enter pasan al campo que sigue;
Shift+Tab, al anterior; Esc lo suelta. El agente de un paso y el proyecto se
eligen en un menú, como el de «con quién hablas» del chat.

Quién ejecuta la cadena es la isla: cada paso se le manda al chat de ese
agente en el proyecto (`chat_free`: la de siempre y, si trabaja, otra libre
o una nueva), como si se lo escribieras tú, y cuando
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
import time

import cairo
import gi

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from . import mascot, paint, projects, settings, state, workflows  # noqa: E402

WF_W = 600                    # la isla de los flujos, abierta: el ancho del chat y del tablero
WF_WIN_H = 760                # alto de su ventana: lo más alto que llega (el editor con diez pasos)
WF_PILL_W, WF_PILL_H = 176, 34    # colapsada
WF_GAP = 6                    # entre ella y la isla de siempre
WF_EDGE = 8                   # lo que se deja al borde de la pantalla
WF_SPRING_K, WF_SPRING_C = 220.0, 22.0    # los de la isla: rebota un poquito
WF_IDLE_SECS = 90             # sin teclear tanto rato, suelta el teclado (como el chat)
WF_SIDES = {'left': '›', 'right': '‹'}    # hacia dónde se colapsa, según el lado en que sale
WF_GLASS_EDGE = .16           # el filo claro del vidrio (`app.GLASS_EDGE`)
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
WF_GLASS_ALPHA = .7           # el menú abierto, en vidrio: como la burbuja de una fuente (`app.TIP_GLASS_ALPHA`)
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


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class WorkflowView:
    """Lo que guarda: `workflows` (los guardados), `wf_open`, `wf_screen`
    ('list', 'edit' o 'run'), `wf_draft` (lo que se edita), `wf_run` (la
    ejecución, en curso o la última) con `wf_chat` (el chat del paso que
    corre), `wf_field` (el campo en el que se escribe: 'name' o el número de
    un paso), `wf_menu` (el menú abierto: ('agent', paso) o ('project',)),
    `wf_confirm` (lo que se pregunta antes de perder algo) y `wf_error` (lo
    que no se pudo guardar), `wf_collapsed` (está en su pastilla) y, de su
    ventana, `flows_win`, `flows_da` y `wf_entry`, con `fw`/`fh` (lo que mide
    ahora la isla, que rebota hasta su tamaño) y `wf_hits`/`wf_buttons` (lo
    que se puede pulsar, del último dibujo)."""

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
        self.wf_collapsed = bool(self.settings.get('flows_collapsed'))
        self.flows_win = self.flows_da = self.wf_entry = self.wf_entry_box = self.flows_overlay = None
        self.fw, self.fh, self.fvw, self.fvh = float(WF_PILL_W), 0.0, 0.0, 0.0
        self.fticking, self.flast = False, None
        self.wf_hits, self.wf_buttons, self.wf_pointer = [], {}, None
        self.wf_box = None            # dónde va el texto de la caja, como lo midió el último dibujo
        self.wf_typing, self.wf_keyed = False, 0.0
        self.wf_side, self.wf_region = 'left', None

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
                c = self.chat_free(workflows.chat_agent(step.agent), run.w.project)
                if c.busy:
                    why = 'está ocupado con otro turno'
                elif not c.send(run.prompt(i), shown=run.shown(i), kind='flow'):
                    why = 'no se pudo hablar con Claude'
            if not why:
                run.begin(i)
                self.wf_chat = c
                break
            i = run.refuse(i, why)
        else:
            self.workflow_ended()
        self.wf_redraw()

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
            self.wf_redraw()
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
        self.wf_redraw()

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
        """Abre la isla de los flujos donde se dejó; con una ejecución en
        curso, en ella. Si estaba colapsada, se queda así."""
        if screen is not None:
            self.wf_screen = screen
        elif self.wf_run is not None and self.wf_run.running and self.wf_draft is None:
            self.wf_screen = 'run'
        if self.wf_screen == 'edit' and self.wf_draft is None:
            self.wf_screen = 'list'
        if self.wf_screen == 'run' and self.wf_run is None:
            self.wf_screen = 'list'
        if screen is not None and self.wf_collapsed:
            self.wf_collapse(False)             # lo piden para verlo: un aviso, «Ver»…
        self.wf_open, self.wf_menu, self.wf_scroll = True, None, 0
        if not self.projects:
            self.projects = projects.listing()
        win = self.flows_window()
        if win is not None:
            if self.windowed:
                if self.chat_typing:
                    self.chat_type(False)       # el teclado es de la caja del panel, no de la del chat
                self.flows_dock()
            else:
                self.flows_monitor()
                win.set_visible(True)
        self.wf_redraw()

    def close_workflows(self):
        """Quita la isla de los flujos. Lo que se editaba sigue ahí al volver."""
        self.wf_focus(None)
        self.wf_open, self.wf_menu, self.wf_confirm = False, None, None
        self.flows_dock()
        self.wf_redraw()

    def wf_collapse(self, on):
        """La deja en su pastilla, o la abre otra vez. Se acuerda."""
        self.wf_focus(None)
        self.wf_collapsed, self.wf_menu = bool(on), None
        self.settings['flows_collapsed'] = self.wf_collapsed
        settings.save(self.settings)
        self.wf_redraw()

    def wf_pill(self):
        """¿Se ve como pastilla? En la ventana de la app no hay pastilla: es
        el panel entero o nada."""
        return self.wf_collapsed and not self.windowed

    def workflows_tick(self):
        """Cada segundo: suelta el teclado si hace rato que no se teclea y, con
        una ejecución a la vista, lo que lleva el paso que corre."""
        if self.wf_typing and time.monotonic() - self.wf_keyed > WF_IDLE_SECS:
            self.wf_focus(None)
        run = self.wf_run
        if self.wf_open and run is not None and run.running:
            self.wf_redraw()

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

    def flows_goal(self):
        """Lo que mide la isla de los flujos ahora: su pastilla, su panel, o
        nada (sin alto) si está cerrada."""
        if not self.wf_open:
            return self.fw, 0
        return (WF_PILL_W, WF_PILL_H) if self.wf_pill() else self.workflows_goal()

    # ── los campos de texto: una caja propia, encima del que se escribe ─────

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
            self.wf_type(False)
            return
        self.wf_loading = True
        self.wf_entry_set(self.wf_text(field))
        self.wf_loading = False
        self.wf_type(True)

    def wf_type(self, on):
        """La ventana de los flujos toma el teclado para escribir, o lo suelta."""
        self.wf_typing = bool(on) and self.wf_open
        self.wf_keyed = time.monotonic()
        if self.flows_win is not None:
            if not self.windowed:
                LayerShell.set_keyboard_mode(
                    self.flows_win, LayerShell.KeyboardMode.ON_DEMAND if self.wf_typing else LayerShell.KeyboardMode.NONE)
            if self.wf_typing and self.wf_entry_box is not None and self.wf_entry_box.get_visible():
                self.wf_entry.grab_focus()         # si no, lo hace `wf_place_entry` al ponerla en su sitio
        self.wf_redraw()

    def wf_entry_set(self, text):
        if self.wf_entry is not None:
            buf = self.wf_entry.get_buffer()
            buf.set_text(text)
            buf.place_cursor(buf.get_end_iter())

    def wf_entry_text(self):
        buf = self.wf_entry.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

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
            self.wf_redraw()
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
        self.wf_redraw()
        return True

    def on_wf_scroll(self, dy):
        """La rueda: la lista de guardados o, con un menú abierto, sus opciones."""
        self.wf_scroll = max(0, self.wf_scroll + (1 if dy > 0 else -1))
        self.wf_redraw()

    # ── la isla de los flujos: su ventana, su sitio y su forma ───────────────

    def flows_window(self):
        """Su ventana de layer-shell, de lado a lado de la pantalla y
        transparente, con el dibujo y la caja de texto dentro. None si aún no
        hay aplicación (las pruebas)."""
        if self.flows_win is not None:
            return self.flows_win
        app = getattr(self, 'gtk_app', None)
        if app is None:
            return None
        win = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(win)
        # El mismo nombre que la isla: la regla de Hyprland que desenfoca el vidrio es por nombre
        # entero (`match:namespace elyares`), y con otro la isla de los flujos quedaría sin desenfoque.
        LayerShell.set_namespace(win, 'elyares')
        LayerShell.set_layer(win, LayerShell.Layer.TOP)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(win, edge, True)
        LayerShell.set_exclusive_zone(win, 0)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
        win.set_default_size(640, WF_WIN_H)
        da = Gtk.DrawingArea()
        da.set_content_height(WF_WIN_H)
        da.set_draw_func(self.flows_draw)
        motion = Gtk.EventControllerMotion()
        motion.connect('motion', self.on_flows_motion)
        motion.connect('leave', lambda *_: self.on_flows_motion(None, None, None))
        da.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect('pressed', self.on_flows_click)
        da.add_controller(click)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', lambda _c, _dx, dy: self.on_flows_scroll(dy))
        da.add_controller(scroll)
        # La caja de texto, de una sola línea, va encima del dibujo.
        view = Gtk.TextView()
        view.add_css_class('elyares-chat')
        view.set_wrap_mode(Gtk.WrapMode.NONE)
        view.set_accepts_tab(False)
        view.get_buffer().connect('changed', lambda buf: self.wf_typed(self.wf_entry_text()))
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.on_wf_entry_key)
        view.add_controller(keys)
        box = Gtk.ScrolledWindow()
        box.add_css_class('elyares-chat')
        box.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.EXTERNAL)
        box.set_child(view)
        box.set_halign(Gtk.Align.START)
        box.set_valign(Gtk.Align.START)
        box.set_visible(False)
        overlay = Gtk.Overlay()
        overlay.set_child(da)
        overlay.add_overlay(box)
        win.set_child(overlay)
        self.flows_win, self.flows_da, self.wf_entry, self.wf_entry_box = win, da, view, box
        self.flows_overlay = overlay
        return win

    def flows_dock(self):
        """Dónde está el panel. En modo ventana no es una capa: su dibujo y su
        caja pasan al `overlay` de la ventana de la app y, abierto, la cubren
        entera; cerrado, se esconden. Fuera de ese modo vuelve a su capa."""
        win, panel = self.flows_win, self.flows_overlay
        if win is None or panel is None:
            return
        if self.windowed:
            if panel.get_parent() is win:
                win.set_child(None)
                self.overlay.add_overlay(panel)
            win.set_visible(False)
            panel.set_visible(self.wf_open and not self.flows_widgets())
        elif panel.get_parent() is self.overlay:
            self.overlay.remove_overlay(panel)
            win.set_child(panel)
            panel.set_visible(True)

    def flows_monitor(self):
        """La isla de los flujos sale en la pantalla en la que está la isla."""
        name = (getattr(self, 'monitor', None) or {}).get('name')
        if self.flows_win is None or not name:
            return
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            if monitors.get_item(i).get_connector() == name:
                LayerShell.set_monitor(self.flows_win, monitors.get_item(i))

    @staticmethod
    def flows_side(width, win_left):
        """De qué lado de la isla sale: la izquierda, salvo que la isla esté
        tan corrida a ese lado de la pantalla que no cabe; entonces, la
        derecha. Si no cabe en ninguno, donde haya más sitio. Se decide con
        la ventana de la isla, no con su tamaño de ahora: no brinca de lado
        mientras ella crece o se encoge."""
        from . import app
        left = win_left - WF_GAP - WF_EDGE
        right = width - (win_left + app.WIN_W) - WF_GAP - WF_EDGE
        if left >= WF_W:
            return 'left'
        if right >= WF_W:
            return 'right'
        return 'left' if left >= right else 'right'

    def flows_rect(self, width):
        """(x, ancho, alto) de la isla de los flujos en su ventana: pegada a
        la de siempre, del lado que le toca."""
        from . import app
        if self.windowed:
            self.wf_side = 'left'
            return self.island_rect(width)      # la ventana es el panel: todo el ancho y su alto
        w, h = clamp(self.fw, 0, WF_W), clamp(self.fh, 0, WF_WIN_H)
        win_left = self.offset() if self.moved() else (width - app.WIN_W) / 2
        ix0, iw, _ = self.island_rect(app.WIN_W)
        self.wf_side = self.flows_side(width, win_left)
        if self.wf_side == 'left':
            x0 = win_left + ix0 - WF_GAP - w
        else:
            x0 = win_left + ix0 + iw + WF_GAP
        return clamp(x0, 0, max(0, width - w)), w, h

    def wf_redraw(self):
        """Pide un dibujo; la isla rebota hasta su tamaño mientras haga falta."""
        da = self.flows_da
        if da is None:
            return
        da.queue_draw()
        if not self.fticking:
            self.fticking, self.flast = True, None
            da.add_tick_callback(self.flows_on_tick)

    def flows_follow(self):
        """La isla de siempre se movió o cambió de tamaño: la de los flujos la sigue."""
        if self.flows_win is not None and not self.windowed:
            LayerShell.set_margin(self.flows_win, LayerShell.Edge.TOP, self.top())
        if self.flows_da is not None and self.wf_open:
            self.flows_da.queue_draw()
            self.flows_region()

    def flows_on_tick(self, widget, _clock):
        now = time.monotonic()
        dt = 1 / 60 if self.flast is None else min(0.05, now - self.flast)
        self.flast = now
        tw, th = self.flows_goal()
        for pos, vel, goal in (('fw', 'fvw', tw), ('fh', 'fvh', th)):
            x, v = getattr(self, pos), getattr(self, vel)
            v += (WF_SPRING_K * (goal - x) - WF_SPRING_C * v) * dt
            setattr(self, vel, v)
            setattr(self, pos, x + v * dt)
        settled = abs(tw - self.fw) < 0.5 and abs(th - self.fh) < 0.5 and abs(self.fvw) < 1 and abs(self.fvh) < 1
        if settled:
            self.fw, self.fh, self.fvw, self.fvh = tw, th, 0.0, 0.0
        self.flows_region()
        widget.queue_draw()
        if settled:
            self.fticking = False
            if self.windowed:
                self.flows_dock()
            elif not self.wf_open and self.flows_win is not None:
                self.flows_win.set_visible(False)       # ya se cerró: no deja nada que tapar
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def flows_region(self):
        """Solo la isla recibe clics; fuera de ella pasan a las ventanas de abajo."""
        surface = self.flows_win.get_surface() if self.flows_win is not None and not self.windowed else None
        if surface is None:
            return
        x0, w, h = self.flows_rect(self.flows_da.get_width())
        region = (int(x0), 0, int(w) + 1, int(h) + 1) if h >= 1 else (0, 0, 0, 0)
        if region != self.wf_region:
            surface.set_input_region(cairo.Region(cairo.RectangleInt(*region)))
            self.wf_region = region

    def flows_draw(self, _da, cr, width, _height):
        """La isla de los flujos: su cuerpo, como el de la isla de siempre, y
        dentro la pastilla o el panel. Lo que se puede pulsar queda en
        `wf_hits` y `wf_buttons`, aparte de lo de la isla de siempre."""
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        x0, w, h = self.flows_rect(width)
        if h < 0.5 or w < 1:
            self.wf_hits, self.wf_buttons, self.wf_box = [], {}, None
            self.wf_place_entry(0)
            return
        edge = self.island_fill(cr, x0, w, h)
        cr.save()
        cr.clip()
        # Los ayudantes de dibujo de la isla apuntan lo pulsable en sus listas.
        island = (self.hits, self.buttons, self.pointer)
        self.hits, self.buttons, self.pointer = [], {}, self.wf_pointer
        self.wf_box = None
        try:
            if self.wf_pill():
                self.draw_wf_pill(cr, x0, w, h, clamp((h - 14) / 20))
            else:
                self.draw_workflows(cr, x0, w, h, clamp((w - 420) / 120) * clamp((h - 40) / 40))
        finally:
            self.wf_hits, self.wf_buttons = self.hits, self.buttons
            self.hits, self.buttons, self.pointer = island
        cr.restore()
        if edge:
            cr.append_path(edge)
            cr.set_source_rgba(1, 1, 1, WF_GLASS_EDGE)
            cr.set_line_width(1)
            cr.stroke()
        self.wf_place_entry(h)

    def draw_wf_pill(self, cr, x0, w, h, alpha):
        """La isla colapsada: una pastilla con «Flujos» y cómo va lo que corre.
        Un clic en ella la abre."""
        run = self.wf_run
        soft = rgb(self.wf_ink('text', .62))
        if self.over(x0, 0, w, h):
            cr.rectangle(x0, 0, w, h)
            cr.set_source_rgba(1, 1, 1, .06 * alpha)
            cr.fill()
        if run is not None and run.running:
            tone, note = 'cmd', f'paso {run.index + 1}/{len(run.w.steps)}'
        elif run is not None and run.failed is not None:
            tone, note = 'bad', 'falló'
        elif run is not None and run.done:
            tone, note = 'pass', 'terminó'
        else:
            tone, note = None, str(len(self.workflows))
        mid = WF_PILL_H / 2
        cr.new_sub_path()
        cr.arc(x0 + 16, mid, 3.5, 0, 6.2832)
        cr.set_source_rgba(*(rgb(self.wf_ink(tone)) if tone else soft), alpha)
        cr.fill()
        tw = self.wf_put(cr, 'Flujos', FONT_WF_HEAD, x0 + 28, mid - 8, TITLE, alpha)
        self.wf_put(cr, note, FONT_WF_NOTE, x0 + 28 + tw + 8, mid - 6, soft, alpha, width=w - tw - 80)
        opens = '‹' if self.wf_side == 'left' else '›'
        self.wf_put(cr, opens, FONT_WF_ICON, x0 + w - 14, mid - 9, soft, alpha, align=1.0)

    def on_flows_motion(self, _ctrl, x, y):
        self.wf_pointer = None if x is None else (x, y)
        if self.flows_da is not None:
            self.flows_da.queue_draw()

    def on_flows_click(self, _gesture, _n, x, y):
        x0, w, h = self.flows_rect(self.flows_da.get_width())
        if not (x0 <= x <= x0 + w and y <= h):
            return
        if self.wf_pill():
            self.wf_collapse(False)
            return
        for key, (bx, by, bw, bh) in self.wf_buttons.items():
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.on_wf_hit(key[3:] if key.startswith('wf-') else key)
                return
        for kind, key, hx, hy, hw, hh in self.wf_hits:
            if kind == 'wf' and hx <= x <= hx + hw and hy <= y <= hy + hh:
                self.on_wf_hit(key)
                return

    def on_flows_scroll(self, dy):
        pointer = self.wf_pointer
        if pointer is None or self.wf_pill():
            return False
        x0, w, h = self.flows_rect(self.flows_da.get_width())
        if not (x0 <= pointer[0] <= x0 + w and pointer[1] <= h):
            return False
        self.on_wf_scroll(dy)
        return True

    def on_wf_entry_key(self, _ctrl, keyval, _code, mods):
        self.wf_keyed = time.monotonic()
        return self.on_wf_key(keyval, bool(mods & Gdk.ModifierType.SHIFT_MASK))

    def wf_place_entry(self, h):
        """Pone la caja de texto de verdad sobre el campo dibujado en el que se escribe."""
        box = self.wf_entry_box
        if box is None:
            return
        show = (self.wf_field is not None and self.wf_typing and self.wf_box is not None
                and not self.wf_pill() and h > self.flows_goal()[1] - 40)
        if show:
            x, y, w, hh = self.wf_box
            if (box.get_margin_start(), box.get_margin_top()) != (x, y):
                box.set_margin_start(x)
                box.set_margin_top(y)
            box.set_size_request(w, hh)
        if box.get_visible() != show:
            box.set_visible(show)
            if show:
                self.wf_entry.grab_focus()

    # ── lo que se hace desde el panel ───────────────────────────────────────

    def on_wf_hit(self, key):
        """Un clic en el panel: un enlace, un botón, un campo o una opción de un menú."""
        menu, self.wf_menu = self.wf_menu, None
        what, _, arg = key.partition(':')
        index = int(arg) if arg.isdigit() else None
        draft, run = self.wf_draft, self.wf_run
        if what == 'close':
            self.close_workflows()
        elif what == 'collapse':
            self.wf_collapse(True)
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
        self.wf_redraw()

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
        self.wf_redraw()

    def workflows_confirmed(self):
        """Se dijo que sí a lo que se preguntaba."""
        what, arg = self.wf_confirm
        self.wf_confirm = None
        if what == 'discard':
            self.wf_draft, self.wf_screen = None, 'list'
        elif what == 'delete':
            self.workflows_delete(arg)
        self.wf_redraw()

    def workflows_write(self, found, what, again):
        """Guarda la lista. Si no se puede, lo dice en el panel, con cómo
        reintentar, y devuelve False: lo que había en pantalla sigue ahí."""
        try:
            workflows.save(found)
        except OSError as e:
            self.wf_error = (what, errno.errorcode.get(e.errno, 'desconocido'), again)
            self.wf_redraw()
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
        self.wf_redraw()

    def workflows_delete(self, name):
        what = f'No pudimos borrar «{name}». Vuelve a intentarlo.'
        self.workflows_write([w for w in self.workflows if w.name != name], what,
                             lambda: self.workflows_delete(name))
        self.wf_redraw()

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

    def wf_ink(self, role, light=None):
        """El color de un papel para el panel. `ink` aviva los colores del
        tema para la burbuja de una fuente, y con los grises eso los vuelve
        azulados: aquí el texto es neutro, con tres escalones —lo principal,
        lo secundario (notas y etiquetas) y los enlaces— y el color solo
        donde dice algo: el acento en lo que se puede lanzar o corre, verde
        y rojo en lo que salió o falló, ámbar en lo que falta guardar."""
        colors = self.colors
        if role == 'cmd':
            return mascot.accent(state.MAIN_ROLE)
        if role == 'flag':
            return colors['pct2']
        if role == 'head':
            return paint.mix(colors['text'], '#ffffff', .4)
        if role == 'text':
            return colors['text'] if light is not None and light < .66 else paint.mix(colors['text'], '#ffffff', .35)
        return colors[role]

    def wf_put(self, cr, text, font, x, y, color, alpha, width=None, align=0.0, lines=1):
        """`put` del panel: en modo vidrio, con la sombra de la burbuja debajo
        de cada texto, que lo despega de lo que haya detrás. Devuelve su ancho."""
        if not self.settings['glass']:
            return self.put(cr, text, font, x, y, color, alpha, width, align, lines=lines)
        layout = self._layout(cr, text, font, width, lines)
        tw = layout.get_pixel_size()[0]
        self.tip_text(cr, layout, x - tw * align, y, color[:3], alpha, True)
        return tw

    def wf_link(self, cr, key, label, x, y, alpha, right=False, tone=None, on=True, font=FONT_WF_HEAD):
        """Un enlace del panel, con su clic. Con `right`, pegado a x por la
        derecha. Apagado (`on` False) se ve tenue y no hace nada. Devuelve su ancho."""
        layout = self._layout(cr, label, font)
        lw, lh = layout.get_pixel_size()
        if right:
            x -= lw
        over = on and self.over(x - 4, y - 4, lw + 8, lh + 8)
        color = (1, 1, 1) if over else tone or rgb(self.wf_ink('text', .7))
        self.tip_text(cr, layout, x, y, color, alpha * (1 if on else .35), self.settings['glass'])
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
        soft = rgb(self.wf_ink('text', .62))
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
        arrow = WF_SIDES[self.wf_side]
        if not self.windowed:
            x -= self.wf_link(cr, 'collapse', f'colapsar {arrow}' if arrow == '›' else f'{arrow} colapsar', x, 14,
                              alpha, right=True) + 14
        tw = self.wf_put(cr, title, FONT_WF_TITLE, left, 14, TITLE, alpha, width=x - left - 120)
        if note:
            self.wf_put(cr, note, FONT_WF_NOTE, left + tw + 12, 17, soft, alpha, width=x - left - tw - 24)
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
        soft = rgb(self.wf_ink('text', .62))
        if not found:
            self.wf_put(cr, 'Todavía no guardaste ningún workflow. Crea uno para repetir una cadena de agentes '
                     'sin escribirla cada vez.', FONT_WF, left, y + 4, rgb(self.wf_ink('arg')), alpha,
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
                              tone=rgb(self.wf_ink('bad')), on=not (mine and busy)) + 14
            x -= self.wf_link(cr, f'edit:{i}', 'editar', x, ry + 8, alpha, right=True) + 14
            x -= self.wf_link(cr, f'launch:{i}', 'lanzar ›', x, ry + 8, alpha, right=True,
                              tone=rgb(self.wf_ink('cmd')), on=bool(w.steps) and not busy) + 14
            if mine:
                x -= self.wf_link(cr, 'view', 'ver ›', x, ry + 8, alpha, right=True) + 14
            nw = self.wf_put(cr, w.name, FONT_WF, left + 4, ry + 8, TITLE, alpha, width=(x - left) * .55)
            steps = '1 paso' if len(w.steps) == 1 else f'{len(w.steps)} pasos'
            here = self.wf_here()
            place = (self.project_label(w.project) if w.project
                     else f'donde estés (ahora {self.project_label(here)})' if here else 'donde estés')
            note = f'{steps} · {place}'       # si no cabe, se corta el sitio, no cuántos pasos
            tone = soft
            if mine:
                note += f' · {run.status().rstrip(".…").lower()}'
                tone = rgb(self.wf_ink('cmd' if busy else 'bad' if run.failed is not None else 'pass'))
            self.wf_put(cr, note, FONT_WF_NOTE, left + nw + 16, ry + 10, tone, alpha, width=x - left - nw - 24)
        rest = len(found) - self.wf_scroll - len(shown)
        if rest > 0:
            self.wf_put(cr, f'↓ {rest} más', FONT_WF_NOTE, left + width, y + len(shown) * WF_ROW, soft, alpha, align=1.0)
        return y + len(shown) * WF_ROW + WF_PAD

    def draw_wf_field(self, cr, field, text, hint, x, y, width, alpha, bad=False):
        """Un campo de texto: su caja y lo que tiene. Si es en el que se
        escribe, deja su sitio (`wf_box`) para la caja de texto de verdad,
        que es la que enseña el texto."""
        active = self.wf_field == field
        mascot.rrect(cr, x, y, width, WF_FIELD_H, 8)
        cr.set_source_rgba(1, 1, 1, (.10 if active else .06) * alpha)
        cr.fill()
        if active or bad:
            mascot.rrect(cr, x + .5, y + .5, width - 1, WF_FIELD_H - 1, 8)
            cr.set_source_rgba(*rgb(self.wf_ink('bad') if bad else mascot.accent(state.MAIN_ROLE)), .8 * alpha)
            cr.set_line_width(1)
            cr.stroke()
        line = self._layout(cr, 'X', FONT_WF_FIELD).get_pixel_size()[1]
        tx, ty, tw = x + WF_FIELD_INSET, y + (WF_FIELD_H - line) / 2, width - 2 * WF_FIELD_INSET
        if not text:
            self.wf_put(cr, hint, FONT_WF, tx, ty + 1, (1, 1, 1), .34 * alpha, width=tw)
        elif not active:
            self.wf_put(cr, text, FONT_WF_FIELD, tx, ty, rgb(self.wf_ink('arg')), alpha, width=tw)
        if active:
            self.wf_box = (int(tx), int(ty), int(tw), int(line))
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
        self.wf_put(cr, text, FONT_WF, x + WF_FIELD_INSET, y + (WF_FIELD_H - line) / 2,
                 color or rgb(self.wf_ink('arg')), alpha, width=width - 2 * WF_FIELD_INSET - 12)
        self.wf_put(cr, '▾', FONT_WF_ICON, x + width - WF_FIELD_INSET, y + (WF_FIELD_H - line) / 2 - 3,
                 rgb(self.wf_ink('text', .62)), alpha, align=1.0)
        self.hits.append(('wf', key, x, y, width, WF_FIELD_H))
        if opened:
            self.wf_menu_at = (x, y + WF_FIELD_H + 4, y - 4, width)

    def draw_wf_editor(self, cr, left, y, width, alpha):
        draft = self.wf_draft
        head, soft = rgb(self.wf_ink('head')), rgb(self.wf_ink('text', .62))
        inset = (WF_ROW - WF_FIELD_H) / 2
        problem = draft.name_problem(self.workflows) if draft.w.name.strip() else ''
        self.wf_put(cr, 'Nombre', FONT_WF_HEAD, left, y + 9, head, alpha)
        self.draw_wf_field(cr, 'name', draft.w.name, 'Cómo se llama', left + WF_LABEL_W, y + inset,
                           width - WF_LABEL_W, alpha, bad=bool(problem))
        y += WF_ROW
        self.wf_put(cr, 'Proyecto', FONT_WF_HEAD, left, y + 9, head, alpha)
        self.draw_wf_pick(cr, 'project', self.project_label(draft.w.project), left + WF_LABEL_W, y + inset,
                          width - WF_LABEL_W, alpha, opened=self.wf_menu == ('project',))
        y += WF_ROW
        self.wf_put(cr, 'Pasos', FONT_WF_HEAD, left, y + 5, head, alpha)
        y += WF_LINE
        if not draft.w.steps:
            self.wf_put(cr, 'Este workflow aún no tiene pasos. Añade el primero para elegir qué agente empieza.',
                     FONT_WF, left, y + 8, rgb(self.wf_ink('arg')), alpha, width=width)
            y += WF_ROW
        count = len(draft.w.steps)
        for i, step in enumerate(draft.w.steps):
            self.draw_wf_step(cr, i, step, count, left, y, width, alpha)
            y += WF_ROW
        add = '+ Añadir paso' if count else 'Añadir primer paso'
        self.wf_link(cr, 'add', add, left, y + 8, alpha, tone=rgb(self.wf_ink('cmd')), on=count < WF_MAX_STEPS)
        y += WF_ROW
        x = left + self.wf_put(cr, 'Si un paso falla', FONT_WF_HEAD, left, y + 9, head, alpha) + 14
        for value, label in ((workflows.STOP, 'parar ahí'), (workflows.GO, 'seguir con el siguiente')):
            chosen = draft.w.on_fail == value
            layout = self._layout(cr, label, FONT_WF_HEAD)
            lw, lh = layout.get_pixel_size()
            over = self.over(x, y + 4, lw + 20, WF_FIELD_H - 2)
            mascot.rrect(cr, x, y + 4, lw + 20, WF_FIELD_H - 2, (WF_FIELD_H - 2) / 2)
            tint = rgb(mascot.accent(state.MAIN_ROLE)) if chosen else (1, 1, 1)
            cr.set_source_rgba(*tint, (.24 if chosen else .11 if over else .06) * alpha)
            cr.fill()
            self.tip_text(cr, layout, x + 10, y + 4 + (WF_FIELD_H - 2 - lh) / 2, TITLE if chosen else soft, alpha, self.settings['glass'])
            self.hits.append(('wf', f'fail:{value}', x, y + 4, lw + 20, WF_FIELD_H - 2))
            x += lw + 20 + 8
        y += WF_ROW
        # Por qué no se puede lanzar todavía, encima de los botones.
        blocker = self.wf_blocker()
        if problem or blocker:
            self.wf_put(cr, problem or blocker, FONT_WF_NOTE, left, y + 4, rgb(self.wf_ink('bad')) if problem else soft,
                     alpha, width=width)
        y += WF_LINE
        cr.set_source_rgba(1, 1, 1, .07 * alpha)
        cr.rectangle(left, y, width, 1)
        cr.fill()
        by = y + (WF_FOOT - BUTTON_H) / 2 + 2
        if draft.dirty:
            self.wf_put(cr, 'Sin guardar', FONT_WF_NOTE, left, by + 7, rgb(self.wf_ink('flag')), alpha)
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
        self.wf_put(cr, str(i + 1), FONT_WF_NOTE, left + 2, y + 10, rgb(self.wf_ink('text', .62)), alpha)
        self.face(cr, role, 'idle', left + 16 + WF_FACE / 2, y + WF_ROW / 2, WF_FACE, alpha)
        ax = left + 16 + WF_FACE + 8
        self.draw_wf_pick(cr, f'agent:{i}', step.agent, ax, y + inset, WF_AGENT_W, alpha,
                          opened=self.wf_menu == ('agent', i))
        x = left + width - 2
        for key, icon, on in (('drop', '✕', True), ('down', '↓', i + 1 < count), ('up', '↑', i > 0)):
            x -= self.wf_link(cr, f'{key}:{i}', icon, x, y + 6, alpha, right=True, on=on, font=FONT_WF_ICON) + 12
        fx = ax + WF_AGENT_W + 8
        self.draw_wf_field(cr, i, step.text, 'Qué hace en este paso', fx, y + inset, x - fx, alpha)

    def draw_wf_run(self, cr, left, y, width, alpha):
        run = self.wf_run
        soft = rgb(self.wf_ink('text', .62))
        for i, step in enumerate(run.w.steps):
            mark, tone = MARKS[run.states[i]]
            role = state.AGENT_ROLES.get(step.agent, state.MAIN_ROLE)
            self.wf_put(cr, mark, FONT_WF_MARK, left + 2, y + 6, soft if tone == 'text' else rgb(self.wf_ink(tone)), alpha)
            pet = 'working' if run.states[i] == workflows.RUNNING else 'idle'
            self.face(cr, role, pet, left + 24 + WF_FACE / 2, y + WF_ROW / 2, WF_FACE, alpha)
            tw = self.wf_put(cr, took(run.seconds(i)), FONT_WF_NOTE, left + width, y + 10, soft, alpha, align=1.0)
            ax = left + 24 + WF_FACE + 8
            aw = self.wf_put(cr, step.agent, FONT_WF_HEAD, ax, y + 9, TITLE, alpha, width=WF_AGENT_W)
            self.wf_put(cr, step.text, FONT_WF, ax + aw + 10, y + 9, rgb(self.wf_ink('arg')), alpha,
                     width=width - (ax - left) - aw - tw - 24)
            y += WF_ROW
        bad = run.failed
        if bad is not None:
            self.wf_put(cr, self.workflow_trouble(bad) + ' Ábrelo y reintenta desde ese paso.', FONT_WF, left, y + 4,
                     rgb(self.wf_ink('bad')), alpha, width=width, lines=2)
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
        self.wf_put(cr, run.status(), FONT_WF_NOTE, left, by + 7, rgb(self.wf_ink(tone)), alpha, width=x - left)
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
        cr.set_source_rgba(*(rgb(self.wf_ink('bad')) if bad else (1, 1, 1)), (.13 if bad else .07) * alpha)
        cr.fill()
        x = left + width - 10
        for key, label, primary in reversed(buttons):
            x = self.wf_button(cr, key, label, x, y + (WF_BAR - BUTTON_H) / 2, primary, alpha) - 8
        room = x - left - 16
        if note:
            self.wf_put(cr, text, FONT_WF, left + 12, y + 7, rgb(self.wf_ink('arg')), alpha, width=room)
            self.wf_put(cr, note, FONT_WF_NOTE, left + 12, y + 26, rgb(self.wf_ink('text', .62)), alpha, width=room)
        else:
            layout = self._layout(cr, text, FONT_WF, room, 2)
            self.tip_text(cr, layout, left + 12, y + (WF_BAR - layout.get_pixel_size()[1]) / 2,
                          rgb(self.wf_ink('arg')), alpha, self.settings['glass'])
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
        # En vidrio el menú es translúcido como la burbuja de una fuente; con la isla opaca, casi opaco.
        cr.set_source_rgba(.07, .08, .10, (WF_GLASS_ALPHA if self.settings['glass'] else .98) * alpha)
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
            tx, color = x + 10, TITLE if chosen else rgb(self.wf_ink('arg'))
            if faces:
                role = state.AGENT_ROLES.get(label, state.MAIN_ROLE)
                self.face(cr, role, 'idle', x + 8 + 9, ry + WF_MENU_ROW / 2, 18, alpha)
                tx = x + 34
            self.wf_put(cr, ('✓ ' if chosen else '') + label, FONT_WF, tx, ry + 5, color, alpha, width=width - (tx - x) - 10)
            self.hits.insert(0, ('wf', f'pick:{self.wf_scroll + n}', x + 4, ry, width - 8, WF_MENU_ROW))
        if len(items) > len(shown):
            more = len(items) - self.wf_scroll - len(shown)
            self.wf_put(cr, f'↓ {more}' if more > 0 else '↑', FONT_WF_NOTE, x + width - 8, y + mh - 16,
                     rgb(self.wf_ink('text', .62)), alpha, align=1.0)
        # Un botón tapado por el menú no se pulsa a través de él.
        self.buttons = {key: box for key, box in self.buttons.items()
                        if not (x < box[0] + box[2] and box[0] < x + width and y < box[1] + box[3] and box[1] < y + mh)}
        self.hits.insert(len(shown), ('wf', 'menu', x, y, width, mh))     # un clic en su borde lo cierra, nada más
