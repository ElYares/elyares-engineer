"""El panel Git de la isla suelta: el flujo de ramas del proyecto, paso a paso.

Arriba, dónde estás en la cadena (abuelo ← padre ← rama de ahora); debajo, los pasos para subir
el trabajo: commit, subir la rama, PR al padre, merge y, si hace falta, lo mismo del padre al
abuelo. Cada paso lleva su botón y pide un segundo clic para confirmar. Si una rama de la cadena
no existe (`develop`), pregunta a cuál va en vez de ella. La lógica está en `gitflow.py`; aquí solo
se dibuja y se manda cada orden en un hilo, con el aro girando mientras `git`/`gh` contestan.

Se abre desde el panel «Más» o con `elyares-ctl gitflow`. `GitFlowView` es parte de la isla
(`app.Island` la hereda) y usa sus ayudantes de dibujo.
"""

import math
import threading
import time

import cairo

from . import gitflow, gitsuggest, mascot, prefsview, themes

GF_ROW = 30
GF_W = 600                       # la isla se ensancha para este panel; al cerrarlo vuelve a su tamaño
GF_SUG_LOADING_H = 44
GF_SUG_ERROR_H = 96
GF_MSG_PARAGRAPHS = 6            # párrafos del mensaje que se muestran; el resto se corta
GF_MSG_LINES = 2                 # líneas de cada párrafo (Pango cuenta por párrafo, no en total)
GF_PAD = 12                      # aire dentro del bloque del mensaje
GF_REFRESH = 6.0                 # cada cuánto se vuelve a mirar `git` y `gh` con el panel a la vista
GF_CONFIRM_SECS = 4              # lo que dura el «¿Seguro?» tras el primer clic
GF_RESULT_SECS = 10              # cuánto se queda el resultado de una orden
GF_SPIN_SECS = 0.9
BTN_W = 124


