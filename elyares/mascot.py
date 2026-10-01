"""Dibujo de ElYares con cairo.

Es el mismo dibujo del prototipo web, pasado de canvas a cairo. Todo está en
unidades propias: la cara mide unos 160 de ancho y la figura completa, con la
antena, va de y=-130 a y=+118. Quien llama traslada y escala.
"""

import math

import cairo

TAU = math.pi * 2

COLORS = {
    'line': '#10131a', 'face': '#fbfdff', 'face_shade': '#d9e4f5', 'mesh': '#9db0da',
    'band': '#eef4fc', 'hair': '#15171c', 'strap': '#b9c2cf', 'metal': '#aeb7c4',
    'accent': '#4f9bff', 'red': '#ff4d5e', 'red_dim': '#8e2632', 'green': '#35d07f',
    'yellow': '#ffd23f', 'mouth': '#6e1a27', 'tongue': '#ff7d8e', 'laptop': '#cfd6e1',
}


DEFAULT_ACCENT = COLORS['accent']


def set_accent(color):
    """Color de la antena y del foco de la laptop mientras trabaja, y del punto
    de "trabajando" en la lista. None vuelve al azul de siempre."""
    COLORS['accent'] = color or DEFAULT_ACCENT


def rgba(color, alpha=1.0):
    h = COLORS.get(color, color).lstrip('#')
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, alpha


def src(cr, color, alpha=1.0):
    cr.set_source_rgba(*rgba(color, alpha))


# ── primitivas que canvas trae y cairo no ────────────────────────────────────

def quad(cr, cx, cy, x, y):
    """quadraticCurveTo: cairo solo tiene cúbicas."""
    x0, y0 = cr.get_current_point()
    cr.curve_to(x0 + 2 / 3 * (cx - x0), y0 + 2 / 3 * (cy - y0),
                x + 2 / 3 * (cx - x), y + 2 / 3 * (cy - y), x, y)


def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


def ellipse(cr, cx, cy, rx, ry, a0=0.0, a1=TAU):
    # El path se guarda en coordenadas de dispositivo, así que sobrevive al restore
    # y el trazo sale con el grosor normal, no deformado por el scale.
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    cr.new_sub_path()
    cr.arc(0, 0, 1, a0, a1)
    cr.restore()


def squircle(cr, cx, cy, rx, ry, n):
    cr.new_path()
    for i in range(73):
        a = i / 72 * TAU
        c, s = math.cos(a), math.sin(a)
        x = cx + rx * math.copysign(abs(c) ** (2 / n), c)
        y = cy + ry * math.copysign(abs(s) ** (2 / n), s)
        cr.line_to(x, y) if i else cr.move_to(x, y)
    cr.close_path()


def cap_path(cr):
    cr.new_path()
    cr.move_to(-78, 8)
    cr.curve_to(-84, -96, 84, -96, 78, 8)
    quad(cr, 0, 20, -78, 8)
    cr.close_path()


def star(cr, x, y, r):
    cr.new_path()
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r * 0.45 if i % 2 else r
        cr.line_to(x + math.cos(a) * rr, y + math.sin(a) * rr)
    cr.close_path()


def sparkle(cr, x, y, r):
    cr.new_path()
    cr.move_to(x, y - r)
    quad(cr, x, y, x + r, y)
    quad(cr, x, y, x, y + r)
    quad(cr, x, y, x - r, y)
    quad(cr, x, y, x, y - r)
    cr.close_path()


def stroke(cr, width, color='line', alpha=1.0, preserve=False):
    cr.set_line_width(width)
    src(cr, color, alpha)
    cr.stroke_preserve() if preserve else cr.stroke()


def fill(cr, color, alpha=1.0, preserve=False):
    src(cr, color, alpha)
    cr.fill_preserve() if preserve else cr.fill()


_MESH = None
MESH_RES = 2   # píxeles por unidad del mosaico


