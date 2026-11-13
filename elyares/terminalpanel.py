"""La vista Terminal: una terminal completa (VTE) enganchada a la sesión de tmux del proyecto.

El widget solo se engancha: la sesión y lo que corre en ella viven en el servidor
de tmux de `terminal.py` y sobreviven a un reload. Nada de la app escribe aquí
(no hay un método que mande texto): lo que corre lo teclea Yared. Un agente o el
chat con `bypassPermissions` obtendría, si pudiera, un shell con las claves de
`ssh` sin pasar por el candado.
"""

import os
import threading
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Vte', '3.91')

from gi.repository import Gdk, GLib, Gtk, Pango, Vte

from . import fonts, settings, terminal, theme, themes
from .windowframe import SPACE

QUICK_EXIT = 2.0          # un cliente que se va antes de esto no se relanza solo: algo falla
FONT_SIZE = 11
FONT_MIN, FONT_MAX = 7, 28
_panels = []              # todas las terminales vivas: el tamaño es de todas (Terminal, Editor y Taller)


def font_size():
    try:
        return max(FONT_MIN, min(FONT_MAX, int(settings.load().get('term_font') or FONT_SIZE)))
    except (TypeError, ValueError):
        return FONT_SIZE


def set_font_size(size):
    """Guarda el tamaño y lo aplica a todas las terminales abiertas. 0 = el de fábrica."""
    size = FONT_SIZE if not size else max(FONT_MIN, min(FONT_MAX, size))
    values = settings.load()
    values['term_font'] = size
    settings.save(values)
    for panel in _panels:
        panel.apply_font()
    return size


def _rgba(color):
    rgba = Gdk.RGBA()
    rgba.parse(color)
    return rgba


