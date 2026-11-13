"""La isla como app: una ventana normal de Hyprland con lo mismo que la isla.

No es otro programa ni otra isla: es el mismo daemon con el mismo estado. El
dibujo de la isla (tablero, chat, proyectos) vive en un solo `Gtk.DrawingArea`
dentro de un `Gtk.Overlay`; abrir la ventana mueve ese `overlay` de la capa de
layer-shell a una `Gtk.ApplicationWindow` y esconde la capa, y cerrarla lo
devuelve. Nunca se ven las dos a la vez. Ver la decisión 008 del vault.

Se abre con `elyares-ctl window` (o el `.desktop`, que llama a lo mismo) y con
`elyares-ctl window toggle` se alterna. `Island.windowed` dice en cuál de los dos
modos está; la isla lo mira para no tocar el layer-shell mientras no se ve y para
quedarse siempre abierta, sin esconderse ni asomarse.
"""

import threading
import time

from gi.repository import GLib, Gtk

from . import (editorpanel, fonts, gitview, hypr, mascot, pomodoro, settings, tallerpanel, terminal, terminalpanel,
               themes, tmuxsessions, windowframe)
from .state import MAIN_ROLE, elapsed

APP_ID = 'dev.elyares.Engineer'
TITLE = 'Elyares Engineer'
CLASS_RE = r'^(dev\.elyares\.Engineer)$'    # la `class` de la ventana, como regex de Hyprland
MIN_W, MIN_H = 480, 320          # lo menos que se le deja a la ventana
FIT_H = 100                      # lo que se le resta a la pantalla para que no la tape entera
FOCUS_ROOM = 220                 # lo que un desglose deja a las barras y a lo que va debajo
FIT_PAD = 12                     # aire bajo la isla
FIT_STEP = 6                     # cambios de alto menores no mueven la ventana
REMEMBER_SECS = 2                # cada cuánto se guarda el tamaño que Yared va dejando
FIT_SETTLE = 0.6                 # lo que tarda Hyprland en dejarla del alto pedido
PANELS_EVERY = 0.1               # cada cuánto se ponen al día los paneles de widgets
FIT_HOLD = 160                   # un contenido más corto que esto no encoge la ventana: no «respira»
FIT_VOID = 120                   # con su medida guardada, el vacío bajo el contenido que se tolera antes de ajustarla
EDITOR_H = 760                   # el alto que pide el editor para ver código con holgura (se recorta a la pantalla)
OPEN_H = 780                     # alto con el que abre: el tablero y el chat caben; el resto, con scroll de la pantalla