def _mesh_pattern():
    """Los rombitos de la malla como patrón repetido.

    Dibujarlos uno por uno eran ~450 paths por cuadro, la mitad del costo.
    El mosaico mide 7 x 13 unidades: un rombo en cada esquina y otro en el
    centro, que es la fila desplazada media celda.
    """
    global _MESH
    if _MESH is None:
        w, h = 7, 13
        tile = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * MESH_RES, h * MESH_RES)
        tc = cairo.Context(tile)
        tc.scale(MESH_RES, MESH_RES)
        for x, y in ((0, 0), (w, 0), (0, h), (w, h), (3.5, 6.5)):
            tc.move_to(x, y - 2)
            tc.line_to(x + 2, y)
            tc.line_to(x, y + 2)
            tc.line_to(x - 2, y)
            tc.close_path()
        tc.set_source_rgba(40 / 255, 62 / 255, 128 / 255, .55)
        tc.fill()
        pat = cairo.SurfacePattern(tile)
        pat.set_extend(cairo.EXTEND_REPEAT)
        # El filtro por defecto (GOOD) al reducir cuesta más que los 450 paths.
        pat.set_filter(cairo.FILTER_BILINEAR)
        # Mismo origen que tenía el bucle original: (-90, -96)
        pat.set_matrix(cairo.Matrix(MESH_RES, 0, 0, MESH_RES, 90 * MESH_RES, 96 * MESH_RES))
        _MESH = pat
    return _MESH


# ── la mascota ───────────────────────────────────────────────────────────────

BLUSH = {'idle': .22, 'working': .12, 'done': .5, 'annoyed': .55, 'confused': .15,
         'dizzy': .3, 'sleep': .25, 'permission': 0}


