"""La taza del pomodoro, dibujada con Cairo.

Es la de `coffe` (`app/src/Taza.tsx`): el café baja con el reloj en foco y sube en el descanso, y
humea mientras está caliente. Va en un lienzo de 200 × 200 y `draw` la escala al tamaño que se le dé.
Sus colores no son del tema: un tema verde no puede dar café verde.
"""

import math

HUESO = (0xf3 / 255, 0xec / 255, 0xe2 / 255)
CAFE = (0x6f / 255, 0x4e / 255, 0x37 / 255)
CAFE_CLARO = (0x8a / 255, 0x62 / 255, 0x47 / 255)
ESCARCHA = (0xbc / 255, 0xd4 / 255, 0xe6 / 255)
BOCA, FONDO = 74, 158                     # el interior útil: el café se mueve entre estas dos alturas
LINE = 7
STEAM_EVERY = 2.4                         # segundos que tarda un hilo de vapor en subir
STEAM_ROWS = ((82, 52, 0.0), (100, 46, 0.7), (118, 52, 1.4))   # x, y de salida y desfase

# Lo que dice `coffe status --json` (`phase`) -> estado de la taza.
STATES = {'focus': 'vaciando', 'overlearning': 'repaso', 'break': 'llenando',
          'short_break': 'llenando', 'long_break': 'llenando', 'break-long': 'llenando'}


def state_of(status):
    """El estado de la taza para lo que da `pomodoro.describe`: vaciando, repaso, llenando, refri o vacia."""
    if not status:
        return 'vacia'
    if status['phase'] == 'idle':
        return 'refri' if status['parked'] else 'vacia'
    return STATES.get(status['phase'], 'vacia')


def level_of(status):
    """Cuánto café hay, de 0 a 1: en foco baja con el tiempo, en descanso sube y con algo en el refri queda a medias."""
    if not status:
        return 0.0
    state = state_of(status)
    progress = min(1.0, max(0.0, status['progress']))
    if state in ('vaciando', 'repaso'):
        return 1 - progress
    if state == 'llenando':
        return progress
    return .55 if state == 'refri' else 0.0


def body(cr):
    """El contorno de la taza, sin pintarlo."""
    cr.move_to(52, 70)
    cr.line_to(148, 70)
    cr.line_to(137, 150)
    cr.curve_to(136.3, 156.7, 131.4, 160, 124, 160)
    cr.line_to(76, 160)
    cr.curve_to(68.6, 160, 63.7, 156.7, 63, 150)
    cr.close_path()


def ellipse(cr, cx, cy, rx, ry):
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()


def handle(cr):
    cr.move_to(148, 88)
    cr.curve_to(165, 89.3, 174, 95, 174, 110)
    cr.curve_to(174, 125, 165, 130.7, 148, 132)


def steam(cr, now, alpha):
    """Tres hilos que suben y se desvanecen, cada uno con su desfase (a la vez parecerían un peine)."""
    cr.set_line_width(4)
    cr.set_line_cap(1)
    for x, y, delay in STEAM_ROWS:
        phase = ((now - delay) % STEAM_EVERY) / STEAM_EVERY
        fade = math.sin(math.pi * phase) ** 1.5 * .5
        rise = 6 - 20 * phase
        cr.save()
        cr.translate(x, y + rise)
        cr.move_to(0, 0)
        cr.curve_to(7, -3, 7, -7, 0, -10)
        cr.curve_to(-7, -13, -7, -17, 0, -20)
        cr.restore()
        cr.set_source_rgba(*HUESO, fade * alpha)
        cr.stroke()


def fridge(cr, alpha):
    cr.set_source_rgba(*ESCARCHA, alpha)
    cr.set_line_width(5)
    cr.set_line_join(1)
    cr.rectangle(22, 14, 156, 176)
    cr.move_to(22, 62)
    cr.line_to(178, 62)
    cr.stroke()
    cr.set_line_cap(1)
    for y0, y1 in ((32, 48), (80, 104)):
        cr.move_to(158, y0)
        cr.line_to(158, y1)
        cr.stroke()


def draw(cr, x, y, size, state, level, now, alpha=1.0):
    """La taza en (x, y), de `size` px de lado. `now`: segundos para el vapor (cualquier reloj que avance)."""
    level = min(1.0, max(0.0, level))
    top = FONDO - (FONDO - BOCA) * level
    cr.save()
    cr.translate(x, y)
    cr.scale(size / 200, size / 200)
    if state == 'refri':
        fridge(cr, alpha)
    if state in ('vaciando', 'repaso', 'llenando') and level > .04:
        steam(cr, now, alpha)
    cr.set_source_rgba(*HUESO, alpha)
    cr.set_line_width(LINE)
    cr.set_line_cap(1)
    handle(cr)
    cr.stroke()
    # El café solo se pinta dentro del cuerpo de la taza.
    cr.save()
    body(cr)
    cr.clip()
    cr.rectangle(45, top, 110, FONDO - top + 4)
    cr.set_source_rgba(*CAFE, alpha)
    cr.fill()
    if level > .02:
        ellipse(cr, 100, top, 55, 5)
        cr.set_source_rgba(*CAFE_CLARO, alpha)
        cr.fill()
    cr.restore()
    # El cuerpo va después del café: el trazo queda encima.
    cr.set_source_rgba(*HUESO, alpha)
    cr.set_line_join(1)
    body(cr)
    cr.stroke()
    ellipse(cr, 100, 70, 48, 8)
    cr.stroke()
    cr.set_source_rgba(*HUESO, .85 * alpha)
    cr.move_to(58, 172)
    cr.line_to(142, 172)
    cr.stroke()
    if state == 'refri':                     # el cristal de la puerta va delante de todo
        cr.set_source_rgba(*ESCARCHA, .16 * alpha)
        cr.rectangle(22, 14, 156, 176)
        cr.fill()
    cr.restore()