class GitFlowView:
    """Lo que guarda: `gf_open`, `gf_data` (raíz, flujo y pasos de la última lectura), `gf_busy` (la orden
    en camino), `gf_confirm` (el botón que espera su segundo clic) y `gf_result` (qué dijo la última orden)."""

    gf_open = False
    gf_data = None
    gf_loading = False
    gf_busy = None
    gf_confirm = None
    gf_result = None
    gf_at = 0.0
    gf_seen = None
    gf_msg_cache = (None, ('', 0))    # el último mensaje medido: ((texto, ancho), (texto a dibujar, alto))
    gf_sug = None                # el mensaje sugerido: {'loading': True} o {'text', 'files', 'lines', 'risky', 'error'}

    def gf_root(self):
        """El repositorio del proyecto a la vista ('' si no hay uno)."""
        return gitflow.toplevel(self.window_editor_root())

    def toggle_gitflow(self):
        """Abre o cierra el panel. En la ventana no hay: sus vistas están en la barra de título."""
        if self.windowed:
            return
        self.gf_open = not self.gf_open
        self.off = False
        if self.gf_open:
            if self.chat_open:
                self.close_chat()
            self.projects_open = self.prefs_open = self.more_open = self.boxes_open = self.themes_open = self.sp_open = self.sv_open = self.pm_open = False
            self.gf_data, self.gf_confirm, self.gf_result, self.gf_seen, self.gf_sug = None, None, None, set(), None
            self.gf_refresh()
        self.ensure_tick()

    def gf_refresh(self):
        """Vuelve a leer `git` y `gh` en un hilo; el panel sigue con lo anterior (o el esqueleto) mientras."""
        if self.gf_loading:
            return
        self.gf_loading, self.gf_at = True, time.monotonic()
        root = self.gf_root()

        def go():
            try:
                if not root:
                    self.gf_data = ('', None, [])
                else:
                    flow = gitflow.resolve(root)
                    self.gf_data = (root, flow, gitflow.status(root, flow))
            except Exception:
                self.gf_data = (root, None, [])
            finally:
                self.gf_loading = False
        threading.Thread(target=go, daemon=True).start()

    def gf_tick(self, now):
        """Cada segundo: con el panel a la vista y nada en camino, se vuelve a mirar cada GF_REFRESH."""
        if self.gf_open and not self.windowed and not self.gf_busy and now - self.gf_at > GF_REFRESH:
            self.gf_refresh()

    def gitflow_busy(self):
        """¿Hay algo que animar? Aún no hay lectura, o una orden va en camino."""
        return self.gf_open and not self.windowed and (self.gf_data is None or bool(self.gf_busy)
                                                       or bool(self.gf_sug and self.gf_sug.get('loading')))

    def gf_prompt(self):
        """¿Se muestra la pregunta «seguir aquí o rama nueva»? Una vez por rama y por apertura del panel."""
        if not self.gf_data or not self.gf_data[1]:
            return False
        flow = self.gf_data[1]
        return (flow.root, flow.branch) not in self.gf_seen and bool(flow.parent) and flow.branch != flow.parent

    def gf_message(self, text, width):
        """El mensaje sugerido listo para dibujar: sus primeros párrafos, y lo que miden de alto. Se mide con
        el tipo de letra de verdad (cuadro nuevo de Cairo): el alto sale de lo que de verdad ocupa."""
        key = (text, int(width))
        if self.gf_msg_cache[0] != key:
            body = [p for p in text.replace(gitsuggest.TRAILER, '').strip().splitlines() if p.strip()][:GF_MSG_PARAGRAPHS]
            shown = '\n'.join(body)
            cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
            height = self._layout(cr, shown, prefsview.FONT_PREFS_NOTE, width, GF_MSG_LINES).get_pixel_size()[1]
            self.gf_msg_cache = (key, (shown, height))
        return self.gf_msg_cache[1]

    def gf_sug_h(self):
        """Lo que mide el bloque de la sugerencia: el aro, un error, o el mensaje con su nota y sus botones."""
        sug = self.gf_sug
        if not sug:
            return 0
        if sug.get('loading'):
            return GF_SUG_LOADING_H
        if sug.get('error'):
            return GF_SUG_ERROR_H
        height = self.gf_message(sug['text'], GF_W - 2 * prefsview.PREFS_PAD - 2 * GF_PAD)[1]
        return GF_PAD + height + 8 + 18 + 6 + (GF_ROW - 6) + GF_PAD + 8

    def gitflow_goal(self):
        _, flow, steps = self.gf_data or ('', None, [])
        rows = max(3, len(steps)) if flow else 3
        extra = self.gf_sug_h() + (GF_ROW + 8 if self.gf_prompt() else 0) + (GF_ROW * (1 + len(flow.options)) if flow and flow.ask else 0)
        return GF_W, prefsview.PREFS_HEAD + GF_ROW * bool(flow) + extra + rows * GF_ROW + prefsview.PREFS_FOOT + 6

    def gf_spinner(self, cr, cx, cy, r, alpha):
        turn = 0.0 if self.motion_reduced() else (time.monotonic() % GF_SPIN_SECS) / GF_SPIN_SECS * 2 * math.pi
        cr.new_sub_path()
        cr.arc(cx, cy, r, turn, turn + math.pi * 1.5)
        cr.set_source_rgba(*themes.hot(), .9 * alpha)
        cr.set_line_width(1.6)
        cr.stroke()

    def draw_gitflow(self, cr, x0, w, h, alpha):
        pad = prefsview.PREFS_PAD
        left, width = x0 + pad, w - 2 * pad
        soft = mascot.rgba(self.ink('text', .62))[:3]
        head = mascot.rgba(self.ink('head'))[:3]
        self.put(cr, 'Git', prefsview.FONT_PREFS_TITLE, left, 14, mascot.rgba(self.ink('text'))[:3], alpha)
        if self.gitflow_busy() or self.gf_loading and self.gf_data is None:
            self.gf_spinner(cr, left + 48, 22, 5, alpha)
        layout = self._layout(cr, 'Cerrar', 'Sans Semi-Bold 9')
        lw, lh = layout.get_pixel_size()
        x = left + width - lw
        over = self.over(x - 4, 10, lw + 8, lh + 8)
        self.tip_text(cr, layout, x, 14, themes.hot() if over else mascot.rgba(self.ink('text', .7))[:3], alpha, False)
        self.hits.append(('gitflow', ('close',), x - 4, 10, lw + 8, lh + 8))
        cr.set_source_rgba(*themes.glow(), .07 * alpha)
        cr.rectangle(left, prefsview.PREFS_HEAD - 8, width, 1)
        cr.fill()
        y = prefsview.PREFS_HEAD
        if self.gf_data is None:
            self.draw_gf_skeleton(cr, left, y, width, alpha)
            self.put(cr, 'Leyendo git y gh…', prefsview.FONT_PREFS_NOTE, left + 4, h - prefsview.PREFS_FOOT + 4, soft, alpha * .9)
            return
        root, flow, steps = self.gf_data
        if flow is None:
            self.put(cr, 'Sin proyecto con git a la vista.' if not root else 'No pude leer este repositorio.',
                     prefsview.FONT_PREFS, left + 4, y + 4, soft, alpha)
            self.put(cr, 'Abre un chat o elige una sesión en un repositorio.', prefsview.FONT_PREFS_NOTE,
                     left + 4, y + 22, soft, alpha * .9, width=width)
            return
        self.draw_gf_chain(cr, flow, left, y, width, head, soft, alpha)
        y += GF_ROW
        if self.gf_prompt():
            y = self.draw_gf_prompt(cr, flow, left, y, width, head, soft, alpha)
        if flow.ask:
            y = self.draw_gf_ask(cr, flow, left, y, width, head, soft, alpha)
        if self.gf_sug:
            y = self.draw_gf_sug(cr, left, y, width, head, soft, alpha)
        for step in steps:
            self.draw_gf_step(cr, step, left, y, width, head, soft, alpha)
            y += GF_ROW
        self.draw_gf_foot(cr, left, h, width, soft, alpha)

    def draw_gf_skeleton(self, cr, x, y, w, alpha):
        beat = .5 if self.motion_reduced() else .5 + .5 * math.sin(time.monotonic() % 1.3 / 1.3 * 2 * math.pi)
        for i in range(3):
            for bx, bw in ((x + 4, 14), (x + 26, w * (.5 - .07 * i)), (x + w - BTN_W, BTN_W)):
                mascot.box(cr, bx, y + i * GF_ROW + 7, bw, GF_ROW - 16, 6)
                cr.set_source_rgba(*themes.glow(), (.05 + .09 * beat) * alpha)
                cr.fill()

    def draw_gf_chain(self, cr, flow, x, y, w, head, soft, alpha):
        """Abuelo ← padre ← rama de ahora, con la de ahora resaltada."""
        names = [(flow.grand or '—'), (flow.parent or '—'), flow.branch]
        cx = x + 4
        for i, name in enumerate(names):
            color = themes.hot() if i == 2 else head if name != '—' else soft
            cx += self.put(cr, name, prefsview.FONT_PREFS, cx, y + 4, color, alpha, width=max(60, w // 3 - 30)) + 8
            if i < 2:
                cx += self.put(cr, '←', prefsview.FONT_PREFS, cx, y + 4, soft, alpha) + 8

    def draw_gf_prompt(self, cr, flow, x, y, w, head, soft, alpha):
        """«Estás en esta rama»: seguir aquí o abrir el chat para crear una nueva desde el padre."""
        self.put(cr, '¿Seguir aquí o rama nueva?', prefsview.FONT_PREFS_NOTE, x + 4, y + 8, soft, alpha, width=max(80, w - 240))
        bx = x + w
        for key, label in (('new', 'Rama nueva…'), ('stay', 'Seguir aquí')):
            bw = self._layout(cr, label, prefsview.FONT_PREFS_NOTE).get_pixel_size()[0] + 20
            bx -= bw
            self.draw_gf_button(cr, label, bx, y + 2, bw, ('prompt', key), alpha, False)
            bx -= 6
        return y + GF_ROW + 8

    def draw_gf_ask(self, cr, flow, x, y, w, head, soft, alpha):
        """Una rama de la cadena no existe: ¿a cuál va en vez de ella?"""
        self.put(cr, f'«{flow.ask}» no existe. ¿A qué rama va en su lugar?', prefsview.FONT_PREFS, x + 4, y + 6,
                 themes.hot(), alpha, width=w - 8)
        y += GF_ROW
        for name in flow.options:
            self.draw_gf_button(cr, name, x + 4, y + 2, min(w - 8, 130), ('ask', flow.ask, name), alpha, False)
            y += GF_ROW
        return y

    def draw_gf_sug(self, cr, x, y, w, head, soft, alpha):
        """El mensaje sugerido (o el aro mientras se redacta) con sus botones: Commitear, Otra, Editar en el chat."""
        sug, total = self.gf_sug, self.gf_sug_h()
        mascot.box(cr, x - 4, y, w + 8, total - 6, 8)
        cr.set_source_rgba(*themes.glow(), .06 * alpha)
        cr.fill()
        if sug.get('loading'):
            self.gf_spinner(cr, x + 14, y + 19, 5, alpha)
            self.put(cr, 'Redactando el mensaje…', prefsview.FONT_PREFS_NOTE, x + 30, y + 12, soft, alpha)
            return y + total
        if sug.get('error'):
            self.put(cr, sug['error'], prefsview.FONT_PREFS_NOTE, x + GF_PAD, y + GF_PAD, themes.tuple_of(themes.signal()[2]),
                     alpha, width=w - 2 * GF_PAD, lines=2)
            self.draw_gf_button(cr, 'Cerrar', x + GF_PAD - 4, y + total - GF_ROW - 2, 80, ('sug', 'drop'), alpha, False)
            return y + total
        inner = w - 2 * GF_PAD
        text, height = self.gf_message(sug['text'], inner)
        self.put(cr, text, prefsview.FONT_PREFS_NOTE, x + GF_PAD, y + GF_PAD, head, alpha, width=inner, lines=GF_MSG_LINES)
        note = f'{len(sug["files"])} archivos, {sug["lines"]} líneas'
        warn = sug['lines'] > gitsuggest.LINES_MAX or bool(sug['risky'])
        if sug['risky']:
            note = 'Fuera del commit (riesgosos): ' + ', '.join(sug['risky'][:3])
        elif sug['lines'] > gitsuggest.LINES_MAX:
            note += f' · pasa de ~{gitsuggest.LINES_MAX}: ¿partirlo?'
        top = y + GF_PAD + height + 8
        self.put(cr, note, prefsview.FONT_PREFS_NOTE, x + GF_PAD, top, themes.hot() if warn else soft, alpha, width=inner)
        bx = x + GF_PAD - 4
        for key, label, bw in (('use', 'Commitear', 96), ('again', 'Otra', 64), ('edit', 'Editar en el chat', 150), ('drop', 'Descartar', 90)):
            self.draw_gf_button(cr, label, bx, top + 24, bw, ('sug', key), alpha, key == 'use' and self.gf_busy == 'commit')
            bx += bw + 8
        return y + total

    def draw_gf_button(self, cr, label, x, y, w, key, alpha, pending, confirm=False):
        over = not pending and self.over(x, y, w, GF_ROW - 8)
        mascot.box(cr, x, y, w, GF_ROW - 8, 8)
        cr.set_source_rgba(*(themes.hot() if confirm else themes.glow()), (.30 if confirm else .18 if over else .09) * alpha)
        cr.fill()
        if pending:
            self.gf_spinner(cr, x + w / 2, y + (GF_ROW - 8) / 2, 5, alpha)
        else:
            self.put(cr, '¿Seguro?' if confirm else label, prefsview.FONT_PREFS_NOTE, x + w / 2, y + 4,
                     mascot.rgba(self.ink('head'))[:3], alpha, align=.5)
            self.hits.append(('gitflow', key, x, y, w, GF_ROW - 8))

    def draw_gf_step(self, cr, step, x, y, w, head, soft, alpha):
        green, amber, _red = themes.signal()
        icon, color = {'done': ('✓', green), 'todo': ('○', amber), 'wait': ('·', None), 'na': ('–', None)}.get(step.state, ('·', None))
        ink = themes.tuple_of(color) if color else soft
        self.put(cr, icon, prefsview.FONT_PREFS, x + 4, y + 5, ink, alpha)
        dim = step.state in ('wait', 'na')
        self.put(cr, step.label, prefsview.FONT_PREFS, x + 24, y + 3, soft if dim else head, alpha, width=w - BTN_W - 40)
        self.put(cr, step.note, prefsview.FONT_PREFS_NOTE, x + 24, y + 16, soft, alpha * .9, width=w - BTN_W - 40)
        if step.go:
            asking = self.gf_confirm is not None and self.gf_confirm[0] == step.key \
                and time.monotonic() - self.gf_confirm[1] < GF_CONFIRM_SECS
            self.draw_gf_button(cr, step.go, x + w - BTN_W, y + 1, BTN_W, ('step', step.key), alpha,
                                self.gf_busy == step.key, asking and step.key != 'commit')

    def draw_gf_foot(self, cr, x, h, w, soft, alpha):
        """Lo que dijo la última orden (verde si salió bien, rojo si no), y si no, a qué cuenta de gh habla."""
        if self.gf_result and time.monotonic() - self.gf_result[2] < GF_RESULT_SECS:
            green, _amber, red = themes.signal()
            self.put(cr, self.gf_result[0], prefsview.FONT_PREFS_NOTE, x + 4, h - prefsview.PREFS_FOOT + 2,
                     themes.tuple_of(green if self.gf_result[1] else red), alpha, width=w - 8)
        elif self.gf_data and self.gf_data[1] and not self.gf_data[1].declared:
            self.put(cr, 'Sin cadena en CLAUDE.md. Añade: «Flujo de git: main ← develop ← v2 ← v2-<tema>»',
                     prefsview.FONT_PREFS_NOTE, x + 4, h - prefsview.PREFS_FOOT + 2, soft, alpha * .9, width=w - 8)

    def on_gitflow_hit(self, key):
        """Un clic: cerrar, la pregunta de arriba, la elección de una rama o un paso (con confirmación)."""
        kind = key[0]
        if kind == 'close':
            self.gf_open = False
        elif kind == 'prompt':
            flow = self.gf_data[1]
            self.gf_seen.add((flow.root, flow.branch))
            if key[1] == 'new':
                self.gf_new_branch(flow)
        elif kind == 'ask':
            gitflow.remember(self.gf_data[0], key[1], key[2])
            self.gf_refresh()
        elif kind == 'step':
            self.gf_step(key[1])
        elif kind == 'sug':
            self.gf_sug_hit(key[1])
        self.ensure_tick()

    def gf_new_branch(self, flow):
        """«Rama nueva»: el nombre lo escribes tú en el chat, ya con la petición hecha."""
        self.gf_open = False
        self.open_chat(typing=True, cwd=flow.root)
        self.gf_prefill(f'Crea una rama nueva desde {flow.parent} (`git switch -c`) con el nombre v2-')

    def gf_prefill(self, text):
        if self.entry is not None:
            self.entry.get_buffer().set_text(text)

    def gf_step(self, key):
        """Un paso del flujo. «Commit» abre el chat con /commit; los demás piden un segundo clic."""
        root, flow, _steps = self.gf_data
        if key == 'commit':
            self.gf_suggest()
            return
        now = time.monotonic()
        if self.gf_busy:
            return
        if not (self.gf_confirm and self.gf_confirm[0] == key and now - self.gf_confirm[1] < GF_CONFIRM_SECS):
            self.gf_confirm = (key, now)
            return
        self.gf_confirm, self.gf_busy, self.gf_result = None, key, None

        def go():
            try:
                ok, said = gitflow.act(root, flow, key)
            except Exception as err:
                ok, said = False, str(err)
            self.gf_result = ((said.splitlines()[-1] if said else 'listo' if ok else 'falló')[:120], ok, time.monotonic())
            self.gf_busy, self.gf_loading = None, False
            self.gf_refresh()
        threading.Thread(target=go, daemon=True).start()

    def gf_suggest(self):
        """«Sugerir mensaje»: lo redacta `gitsuggest` en un hilo; mientras, el bloque muestra el aro."""
        root = self.gf_data[0]
        if self.gf_busy or (self.gf_sug and self.gf_sug.get('loading')):
            return
        self.gf_sug = {'loading': True}

        def go():
            try:
                found = gitsuggest.suggest(root)
                self.gf_sug = {'text': found.text, 'error': found.error, 'files': found.changes.files if found.changes else [],
                               'lines': found.changes.lines if found.changes else 0,
                               'risky': found.changes.risky if found.changes else []}
            except Exception as err:
                self.gf_sug = {'error': f'no pude redactarlo: {err}'}
        threading.Thread(target=go, daemon=True).start()

    def gf_sug_hit(self, what):
        """Los botones del mensaje: commitear con él, pedir otro, seguir en el chat o descartarlo."""
        sug, root = self.gf_sug, self.gf_data[0]
        if what == 'drop' or not sug or sug.get('loading'):
            self.gf_sug = None
        elif what == 'again':
            self.gf_sug = None
            self.gf_suggest()
        elif what == 'edit':
            subject = (sug.get('text') or '').splitlines()[0] if sug.get('text') else ''
            self.gf_open, self.gf_sug = False, None
            self.open_chat(typing=True, cwd=root)
            self.gf_prefill(f'/commit {subject}'.strip())
        elif what == 'use' and sug.get('text') and not self.gf_busy:
            text, files = sug['text'], sug['files']
            self.gf_busy, self.gf_result = 'commit', None

            def go():
                try:
                    ok, said = gitsuggest.commit(root, text, files)
                except Exception as err:
                    ok, said = False, str(err)
                self.gf_result = ((said.splitlines()[-1] if said else 'commit hecho')[:120], ok, time.monotonic())
                if ok:
                    self.gf_sug = None
                self.gf_busy, self.gf_loading = None, False
                self.gf_refresh()
            threading.Thread(target=go, daemon=True).start()