def draw(cr, state, age, t, look=(0.0, 0.0), blink=False, ink='#e8eefc', motion=1.0):
    """Dibuja a ElYares centrado en (0, 0).

    state: idle | working | permission | done | confused | annoyed | dizzy | sleep
    age:   segundos desde que entró al estado (para saltos y aplastones)
    t:     reloj en segundos (para respirar, parpadear la antena, etc.)
    look:  hacia dónde mira, cada eje en -1..1
    """
    st = state
    cr.save()
    # arc() une con una línea desde el punto actual: se arranca sin path
    cr.new_path()
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)

    # cuerpo: respiración, saltos, aplastones
    by, sx, sy, rot = 0.0, 1.0, 1.0, 0.0
    br = math.sin(t * 2.2) * 0.018 * motion
    sy += br
    sx -= br * 0.6
    if st == 'done':
        p = (age * 1.4) % 1
        h = math.sin(p * math.pi)
        by = -h * 24 * motion
        land = max(0.0, 0.22 - h) / 0.22
        sy -= land * 0.08 * motion
        sx += land * 0.08 * motion
    elif st == 'annoyed':
        k = max(0.0, 1 - age * 2.2)
        w = math.cos(age * 28)
        sy -= 0.14 * k * w
        sx += 0.12 * k * w
    elif st == 'dizzy':
        rot = math.sin(t * 5) * 0.09 * motion
    elif st == 'permission':
        rot = math.sin(t * 16) * 0.035 * motion * (1 if (t % 1.6) < 0.45 else 0)
    elif st == 'sleep':
        rot, by = 0.07, 4
    elif st == 'confused':
        rot = -0.07 + math.sin(t * 1.5) * 0.02 * motion
    cr.translate(0, by + 100)
    cr.rotate(rot)
    cr.scale(sx, sy)
    cr.translate(0, -100)

    # orejas
    for g in (-1, 1):
        ellipse(cr, g * 78, 40, 17, 20)
        fill(cr, 'face', preserve=True)
        stroke(cr, 5)
        ellipse(cr, g * 80, 40, 7, 10)
        fill(cr, 'face_shade')

    # cara
    squircle(cr, 0, 36, 80, 66, 2.7)
    grad = cairo.RadialGradient(-22, 6, 8, 0, 40, 96)
    grad.add_color_stop_rgba(0, 1, 1, 1, 1)
    grad.add_color_stop_rgba(0.68, *rgba('face'))
    grad.add_color_stop_rgba(1, *rgba('face_shade'))
    cr.set_source(grad)
    cr.fill_preserve()
    stroke(cr, 5.5)

    # patillas
    for g in (-1, 1):
        cr.new_path()
        cr.move_to(g * 76, 4)
        cr.line_to(g * 73, 24)
        cr.line_to(g * 65, 10)
        cr.line_to(g * 61, 22)
        cr.line_to(g * 55, 6)
        cr.close_path()
        fill(cr, 'hair')

    # gorra al revés, de malla
    cap_path(cr)
    fill(cr, 'mesh')
    cr.save()
    cap_path(cr)
    cr.clip()
    cg = cairo.LinearGradient(0, -80, 0, 12)
    cg.add_color_stop_rgba(0, 1, 1, 1, .38)
    cg.add_color_stop_rgba(1, 20 / 255, 40 / 255, 110 / 255, .28)
    cr.set_source(cg)
    cr.paint()
    cr.set_source(_mesh_pattern())
    cr.paint()
    cr.move_to(0, -72)
    cr.line_to(0, -30)
    stroke(cr, 3)
    cr.move_to(-40, 6)
    cr.curve_to(-42, -46, 42, -46, 40, 6)
    cr.close_path()
    fill(cr, 'hair', preserve=True)
    stroke(cr, 4)
    cr.restore()
    cap_path(cr)
    stroke(cr, 5.5)

    # copete que sale por la abertura
    cr.new_path()
    cr.move_to(-32, -16)
    quad(cr, -44, -28, -48, -40); quad(cr, -36, -37, -26, -31)
    quad(cr, -32, -48, -27, -60); quad(cr, -16, -48, -10, -39)
    quad(cr, -8, -54, -2, -62);   quad(cr, 7, -52, 8, -39)
    quad(cr, 16, -52, 25, -58);   quad(cr, 26, -44, 22, -33)
    quad(cr, 34, -38, 43, -43);   quad(cr, 38, -28, 32, -16)
    cr.close_path()
    fill(cr, 'hair', preserve=True)
    stroke(cr, 3)
    cr.move_to(-22, -34); quad(cr, -24, -46, -26, -55)
    cr.move_to(-1, -40);  quad(cr, -1, -50, -2, -57)
    cr.move_to(14, -37);  quad(cr, 18, -46, 22, -52)
    cr.set_source_rgba(1, 1, 1, .28)
    cr.set_line_width(2.2)
    cr.stroke()

    # banda inferior y correa con hoyitos
    cr.move_to(-78, 8)
    quad(cr, 0, 20, 78, 8)
    cr.line_to(76, -4)
    quad(cr, 0, 8, -76, -4)
    cr.close_path()
    fill(cr, 'band', preserve=True)
    stroke(cr, 4.5)
    rrect(cr, -40, -13, 80, 13, 5)
    fill(cr, 'strap', preserve=True)
    stroke(cr, 3.5)
    for x in (-30, -16, -6, 4, 14, 24):
        cr.arc(x, -6.5, 2.8 if x == -30 else 2.1, 0, TAU)
        fill(cr, 'line')

    # antena
    cr.move_to(0, -66)
    cr.line_to(5, -100)
    cr.line_to(36, -112)
    stroke(cr, 9, preserve=True)
    stroke(cr, 4.5, 'metal')
    ellipse(cr, 0, -68, 14, 8, math.pi, TAU)
    cr.close_path()
    fill(cr, 'metal', preserve=True)
    stroke(cr, 3.5)

    if st in ('permission', 'working'):
        col = 'red' if st == 'permission' else 'accent'
        sp = 1.6 if st == 'permission' else 0.9
        for k in range(3):
            p = (t * sp * motion + k / 3) % 1
            cr.new_path()
            cr.arc(48, -115, 17 + p * 26, -2.5, -0.45)
            stroke(cr, 4, col, (1 - p) * 0.85)

    ball, glow = 'face', 0.0
    if st == 'working':
        ball, glow = 'accent', 10 + 8 * math.sin(t * 5)
    elif st == 'permission':
        on = (t * 2.6) % 1 < 0.55
        ball, glow = ('red', 22) if on else ('red_dim', 0)
    elif st == 'done':
        ball, glow = 'green', 16
    elif st == 'annoyed':
        ball, glow = 'red', 8
    elif st in ('confused', 'dizzy'):
        ball, glow = 'yellow', 6
    elif st == 'sleep':
        ball = '#c3ccd9'
    if glow > 0:
        # canvas tiene shadowBlur; aquí el halo es un degradado radial
        halo = cairo.RadialGradient(48, -115, 8, 48, -115, 12 + glow)
        halo.add_color_stop_rgba(0, *rgba(ball, .7))
        halo.add_color_stop_rgba(1, *rgba(ball, 0))
        cr.set_source(halo)
        cr.arc(48, -115, 12 + glow, 0, TAU)
        cr.fill()
    cr.arc(48, -115, 12, 0, TAU)
    fill(cr, ball, preserve=True)
    stroke(cr, 4)
    cr.arc(44, -119, 3.5, 0, TAU)
    cr.set_source_rgba(1, 1, 1, .8)
    cr.fill()

    # ojos
    eyes = ((-39, 34), (39, 34))
    ox, oy = look[0] * 7, look[1] * 5
    if st == 'working':
        ox, oy = ox * 0.4 + 2, 5
    elif st == 'permission':
        ox, oy = 6, 1

    def pac(x, y, r, syy):
        if syy < 0.3:
            cr.move_to(x - r, y)
            cr.line_to(x + r, y)
            stroke(cr, 5)
            return
        cr.save()
        cr.translate(x, y)
        cr.scale(1, syy)
        cr.move_to(0, 0)
        cr.arc(0, 0, r, math.pi + 0.45, math.pi - 0.45)
        cr.close_path()
        fill(cr, 'line')
        cr.arc(r * 0.28, -r * 0.36, r * 0.27, 0, TAU)
        cr.set_source_rgba(1, 1, 1, 1)
        cr.fill()
        cr.restore()

    blink_sy = 0.1 if blink else 1.0
    if st == 'done':
        for x, y in eyes:
            cr.new_path()
            cr.arc(x, y + 6, 10, math.pi * 1.15, math.pi * 1.85)
            stroke(cr, 6)
    elif st == 'annoyed':
        for x, y in eyes:
            g = 1 if x < 0 else -1
            cr.move_to(x - g * 9, y - 8)
            cr.line_to(x + g * 7, y)
            cr.line_to(x - g * 9, y + 8)
            stroke(cr, 6)
    elif st == 'dizzy':
        for x, y in eyes:
            cr.new_path()
            a = 0.0
            while a < 4.2 * math.pi:
                r = 1 + a * 0.92
                aa = a + t * 7 * motion
                cr.line_to(x + math.cos(aa) * r, y + math.sin(aa) * r)
                a += 0.25
            stroke(cr, 3.4)
    elif st == 'sleep':
        for x, y in eyes:
            cr.new_path()
            cr.arc(x, y - 3, 10, 0.15 * math.pi, 0.85 * math.pi)
            stroke(cr, 5)
    elif st == 'confused':
        pac(eyes[0][0] + ox * 0.5, eyes[0][1] + oy * 0.5, 8, blink_sy)
        pac(eyes[1][0] + ox * 0.5, eyes[1][1] + oy * 0.5, 13, blink_sy)
        cr.move_to(24, 17)
        cr.line_to(52, 21)
        stroke(cr, 4.5)
    else:
        r = 13 if st == 'permission' else 11.5
        for x, y in eyes:
            pac(x + ox, y + oy, r, blink_sy)

    # gafas
    for x, y in ((-68, 12), (10, 12)):
        rrect(cr, x, y, 58, 44, 13)
        cr.set_source_rgba(200 / 255, 226 / 255, 1, .28)
        cr.fill_preserve()
        cr.save()
        cr.clip()
        cr.move_to(x + 8, y + 44)
        cr.line_to(x + 26, y)
        cr.line_to(x + 36, y)
        cr.line_to(x + 18, y + 44)
        cr.close_path()
        cr.set_source_rgba(1, 1, 1, .42)
        cr.fill()
        cr.restore()
        rrect(cr, x, y, 58, 44, 13)
        stroke(cr, 7)
    cr.move_to(-10, 26)
    quad(cr, 0, 21, 10, 26)
    stroke(cr, 6)
    cr.move_to(-68, 24); cr.line_to(-80, 22)
    cr.move_to(68, 24);  cr.line_to(80, 22)
    stroke(cr, 5)

    # cachetes
    blush = BLUSH.get(st, .2)
    if blush > 0:
        for g in (-1, 1):
            ellipse(cr, g * 56, 68, 11, 6.5)
            cr.set_source_rgba(1, 110 / 255, 145 / 255, blush)
            cr.fill()

    # boca
    if st == 'done':
        cr.move_to(-20, 66)
        quad(cr, 0, 96, 20, 66)
        cr.close_path()
        fill(cr, 'mouth', preserve=True)
        cr.save()
        cr.clip_preserve()
        path = cr.copy_path()
        cr.new_path()
        ellipse(cr, 0, 84, 11, 7)
        fill(cr, 'tongue')
        cr.restore()
        cr.new_path()
        cr.append_path(path)
        stroke(cr, 4)
    elif st == 'working':
        cr.new_path()
        cr.arc(0, 58, 12, 0.3 * math.pi, 0.7 * math.pi)
        stroke(cr, 4.5)
        cr.new_path()
        cr.arc(8, 69.5, 4.5, 0, math.pi)
        fill(cr, 'tongue', preserve=True)
        stroke(cr, 2.5)
    elif st == 'permission':
        ellipse(cr, 0, 75, 6, 7.5)
        fill(cr, 'line')
    elif st == 'annoyed':
        cr.move_to(-15, 77)
        for x, y in ((-7.5, 72), (0, 77), (7.5, 72), (15, 77)):
            cr.line_to(x, y)
        stroke(cr, 4)
    elif st == 'dizzy':
        cr.new_path()
        for x in range(-16, 17, 2):
            cr.line_to(x, 75 + math.sin(x * 0.45 + t * 6) * 3)
        stroke(cr, 4)
    elif st == 'sleep':
        ellipse(cr, 0, 76, 4 + math.sin(t * 1.2) * 0.8, 5 + math.sin(t * 1.2))
        stroke(cr, 3.5)
    elif st == 'confused':
        cr.move_to(-12, 78)
        cr.line_to(12, 72)
        stroke(cr, 4.5)
    else:
        cr.new_path()
        cr.arc(0, 56, 22, 0.28 * math.pi, 0.72 * math.pi)
        stroke(cr, 5)

    # laptop mini mientras trabaja
    if st == 'working':
        rrect(cr, -32, 86, 64, 22, 4)
        fill(cr, 'laptop', preserve=True)
        stroke(cr, 3.5)
        cr.arc(0, 97, 4, 0, TAU)
        fill(cr, 'accent')
        rrect(cr, -42, 106, 84, 8, 3)
        fill(cr, 'metal', preserve=True)
        stroke(cr, 3.5)
        b1 = -abs(math.sin(t * 13)) * 5 * motion
        b2 = -abs(math.sin(t * 13 + 1.6)) * 5 * motion
        for x, b in ((-26, b1), (26, b2)):
            cr.arc(x, 104 + b, 7.5, 0, TAU)
            fill(cr, 'face', preserve=True)
            stroke(cr, 3.5)

    # extras flotantes
    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    if st == 'sleep':
        for i in range(3):
            p = (t * 0.45 + i / 3) % 1
            cr.set_font_size(14 + i * 5)
            cr.move_to(58 + p * 26, -40 - p * 52)
            src(cr, ink, math.sin(p * math.pi))
            cr.show_text('z')
    elif st == 'confused':
        cr.set_font_size(38)
        cr.move_to(74, -52 + math.sin(t * 2.4) * 4 * motion)
        cr.text_path('?')
        fill(cr, 'yellow', preserve=True)
        stroke(cr, 3)
    elif st == 'dizzy':
        for k in range(3):
            a = t * 4 * motion + k * TAU / 3
            star(cr, math.cos(a) * 58, -82 + math.sin(a) * 13, 9)
            fill(cr, 'yellow', preserve=True)
            stroke(cr, 2.5)
    elif st == 'done':
        for x, y, ph in ((-86, -30, 0), (84, -52, 1.3), (-70, -86, 2.1), (88, 20, 3.2)):
            s = max(0.0, math.sin(t * 3 * motion + ph)) * 11 + 2
            sparkle(cr, x, y, s)
            fill(cr, 'green' if ph > 2 else 'yellow')
    elif st == 'annoyed':
        cr.save()
        cr.translate(66, -34)
        cr.rotate(0.3)
        for _ in range(4):
            cr.rotate(math.pi / 2)
            cr.move_to(4, -10)
            quad(cr, 4, -4, 10, -4)
            stroke(cr, 5, 'red')
        cr.restore()

    cr.new_path()
    cr.restore()