class TerminalPanel(Gtk.Box):
    """`kind=''` es la terminal de siempre; `kind='nvim'`, una sesión que corre nvim (la mitad de arriba del Taller)."""

    def __init__(self, kind=''):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE[0])
        self.kind = kind
        self.add_css_class('elyares-sources')
        self.root = None            # la carpeta cuya sesión se ve; None = aún no se ha elegido (distinto de '')
        self.name = ''
        self.started = 0.0
        self.running = False        # hay un cliente de tmux enganchado
        self.replaced = False       # el que se va es el viejo, por cambiar de proyecto: no es un cierre
        self.shown = False
        self.theme_sig = None
        self.head = Gtk.Label(xalign=0)
        self.head.set_margin_start(SPACE[1])
        self.head.set_margin_top(SPACE[1])
        self.term = Vte.Terminal()
        self.term.set_vexpand(True)
        self.term.set_hexpand(True)
        self.term.set_scrollback_lines(10000)
        self.apply_font()
        _panels.append(self)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._key)
        self.term.add_controller(keys)
        self.term.connect('child-exited', self._exited)
        self.note = Gtk.Label(xalign=0, wrap=True)
        self.note.add_css_class('dim-label')
        self.note.set_margin_start(SPACE[1])
        self.again = Gtk.Button(label='Reabrir')
        self.again.add_css_class('elyares-btn')
        self.again.set_halign(Gtk.Align.START)
        self.again.set_margin_start(SPACE[1])
        self.again.connect('clicked', lambda _b: self.open(self.root))
        bar = Gtk.Box(spacing=SPACE[0])
        self.head.set_hexpand(True)
        bar.append(self.head)
        for label, step, tip in (('A−', -1, 'Texto más chico (Ctrl+−)'), ('A+', 1, 'Texto más grande (Ctrl++)')):
            btn = Gtk.Button(label=label)
            btn.add_css_class('elyares-btn')
            btn.set_tooltip_text(tip)
            btn.connect('clicked', lambda _b, d=step: set_font_size(font_size() + d))
            bar.append(btn)
        for widget in (bar, self.note, self.again, self.term):
            self.append(widget)
        self._say('')
        self.set_visible(False)

    def apply_font(self):
        self.term.set_font(Pango.FontDescription.from_string(f'{fonts.MONO} {font_size()}'))

    def _key(self, _ctl, keyval, _code, state):
        """Ctrl+− / Ctrl++ / Ctrl+0: el tamaño del texto, solo con el foco en la terminal."""
        if not state & Gdk.ModifierType.CONTROL_MASK or state & Gdk.ModifierType.ALT_MASK:
            return False
        if keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            set_font_size(font_size() - 1)
        elif keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            set_font_size(font_size() + 1)
        elif keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            set_font_size(0)
        else:
            return False
        return True

    def set_terminal(self, root, visible):
        """Lo llama la ventana en cada vuelta de los paneles: barato si nada cambió."""
        if visible and not self.shown:
            self.term.grab_focus()          # al abrir la vista el teclado es de la terminal
        self.shown = visible
        if not visible:
            return
        sig = (themes.current, themes.is_light(), theme.terminal_stamp())
        if sig != self.theme_sig:
            self.theme_sig = sig
            self._colors()
            threading.Thread(target=terminal.reload_theme, args=(sig[2],), daemon=True).start()
        if root != self.root:
            self.open(root)

    def _colors(self):
        """Los colores de la terminal: los del tema que sigue la barra de tmux de Yared (el de la terminal o el
        de omarchy): texto, fondo, cursor, selección y los 16 ANSI. Sin ese tema, los de la app."""
        pal = theme.terminal_palette()
        fg, bg = pal.get('foreground'), pal.get('background')
        if not (fg and bg):
            surface = themes.get()
            fg, bg = surface['ink'], surface['surface'][0]
        ansi = [_rgba(pal[f'color{i}']) for i in range(16) if f'color{i}' in pal]
        self.term.set_colors(_rgba(fg), _rgba(bg), ansi if len(ansi) == 16 else None)
        if pal.get('cursor'):
            self.term.set_color_cursor(_rgba(pal['cursor']))
        if pal.get('selection_background'):
            self.term.set_color_highlight(_rgba(pal['selection_background']))
        if pal.get('selection_foreground'):
            self.term.set_color_highlight_foreground(_rgba(pal['selection_foreground']))

    def open(self, root):
        """Engancha la terminal a la sesión de esa carpeta (la crea si no existe)."""
        self.root = root
        if not root:
            self.name = ''
            self.head.set_markup('<b>Terminal</b>')
            self._say('Abre el chat de un proyecto, o una sesión de tmux en uno, y aquí se abre su '
                      + ('nvim.' if self.kind else 'terminal.'))
            self._stop()
            return
        base = GLib.markup_escape_text(os.path.basename(root.rstrip('/')) or root)
        what = 'nvim, en una sesión de tmux' if self.kind else 'sesión de tmux'
        self.head.set_markup(f'<b>{base}</b>  <span alpha="60%">{what}; sobrevive al reload</span>')
        self._say('')
        threading.Thread(target=self._prepare, args=(root,), daemon=True).start()

    def _prepare(self, root):
        name, why = terminal.ensure(root, self.kind)
        GLib.idle_add(self._attach, root, name, why)

    def _attach(self, root, name, why):
        if root != self.root:
            return GLib.SOURCE_REMOVE       # mientras tanto se eligió otro proyecto
        if why:
            self._say(f'No se pudo abrir la terminal: {why}', retry=True)
            return GLib.SOURCE_REMOVE
        self.name, self.started = name, time.monotonic()
        self.replaced = self.running
        self.running = True
        self.spawn(root, name)
        self.term.grab_focus()
        return GLib.SOURCE_REMOVE

    def spawn(self, root, name):
        env = [f'{k}={v}' for k, v in terminal.clean_env().items()] + ['COLORTERM=truecolor']
        self.term.spawn_async(Vte.PtyFlags.DEFAULT, root, terminal.attach_argv(name), env,
                              GLib.SpawnFlags.DEFAULT, None, None, -1, None, None)

    def _stop(self):
        self.term.reset(True, True)

    def _exited(self, _term, _status):
        """El cliente se fue (`exit` en la sesión, o tmux se cayó). Si duró, se relanza: la sesión
        se vuelve a crear limpia. Si se fue al instante, algo falla y se dice."""
        if self.replaced:
            self.replaced = False       # el cliente viejo, de otro proyecto
            return
        self.running = False
        if not self.shown or not self.root:
            return
        if time.monotonic() - self.started < QUICK_EXIT:
            self._say('La terminal se cerró al abrirse.', retry=True)
        else:
            self.open(self.root)

    def _say(self, text, retry=False):
        self.note.set_text(text)
        self.note.set_visible(bool(text))
        self.again.set_visible(retry)