class WindowView:
    """Lo que guarda: `windowed` (la app está a la vista) y `app_win` (su
    ventana, que se crea la primera vez)."""

    fit_h = 0                       # el último alto al que se ajustó la ventana
    fit_at = 0.0                    # cuándo se pidió
    fit_manual = False              # Yared la estiró a mano: su medida manda para lo alto
    fit_shrunk = False              # se encogió sola por un contenido corto: no se guarda ese alto
    fit_saved = (0, 0, 0.0)         # el último tamaño guardado: ancho, alto y cuándo
    windowed = False                # la isla, que se arma sin __init__ en las pruebas, la mira siempre
    app_win = None
    sources_open = False            # la vista Fuentes está a la vista
    panels_key = None
    panels_at = 0.0
    hypr_async = True               # las pruebas lo apagan: el pedido sale en el acto
    window_body = 0                 # alto extra que piden las tarjetas del tablero (lo usa body_h)
    sources_pick = 'claude'         # la fuente que muestra
    panel_open = ''                 # 'alerts', 'settings', 'tmux', 'pomodoro', 'editor', 'terminal' o 'taller' cuando una de esas vistas está a la vista
    help_win = None
    frame = None                    # el marco de widgets (windowframe.Frame); None sin ventana real

    def window_init(self):
        self.tmux_watch = tmuxsessions.Watcher()
        self.pomo_watch = pomodoro.Watcher()
        self.git_watch = gitview.Watcher()
        self.pomo_repo = ''             # la carpeta del chat que se abrió con «Con agente»
        self.windowed = False
        self.app_win = None
        self.frame = None

    # ── abrir y cerrar ──────────────────────────────────────────────────────

    def open_window(self):
        """Abre la ventana de la app, o si ya está abierta, la enfoca."""
        if self.windowed:
            self.app_win.present()
            return
        if self.app_win is None:
            self.app_win = self.window_make()
        # Un widget solo puede tener un padre: primero se suelta de la capa.
        self.win.set_child(None)
        self.window_content(self.overlay)
        self.da.set_content_width(MIN_W)
        self.da.set_content_height(MIN_H)
        self.windowed = True
        self.flows_dock()
        self.fit_h = 0
        self.fit_manual = False
        self.off = False
        self.settings['window'] = True
        self.window_save()
        self.win.set_visible(False)
        self.app_win.present()
        self.expand()
        kept = self.window_kept()
        if kept:
            # La dejó a su medida la última vez: se respeta, y no se ajusta sola.
            self.fit_manual = True
            GLib.timeout_add(250, self.window_restore, kept)

    def close_window(self):
        """Cierra la ventana y devuelve la isla, con el estado que tenía."""
        if not self.windowed:
            return
        if self.fit_manual:
            self.window_remember(force=True)
        if self.frame is not None:
            self.frame.hide_panels()
        self.window_content(None)
        self.app_win.set_visible(False)
        self.windowed = False
        self.flows_dock()
        self.settings['window'] = False
        self.window_save()
        self.win.set_child(self.overlay)
        self.da.set_content_width(self.island_w)
        self.da.set_content_height(self.island_h)
        self.region = None              # la capa vuelve a estrenar su zona de entrada
        self.win.present()
        self.place()
        self.update_region()
        self.collapse()

    def toggle_window(self):
        if self.windowed:
            self.close_window()
        else:
            self.open_window()

    def window_make(self):
        win = Gtk.ApplicationWindow(application=self.gtk_app)
        win.set_title(TITLE)
        win.set_icon_name(APP_ID)
        width, height = self.window_size()
        win.set_default_size(width, height)
        # Cerrarla no es salir: solo vuelve la isla.
        win.connect('close-request', self.on_window_close)
        win.connect('notify::is-active', self.on_window_focus)
        self.frame = windowframe.Frame(self.window_view, self.window_pick)
        self.frame.attach(win)
        self.overlay.add_overlay(self.frame.flows)     # y la lista de Flujos, con el estilo de la app
        self.overlay.add_overlay(self.frame.focus)     # el desglose de un agente, igual
        self.overlay.add_overlay(self.frame.board)     # encima del dibujo, solo con el tablero a la vista
        self.overlay.add_overlay(self.frame.chat_head)     # y la cabecera del chat, solo con el chat
        self.overlay.add_overlay(self.frame.sources)       # y la vista Fuentes, que lo cubre todo
        self.overlay.add_overlay(self.frame.alerts)        # y la bandeja y los ajustes, igual
        self.overlay.add_overlay(self.frame.settings)
        self.overlay.add_overlay(self.frame.tmux)
        self.overlay.add_overlay(self.frame.pomodoro)
        self.frame.editor = editorpanel.EditorPanel()      # en su archivo: importa de windowframe, no al revés
        self.overlay.add_overlay(self.frame.editor)
        self.frame.terminal = terminalpanel.TerminalPanel()
        self.frame.taller = tallerpanel.TallerPanel()
        self.overlay.add_overlay(self.frame.taller)
        self.frame.extra += [self.frame.editor, self.frame.terminal, self.frame.taller]     # `hide_panels` los esconde con los demás
        self.overlay.add_overlay(self.frame.terminal)
        self.frame.help.connect('clicked', lambda _b: self.window_help())
        return win

    def window_content(self, child):
        """El contenido de la ventana: en el marco de widgets si lo hay."""
        if self.frame is not None:
            self.frame.set_content(child)
        else:
            self.app_win.set_child(child)

    def window_view(self, key):
        """Un botón de la barra de título: deja a la vista esa vista."""
        self.sources_open = key == 'sources'
        self.panel_open = key if key in ('alerts', 'settings', 'tmux', 'pomodoro', 'editor', 'terminal', 'taller') else ''
        if key != 'chat' and self.chat_open:
            self.close_chat()
        if key != 'projects' and self.projects_open:
            self.toggle_projects()
        if key != 'flows' and self.wf_open:
            self.close_workflows()
        if key == 'chat' and not self.chat_open:
            self.open_chat()
        elif key == 'projects' and not self.projects_open:
            self.toggle_projects()
        elif key == 'flows' and not self.wf_open:
            self.open_workflows()
        self.ensure_tick()          # en reposo el tick está apagado y los paneles no se pondrían al día

    def window_panels_key(self):
        return (self.window_current(), self.focus, self.tab, self.chat_open, self.wf_open, self.wf_screen,
                self.wf_confirm is not None, self.wf_error is not None)

    def window_panels_stale(self):
        return self.window_panels_key() != self.panels_key

    def window_panels_due(self, now):
        """Los paneles se ponen al día a lo más cada PANELS_EVERY: a 60 cuadros
        por segundo el texto no cambia más rápido. Si cambió de vista o de
        agente, de inmediato, para que un clic responda en el acto."""
        key = self.window_panels_key()
        if key == self.panels_key and now - self.panels_at < PANELS_EVERY:
            return False
        self.panels_key, self.panels_at = key, now
        return True

    def window_covered(self):
        """¿Un panel de widgets lo cubre todo (Fuentes, Alertas, Ajustes)?
        Entonces la isla no dibuja nada que se vea."""
        return (self.frame is not None and self.windowed
                and (self.sources_open or bool(self.panel_open))
                and not (self.chat_open or self.projects_open or self.wf_open))

    def board_widgets(self):
        """¿El tablero lo dibujan los widgets? En la ventana y sin un desglose
        abierto (ese, con su mini chat, sigue en Cairo)."""
        return self.window_board_view() and self.focused() is None

    def focus_widgets(self):
        """¿El desglose de un agente lo llevan los widgets? Con uno abierto."""
        return self.window_board_view() and self.focused() is not None

    def window_board_view(self):
        return (self.frame is not None and self.windowed and not self.sources_open
                and not self.panel_open and not self.wf_open
                and self.target() == 'board' and self.tab_session() is not None)

    def window_board(self):
        from . import app           # hasta aquí: app importa este módulo
        board = self.frame.board
        if self.focus_widgets():
            board.place(0)
            self.window_focus(app)
            return
        self.frame.focus.place(0)
        if not self.board_widgets():
            board.place(0)
            self.window_body = 0
            return
        s = self.tab_session()
        asking = self.asking()
        now, cards, free = time.monotonic(), [], []
        for m in self.team(s):
            busy = m.busy
            color = mascot.COLORS.get(mascot.accent(m.role), mascot.accent(m.role))
            asleep = m.role == MAIN_ROLE and not busy and not s.delegating
            pet = app.MEMBER_PET.get(m.state, 'sleep' if asleep else 'idle')
            if busy:
                took = f' · {elapsed(now - m.since)}' if m.state == 'working' and m.since else ''
                state = {'permission': 'Pide permiso', 'working': 'Trabaja', 'waiting': 'Espera respuesta',
                         'done': 'Terminó'}.get(m.state, m.state) + took
                steps = [m.detail] if m.state == 'permission' else [t for t, _at in m.steps[-3:]] or ['Arrancando…']
                cards.append(dict(role=m.role, name=m.role, color=color, state=state, steps=steps, busy=True,
                                  ask=m.state == 'permission' and self.seat(s, m.role) is asking, pet=pet))
            else:
                note = ('esperando' if s.delegating else 'en reposo') if m.role == MAIN_ROLE else 'libre'
                free.append(dict(role=m.role, name=m.role, color=color, state=note, steps=[], busy=False,
                                 ask=False, pet=pet))
        board.set_cards(cards, free, dict(face=self.window_face, pick=self.window_card, decide=self.window_decide))
        board.animate()
        # Las tarjetas piden lo que miden: si no caben en el alto de siempre,
        # el tablero crece y empuja lo de abajo en vez de esconder un botón.
        width = board.get_width() or self.app_win.get_width() or MIN_W
        self.window_body = max(0, board.natural_h(width) - app.TABS_H)
        board.place(app.TABS_H + self.body_h())

    def window_focus(self, app):
        """El desglose de un agente: sus pasos, quién es y sus enlaces."""
        from . import state
        s, m = self.focused()
        now = time.monotonic()
        color = mascot.accent(m.role)
        pet = app.MEMBER_PET.get(m.state, 'idle')
        n = len(m.steps)
        took = f' · {elapsed(now - m.since)}' if m.busy and m.since else ''
        agent = '' if m.role == MAIN_ROLE else state.ROLE_AGENTS[m.role]
        links = ([('jump', s.sid, 'Ir al pane' if s.pane else 'Ir a su tmux')]
                 if s.pane or s.sid in self.chat_sessions else [])
        links += [('talk', agent, 'Ver su chat' if agent else 'Hablarle'), ('back', None, '‹ Volver')]
        shown = m.steps[-8:]
        marks = {'done': ('✓', 'green'), 'waiting': ('?', 'yellow'), 'permission': ('›', 'red')}
        steps = []
        for i, (text, at) in enumerate(shown):
            if i == len(shown) - 1:
                mark, tone = marks.get(m.state, ('›', None))
                spent = 'ahora' if m.busy else ''
            else:
                mark, tone, spent = '✓', 'green', elapsed(shown[i + 1][1] - at)
            steps.append((mark, mascot.COLORS.get(tone, tone) if tone else '#f2f5ff', text, spent))
        others = [(o.role, app.MEMBER_PET.get(o.state, 'idle'), o.busy) for o in self.team(s) if o.role != m.role]
        empty = '' if n else (f'{agent or m.role} está libre. Ábrele su chat para encargarle algo: '
                              'trabajará en esta carpeta, al lado de los demás.')
        d = dict(role=m.role, name=m.role, color=color, pet=pet, busy=m.busy, label=self.tab_labels()[s.sid],
                 summary=(f'{n} paso{"" if n == 1 else "s"}{took}' if n or m.busy else 'libre'),
                 steps=steps, links=links, others=others, hidden=n - len(shown), empty=empty)
        panel = self.frame.focus
        panel.set_focus(d, dict(face=self.window_face, link=self.window_link, other=self.window_card,
                                pick=self.ensure_tick))
        panel.animate()
        # Sus pasos piden lo que miden: la ventana crece hasta donde cabe la pantalla.
        width = panel.get_width() or self.app_win.get_width() or MIN_W
        room = self.screen_h - FIT_H - FOCUS_ROOM if self.screen_h else 0
        self.window_body = max(0, panel.natural_h(width) - app.TABS_H)
        if room:
            self.window_body = min(self.window_body, room)
        panel.place(app.TABS_H + self.body_h())

    def window_link(self, kind, key):
        """Un enlace del desglose: al pane, a su chat o de vuelta al tablero."""
        s = self.tab_session()
        if kind == 'back':
            self.focus = None
        elif kind == 'jump' and s is not None:
            sess = self.model.sessions.get(key)
            if sess is not None:
                self.go(sess)
        elif kind == 'talk' and s is not None:
            c = self.chat_of(s, key)
            if c is not None:
                self.show_chat(c, typing=True)
            else:
                self.open_chat(typing=True, agent=key, cwd=self.tab_place(s))

    def window_face(self, cr, role, pet, w, h, moving):
        side = min(w, h)
        if not moving:
            mascot.paint_static(cr, role, pet, w / 2, h / 2, side)     # quieta: ya dibujada una vez
            return
        cr.translate(w / 2, h / 2)
        cr.scale(side / 253, side / 253)
        mascot.draw(cr, pet, 1.0, time.monotonic(), motion=1, role=role)

    def window_card(self, role, busy):
        """Un clic en una tarjeta: su desglose; en uno libre, a encargarle algo."""
        s = self.tab_session()
        if s is None or (not busy and role == MAIN_ROLE):
            return
        if busy:
            self.focus = (s.sid, role)
        else:
            from . import state
            self.open_chat(typing=True, agent=state.ROLE_AGENTS[role], cwd=self.tab_place(s))

    def window_decide(self, allow):
        asking = self.asking()
        if asking is not None:
            self.model.decide(asking, allow)
            self.refresh()

    def chat_head_widget(self):
        """¿La cabecera y los agentes del chat los llevan los widgets?"""
        return self.frame is not None and self.windowed and self.target() == 'chat' and not self.wf_open

    def window_agents(self):
        """La barra lateral en el chat: un agente por fila, con su cara, y el
        que habla elegido; si trabaja o pregunta, también en texto."""
        from . import state
        cwd = self.chat.cwd if self.chat is not None else ''
        rows = []
        for role in state.TEAM:
            agent = '' if role == state.MAIN_ROLE else state.ROLE_AGENTS[role]
            other = self.chats.get(self.chat_key(agent, cwd))
            text = 'Pide permiso' if other is not None and other.asking else \
                'Trabaja' if other is not None and other.busy else ''
            rows.append((f'agent:{agent}', state.ROLE_AGENTS[role], None, text, role))
        chosen = f'agent:{self.chat.agent}' if self.chat is not None else 'agent:'
        return rows, chosen, self.window_row_face

    def window_row_face(self, cr, role, w, h):
        self.window_face(cr, role, 'idle', w, h, False)

    def window_chat_head(self):
        head = self.frame.chat_head
        if not self.chat_head_widget():
            head.place(0)
            return
        from . import chatview, state
        c = self.chat
        role = self.chat_role()
        status, _tone = self.chat_status()
        info = dict(role=role, pet=self.chat_pet(), name=c.name if c is not None else state.MAIN_AGENT,
                    color=mascot.accent(role), project=c.project if c is not None else '',
                    status=status, where=state.tilde(c.cwd) if c is not None else '',
                    busy=bool(c is not None and c.busy), can_split=self.chat_can_split(),
                    edited=len(gitview.inside(c.cwd, c.edited)) if c is not None else 0)
        head.set_info(info, dict(face=self.window_face, act=self.window_chat_act))
        head.place(chatview.CHAT_HEAD + 2)

    def window_sources(self):
        """La vista Fuentes: una fila por fuente y el detalle de la elegida."""
        from . import app, commands, sources
        panel = self.frame.sources
        if self.chat_open or self.projects_open or self.wf_open:
            self.sources_open = False           # otra vista la tapó: ya no es la de Fuentes
        panel.set_visible(self.sources_open)
        if not self.sources_open:
            return
        now = time.monotonic()
        dots = {'on': 'green', 'bad': 'red', 'unknown': 'yellow'}
        rows = []
        for key, label in sources.SOURCES:
            state = self.source_state(key)
            note = self.source_note(key) if state != 'off' else ''
            text = sources.STATE_TEXT[state].capitalize() + (f' · {note}' if note else '')
            color = dots.get(state)
            rows.append((key, label, mascot.COLORS.get(color, color) if color else None, text))
        key = self.sources_pick if self.sources_pick in sources.LABELS else 'claude'
        state, src = self.source_state(key), self.sources.get(key) or {}
        status = sources.STATE_TEXT[state].capitalize()
        if state == 'bad' and src.get('since'):
            status += f' desde {app.ago(now - src["since"])}'
        cmds = [(r[1], r[2]) for r in commands.reference(key, commands.load()) if r[0] == 'cmd']
        items = sorted(src.get('items') or [], key=lambda it: it.get('tone') != 'bad') if key == 'github' else []
        items = [dict(label=f'{it["where"]}#{it["number"]} {it["title"]}', note=it['note'], url=it['url'])
                 for it in items if state == 'on']
        detail = dict(key=key, title=sources.LABELS[key], retry=key in ('github', 'devherd') and state != 'off',
                      items=items, status=status, about=sources.ABOUT[key],
                      lines=[] if state != 'on' else list(src.get('tip') or []),
                      why=(src.get('why') or src.get('note') or sources.MISSING.get(key, '')) if state == 'bad' else '',
                      fix=src.get('fix', '') if state == 'bad' else '',
                      toggle=key != 'claude', on=state != 'off', cmds=cmds)
        panel.set_data(rows, key, detail, dict(pick=self.window_source_pick, toggle=self.toggle_source,
                                                      retry=self.window_retry, open=self.window_open_url))

    def flows_widgets(self):
        """¿La lista de workflows la llevan los widgets? En la ventana y en su
        pantalla de lista; el editor, la corrida y sus preguntas son del dibujo."""
        return (self.frame is not None and self.windowed and self.wf_open and self.wf_screen == 'list'
                and self.wf_confirm is None and self.wf_error is None)

    def window_flows(self):
        panel, on = self.frame.flows, self.flows_widgets()
        panel.set_visible(on)
        if self.flows_overlay is not None:
            self.flows_overlay.set_visible(self.wf_open and not on)     # el dibujo, solo cuando las tarjetas no
        if not on:
            return
        run = self.wf_run
        busy = run is not None and run.running
        here = self.wf_here()
        rows = []
        for w in self.workflows:
            mine = run is not None and run.w.name == w.name
            place = (self.project_label(w.project) if w.project
                     else f'donde estés (ahora {self.project_label(here)})' if here else 'donde estés')
            steps = '1 paso' if len(w.steps) == 1 else f'{len(w.steps)} pasos'
            rows.append(dict(name=w.name, place=f'{steps} · {place}', mine=mine, busy=mine and busy,
                             status=run.status().rstrip('.…').lower() if mine else '',
                             launch=bool(w.steps) and not busy, delete=not (mine and busy)))
        panel.set_flows(rows, dict(act=self.window_flow_act))

    def window_flow_act(self, key):
        self.on_wf_hit(key)
        self.wf_redraw()
        self.ensure_tick()

    def window_panels(self):
        """La campana (con su contador), la bandeja de alertas y los ajustes."""
        from . import sources
        frame = self.frame
        pending = self.alerts()
        frame.set_bell(len(pending))
        if self.chat_open or self.projects_open or self.wf_open:
            self.panel_open = ''
        frame.alerts.set_visible(self.panel_open == 'alerts')
        frame.settings.set_visible(self.panel_open == 'settings')
        frame.tmux.set_visible(self.panel_open == 'tmux')
        if self.panel_open == 'tmux':
            frame.tmux.set_sessions(self.window_tmux(), dict(jump=self.window_tmux_jump))
        self.window_code_views(frame)
        frame.pomodoro.set_visible(self.panel_open == 'pomodoro')
        if self.panel_open == 'pomodoro':
            status, tasks = self.pomo_watch.read()
            frame.pomodoro.set_pomodoro(status, tasks, dict(act=self.window_pomodoro,
                                                            agent=self.window_pomodoro_agent))
        if self.panel_open == 'alerts':
            tones = {'': 'red', 'ok': 'green', 'info': 'yellow', 'run': 'metal'}
            cards = []
            for s in pending:
                color = tones.get(s.tone, 'red')
                buttons = [('dismiss', 'Descartar')] + [(i, a['label']) for i, a in enumerate(s.actions)]
                cards.append(dict(sid=s.sid, title=s.name or s.proj or s.sid, buttons=buttons,
                                  color=mascot.COLORS.get(color, color), lines=list(s.lines),
                                  where=s.where, note=s.note))
            frame.alerts.set_alerts(cards, dict(act=self.window_alert))
        elif self.panel_open == 'settings':
            st = self.settings
            rows = [('glass', 'Vidrio', bool(st['glass']), 'La ventana translúcida, desenfocada por Hyprland.'),
                    ('compact', 'Modo compacto', bool(st['compact']), 'De la isla suelta; la ventana no lo usa.'),
                    ('pinned', 'Isla fijada', bool(st['pinned']), 'De la isla suelta; la ventana ya está abierta.'),
                    ('chat_tech', 'Chat técnico', bool(st['chat_tech']), 'Bloques y tablas con borde fino y títulos en mayúsculas.'),
                    ('tech_style', 'Estilo técnico', bool(st['tech_style']),
                     'Esquinas rectas, bordes de 1 px y toda la letra monoespaciada.'),
                    ('tired_eyes', 'Vista cansada', bool(st['tired_eyes']),
                     'Letra más grande y más gruesa, y textos apagados más claros (tamaño abajo).')]
            rows += [(key, f'Fuente: {label}', bool(st[key]), '') for key, label in sources.SOURCES if key != 'claude']
            frame.settings.set_rows(rows, st['position'], dict(toggle=self.window_setting, move=self.move,
                                                               theme=self.window_theme, font=self.window_font,
                                                               tired_scale=self.window_tired_scale,
                                                               pick_theme=self.pick_theme),
                                    fonts.current, themes.current, round(fonts.TIRED_SCALE * 100))

    def window_code_views(self, frame):
        """Editor, Terminal y Taller: los tres miran el mismo proyecto. Cada uno solo trabaja a la vista."""
        open_ = self.panel_open
        frame.terminal.set_visible(open_ == 'terminal')
        frame.editor.set_visible(open_ == 'editor')
        frame.taller.set_visible(open_ == 'taller')
        root = self.window_editor_root()
        frame.terminal.set_terminal(root, open_ == 'terminal')
        frame.taller.terminal.set_terminal(root, open_ == 'taller')
        shown = {'editor': frame.editor, 'taller': frame.taller.editor}
        for key, editor in shown.items():
            editor.nvim.set_terminal(root, open_ == key)
        if open_ in shown:
            self.git_watch.watch(root)
            shown[open_].files.set_files(self.git_watch.read(), self.window_editor_open,
                                         self.window_edited(root))
            frame.taller.fit(self.app_win.get_height() - frame.chrome_h())

    def window_edited(self, root):
        """Los archivos que Claude cambió en los chats de ese proyecto, relativos a él, el último primero."""
        chats = sorted((c for c in self.all_chats() if c.cwd == root), key=lambda c: c.touched, reverse=True)
        return gitview.inside(root, [path for c in chats for path in c.edited]) if root else []

    def window_editor_open(self, path):
        """Un clic en la lista del Editor o del Taller: se elige el archivo y se le pide a nvim que lo abra."""
        self.git_watch.choose(path)
        root = self.git_watch.root

        def go():
            ok, why = terminal.open_in_nvim(root, path)
            if not ok:
                GLib.idle_add(self.on_message, {'event': 'alert', 'session_id': 'nvim', 'name': 'nvim',
                                                'message': why or 'nvim no abrió el archivo', 'tone': '',
                                                'ttl': 20}, None)
        threading.Thread(target=go, daemon=True).start()

    def editor_goal(self):
        """El alto que pide el editor: lo que cabe en la pantalla, hasta EDITOR_H."""
        room = self.screen_h - FIT_H - self.frame.chrome_h() - FIT_PAD if self.screen_h and self.frame else EDITOR_H
        return max(MIN_H, min(EDITOR_H, room))

    def window_editor_root(self):
        """La carpeta que muestra el editor: la del chat que se tiene, o la del proyecto de tmux."""
        if self.chat is not None and self.chat.cwd:
            return self.chat.cwd
        here = self.project_here()
        return here.path if here is not None else ''

    def window_pomodoro(self, order, *args):
        """Un botón de la vista Pomodoro: se le pide a `coffe` y se vuelve a preguntar."""
        def go():
            ok, said = pomodoro.run(order, *args)
            if not ok:
                GLib.idle_add(self.on_message, {'event': 'alert', 'session_id': 'coffe', 'name': 'coffe',
                                                'message': said or f'coffe {order} falló', 'tone': '', 'ttl': 20}, None)
            self.pomo_watch.refresh()
        threading.Thread(target=go, daemon=True).start()

    def window_pomodoro_agent(self, task, repo):
        """«Con agente»: arranca el pomodoro de la tarea y abre el chat en la carpeta
        de su proyecto. Si `coffe` se niega (ya hay un pomodoro, descanso…), no se abre."""
        def go():
            ok, said = pomodoro.run('start', task)
            if ok:
                GLib.idle_add(self.pomodoro_chat, repo)
            else:
                GLib.idle_add(self.on_message, {'event': 'alert', 'session_id': 'coffe', 'name': 'coffe',
                                                'message': said or 'coffe start falló', 'tone': '', 'ttl': 20}, None)
            self.pomo_watch.refresh()
        threading.Thread(target=go, daemon=True).start()

    def pomodoro_chat(self, repo):
        self.pomo_repo = repo
        self.open_chat(typing=True, agent='', cwd=repo)
        return GLib.SOURCE_REMOVE

    def window_tmux(self):
        """Las sesiones de tmux con el estado de los Claude de cada ventana."""
        return self.tmux_sessions()

    def tmux_sessions(self, fresh=False):
        """Lo mismo, o None si tmux aún no contestó; `fresh` pregunta en el acto."""
        found = tmuxsessions.snapshot() if fresh else self.tmux_watch.read()
        if found is None:
            return None
        claude = [(s.pane, s.state, [a.role for a in s.agents.values()])
                  for s in self.model.sessions.values() if s.pane]
        return tmuxsessions.merge(found, claude)

    def window_tmux_jump(self, session, window):
        threading.Thread(target=tmuxsessions.jump, args=(session, window), daemon=True).start()
        self.tmux_watch.refresh()

    def window_alert(self, sid, key):
        s = self.model.sessions.get(sid)
        if s is None:
            return
        if key == 'dismiss':
            self.model.dismiss(s)       # sin ficha tampoco: se va y no vuelve en 15 min
            self.refresh()
            self.ensure_tick()
        else:
            self.act(s, key)

    def window_setting(self, key):
        if key == 'glass':
            self.settings['glass'] = not self.settings['glass']
            settings.save(self.settings)
            self.ensure_tick()
        elif key == 'compact':
            self.settings['compact'] = not self.settings['compact']
            settings.save(self.settings)         # la ventana no usa el compacto: vale al volver la isla
        elif key == 'pinned':
            self.settings['pinned'] = not self.settings['pinned']
            settings.save(self.settings)
        elif key == 'chat_tech':
            self.settings['chat_tech'] = not self.settings['chat_tech']
            settings.save(self.settings)
            self.ensure_tick()
            self.overlay.queue_draw()
        elif key == 'tech_style':
            self.set_techno(not self.settings['tech_style'])
            self.settings['tech_style'] = fonts.techno
            settings.save(self.settings)
            windowframe.use_theme()          # el CSS recto se rehace
            windowframe.load_fonts()
            self.chat_theme()
            self.ensure_tick()
            self.overlay.queue_draw()
        elif key == 'tired_eyes':
            self.set_tired(not self.settings['tired_eyes'])
            self.settings['tired_eyes'] = fonts.tired
            settings.save(self.settings)
            windowframe.use_theme()          # el vidrio cambia de opacidad
            windowframe.load_fonts()
            self.chat_theme()
            self.ensure_tick()
            self.overlay.queue_draw()
        else:
            self.toggle_source(key)

    def window_tired_scale(self, pct):
        """Cambia cuánto agranda la vista cansada (125, 150 o 200 %) y lo guarda."""
        if fonts.use_scale(pct) == self.settings['tired_scale']:
            return
        self.settings['tired_scale'] = round(fonts.TIRED_SCALE * 100)
        settings.save(self.settings)
        windowframe.load_fonts()
        self.chat_theme()
        self.ensure_tick()
        self.overlay.queue_draw()

    def window_font(self, family):
        """Cambia la letra de la app, en la isla y en la ventana, y la guarda."""
        if fonts.valid(family) == fonts.current:
            return
        self.settings['font'] = fonts.use(family)
        settings.save(self.settings)
        windowframe.load_fonts()
        self.ensure_tick()
        self.overlay.queue_draw()

    def pick_theme(self, name):
        """Cambia el tema de la isla y de la ventana, y lo guarda."""
        if themes.valid(name) == themes.current:
            return
        self.settings['theme'] = themes.use(name)
        settings.save(self.settings)
        self.load_theme()
        windowframe.load_fonts()
        self.ensure_tick()
        self.overlay.queue_draw()

    def window_theme(self):
        self.load_theme()
        self.ensure_tick()

    def window_help(self):
        """El diálogo de ayuda: atajos del teclado, del ratón y comandos."""
        from . import commands
        if self.help_win is None or not self.help_win.get_visible():
            self.help_win = windowframe.HelpDialog(self.app_win, self.frame.help)
        sections = commands.load()
        blocks = [('Teclado', commands.shortcuts(hypr.binds())), ('Ratón', sections.get('raton') or []),
                  ('Terminal', sections.get('engineer') or [])]
        blocks += [(name, sections.get(name) or []) for name in ('devherd', 'coffe', 'github', 'terminal', 'usage')]
        self.help_win.set_items([(title, what, text) for title, items in blocks for what, text in items])
        self.help_win.present()
        self.help_win.search.grab_focus()

    @staticmethod
    def window_retry(key):
        """Reintentar: la fuente consulta ya, sin esperar su turno."""
        from . import devherd, github
        {'github': github, 'devherd': devherd}[key].retry()

    @staticmethod
    def window_open_url(url):
        import threading
        from . import actions
        threading.Thread(target=actions.run, args=({'cmd': ['xdg-open', url], 'label': 'PR'},),
                         daemon=True).start()

    def window_source_pick(self, key):
        self.sources_pick = key

    def window_chat_act(self, key):
        if key == 'files':
            self.window_view('editor')      # los archivos que tocó el agente, en el Editor
            return
        self.on_chat_hit(key)

    def window_pick(self, sid):
        """Una fila de la barra lateral: esa sesión pasa a ser la del tablero
        o, en el chat, ese agente el que habla."""
        if sid.startswith('agent:'):
            self.on_chat_hit(sid)
            return
        if sid != self.tab:
            self.tab, self.focus = sid, None
            self.tab_manual = True

    def window_rows(self):
        """Las filas de la barra lateral: nombre, punto y estado en texto."""
        labels, now = self.tab_labels(), time.monotonic()
        rows = []
        for s in self.tabs():
            color = self.tab_dot(s)
            rows.append((s.sid, labels[s.sid], mascot.COLORS.get(color, color) if color else None,
                         self.window_state(self.team(s), now)))
        return rows

    @staticmethod
    def window_state(team, now):
        """El estado de una sesión en palabras, el más urgente primero."""
        states = {m.state for m in team}
        if 'permission' in states:
            return 'Pide permiso'
        if 'working' in states:
            since = min((m.since for m in team if m.state == 'working' and m.since), default=0)
            return f'Trabaja · {elapsed(now - since)}' if since else 'Trabaja'
        if 'waiting' in states:
            return 'Espera respuesta'
        return 'Terminó' if 'done' in states else 'En reposo'

    def window_current(self):
        if self.panel_open:
            return self.panel_open
        if self.sources_open:
            return 'sources'
        if self.wf_open:
            return 'flows'
        if self.chat_open:
            return 'chat'
        if self.projects_open:
            return 'projects'
        return 'board'

    def window_size(self):
        """Con el tamaño con el que la isla abierta cabe entera, sin pasarse de la pantalla."""
        width, height = self.island_w, min(self.island_h, OPEN_H)
        if self.screen_h:
            height = min(height, self.screen_h - FIT_H)
        if self.screen_w:
            width = min(width, self.screen_w)
        return max(width, MIN_W), max(height, MIN_H)

    def window_fit(self, content_h, room):
        """El alto de la ventana sigue al del contenido (más el sitio de las
        burbujas de las pastillas), para que no quede un negro debajo.
        Si Yared la estira (el alto ya no es el que se pidió), su medida manda:
        se guarda y vale para lo alto (el chat). Un contenido mucho más corto
        (el tablero) la encoge igual, sin pisar la medida guardada, y al
        volver lo alto recupera la suya."""
        if self.app_win is None:
            return
        chrome = 0
        if self.frame is not None:
            self.frame.sync(self.window_current())
            self.frame.fold(self.app_win.get_width())
            self.frame.set_glass(bool(self.settings['glass']))
            if self.window_panels_due(time.monotonic()):
                if self.chat_head_widget():
                    self.frame.set_sessions(*self.window_agents())
                else:
                    self.frame.set_sessions(self.window_rows(), self.tab, self.window_row_face)
                self.window_board()
                self.window_chat_head()
                self.window_sources()
                self.window_panels()
                self.window_flows()
            chrome = self.frame.chrome_h()      # la barra de título también es alto de ventana
        now = time.monotonic()
        height = self.app_win.get_height()
        want = max(MIN_H, int(content_h) + int(room) + FIT_PAD + chrome)
        floor = want                    # lo que mide el contenido: más corta, la ventana le corta lo de abajo
        if self.fit_h and height and abs(height - self.fit_h) >= FIT_STEP and now - self.fit_at > FIT_SETTLE \
                and height >= floor - FIT_STEP:
            # No es el alto que se pidió: Yared la estiró.
            self.fit_manual, self.fit_shrunk = True, False
            self.fit_h = height
            self.window_remember(force=True)
            return
        if self.fit_manual:
            kept = self.window_kept()
            tall = height >= floor - FIT_STEP    # una más corta que el contenido no se guarda como su medida
            if kept is None:
                if tall:
                    self.window_remember()
                    return
            else:
                self.fit_shrunk = kept[1] - floor > FIT_VOID
                want = floor if self.fit_shrunk else max(floor, kept[1])
                if tall:
                    self.window_remember()
        if self.fit_h and want < self.fit_h and self.fit_h - want < FIT_HOLD \
                and not (height and height < floor - FIT_STEP):
            return                      # lo que sobra es poco: mejor un poco de aire que una ventana que salta
        if abs(want - self.fit_h) < FIT_STEP and not (height and height < floor - FIT_STEP):
            return
        self.fit_h, self.fit_at = want, now
        self.window_resize(self.app_win.get_width() or MIN_W, want)

    def window_resize(self, width, height):
        # GTK no encoge una ventana flotante cambiándole el tamaño por defecto:
        # se lo pedimos a Hyprland, que es quien la dimensiona.
        cmd = f'dispatch resizewindowpixel exact {width} {height},class:{CLASS_RE}'

        def ask():
            try:
                hypr.request(cmd)
            except OSError:
                if self.hypr_async:
                    GLib.idle_add(self.app_win.set_default_size, width, height)     # desde un hilo, por el bucle de GTK
                else:
                    self.app_win.set_default_size(width, height)

        if self.hypr_async:
            threading.Thread(target=ask, daemon=True, name='resize').start()   # no frena la interfaz
        else:
            ask()

    # ── el tamaño que Yared le deja ─────────────────────────────────────────

    def window_kept(self):
        """El tamaño guardado de la última vez, o None."""
        size = self.settings.get('window_size')
        if (isinstance(size, (list, tuple)) and len(size) == 2
                and all(isinstance(n, int) and MIN_W <= n <= 8000 for n in size)):
            return tuple(size)
        return None

    def window_remember(self, force=False):
        """Guarda el tamaño actual de la ventana para la próxima vez; sin
        `force`, como mucho cada REMEMBER_SECS y solo si cambió."""
        if self.app_win is None:
            return
        now = time.monotonic()
        width, height = self.app_win.get_width(), self.app_win.get_height()
        kept = self.window_kept()
        if self.fit_shrunk and kept:
            height = kept[1]                # encogida por un contenido corto: la medida de Yared no cambia
        saved_w, saved_h, at = self.fit_saved
        if not width or not height or (width, height) == (saved_w, saved_h):
            return
        if not force and now - at < REMEMBER_SECS:
            return
        self.fit_saved = (width, height, now)
        self.settings['window_size'] = [width, height]
        self.window_save()

    def window_restore(self, size):
        self.fit_h, self.fit_at = size[1], time.monotonic()     # lo pedido: no se toma por estirada
        self.window_resize(*size)
        return GLib.SOURCE_REMOVE

    # ── eventos ─────────────────────────────────────────────────────────────

    def on_window_close(self, _win):
        self.close_window()
        return True                     # la ventana ya la quitamos nosotros

    def on_window_focus(self, win, _param):
        """Sin foco, la caja del chat no recibe teclas: se deja de «escribir».
        Al volver, el chat que estaba a la vista vuelve a tomar el teclado sin
        un clic, como cualquier app."""
        if not win.is_active():
            self.window_typed = self.chat_typing
            if self.chat_typing:
                self.chat_type(False)
        elif self.windowed and self.chat_open and not self.chat_typing and getattr(self, 'window_typed', True):
            self.chat_type(True)

    def window_save(self):
        settings.save(self.settings)
