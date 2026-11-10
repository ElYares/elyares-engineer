"""Dibujo de ElYares y su familia con cairo.

Es el mismo dibujo del prototipo web, pasado de canvas a cairo. Todo está en
unidades propias: la cara mide unos 160 de ancho y la figura completa, con la
antena, va de y=-130 a y=+123. Quien llama traslada y escala.

Son ocho personajes con la misma cara, las mismas gafas, la misma antena y
los mismos gestos. Cada uno pone lo suyo en capas: lo que lleva en la cabeza
(`HATS`), lo que asoma detrás de la cara (`BACK`) o delante de las gafas
(`FRONT`), lo que trae en las manos al trabajar (`PROPS`) y su color
(`ACCENTS`).

    engineer    el de siempre: gorra al revés y laptop; el color es el del tema
    architect   casco de obra, lápiz en la oreja y un plano
    auditor     cachucha de frente con </>, camisa y gafete, y un clipboard
    reviewer    visera de editor, lápiz rojo y una lupa sobre el código
    designer    boina, flequillo teñido de colores, un pincel en la oreja,
                pintura en el cachete y una paleta
    mobile      gorro de lana caído, barba y bigote de manubrio, gafas de
                pasta, y un teléfono con su café
    devops      capucha negra, chamarra con </> en el pecho, código reflejado
                en las gafas y una terminal
    researcher  sombrero de explorador con su brújula, pañoleta al cuello y
                un cuaderno donde apunta lo que encuentra
    coach       pelo peinado, diadema con micrófono, corbata y un sobre con
                el CV asomando
    analyst     pelo revuelto con un lápiz detrás de la oreja y un bloque de
                notas adhesivas con sus casillas
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

ROLES = ('engineer', 'architect', 'auditor', 'reviewer', 'designer', 'mobile', 'devops', 'researcher',
         'coach', 'analyst')
# El color de cada personaje: la antena mientras trabaja y su punto en la lista.
# Ni ámbar, ni rojo, ni verde: esos ya dicen permiso, problema y terminado. Con
# ocho ya no quedan tonos lejos de todos: el lima del devops y el naranja del
# researcher van en los dos huecos más anchos que quedaban, entre el amarillo
# y el verde y entre el rojo y el amarillo. El índigo del coach cae entre el
# azul del tema y el morado del auditor. El arena del analyst es el único tono
# apagado: el color del papel, lejos del naranja y del ámbar de «pide permiso».
ACCENTS = {'architect': '#22c7dd', 'auditor': '#9a6bff', 'reviewer': '#ff6fb5',
           'designer': '#e052f0', 'mobile': '#55b8ab', 'devops': '#a6e84a',
           'researcher': '#ff8a4c', 'coach': '#7a86ff', 'analyst': '#d9b38c'}


def set_accent(color):
    """Color de la antena y del foco de la laptop mientras trabaja, y del punto
    de "trabajando" en la lista. None vuelve al azul de siempre."""
    COLORS['accent'] = color or DEFAULT_ACCENT


def accent(role):
    """El color de un personaje, en hexadecimal: el suyo, o el de la gorra si es el engineer
    (la antena sigue el tema: `COLORS['accent']`)."""
    return ACCENTS.get(role, COLORS['mesh'])


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


SQUARE = False      # el estilo técnico: las esquinas de la interfaz, rectas (la mascota no cambia)


def box(cr, x, y, w, h, r):
    """Un rectángulo de la interfaz: redondeado, o recto con el estilo técnico."""
    if SQUARE:
        cr.rectangle(x, y, w, h)
    else:
        rrect(cr, x, y, w, h, r)


def balloon(cr, x, y, w, h, r, base, half, tx, ty):
    """Una burbuja con flecha, como un popover de macOS: un rectángulo
    redondeado con la flecha en el borde de arriba. La flecha nace en `base`
    (y `half` a cada lado), apunta a (tx, ty) y es toda curva: sale del borde
    sin esquina y acaba en una punta redonda."""
    cr.new_sub_path()
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.line_to(base - half, y)
    cr.curve_to(base - half * .45, y, tx - half * .3, ty, tx, ty)
    cr.curve_to(tx + half * .3, ty, base + half * .45, y, base + half, y)
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
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


_STATIC = {}                        # (rol, gesto, tamaño) -> superficie ya dibujada
_STATIC_MAX = 96
_OVERSCAN = 1.3                     # lo que sobresale de la caja de 253: antena, sombrero, sombra


def paint_static(cr, role, pet, x, y, size, alpha=1.0):
    """Una cara quieta, centrada en (x, y) y de `size` de alto. Se dibuja una
    sola vez a doble resolución y después solo se estampa: vectorizarla en cada
    cuadro costaba ~3 ms por cara."""
    import cairo
    px = max(2, int(size * 2))
    key = (role, pet, px)
    surf = _STATIC.get(key)
    side = int(px * _OVERSCAN) + 2
    if surf is None:
        if len(_STATIC) >= _STATIC_MAX:
            _STATIC.clear()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, side, side)
        c = cairo.Context(surf)
        c.translate(side / 2, side / 2)
        c.scale(px / 253, px / 253)
        draw(c, pet, 0, 0, motion=0, role=role)
        _STATIC[key] = surf
    cr.save()
    cr.translate(x, y + size * .015)
    cr.scale(.5, .5)
    cr.set_source_surface(surf, -side / 2, -side / 2)
    cr.paint_with_alpha(alpha)
    cr.restore()


def draw(cr, state, age, t, look=(0.0, 0.0), blink=False, ink='#e8eefc', motion=1.0,
         role='engineer'):
    """Dibuja a ElYares centrado en (0, 0).

    state: idle | working | permission | done | confused | annoyed | dizzy | sleep
    age:   segundos desde que entró al estado (para saltos y aplastones)
    t:     reloj en segundos (para respirar, parpadear la antena, etc.)
    look:  hacia dónde mira, cada eje en -1..1
    role:  qué personaje de la familia es (`ROLES`); uno desconocido es el engineer
    """
    st = state
    if role not in ROLES:
        role = 'engineer'
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

    if role in BACK:
        BACK[role](cr)

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

    HATS[role](cr)

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
        col = 'red' if st == 'permission' else accent(role)
        sp = 1.6 if st == 'permission' else 0.9
        for k in range(3):
            p = (t * sp * motion + k / 3) % 1
            cr.new_path()
            cr.arc(48, -115, 17 + p * 26, -2.5, -0.45)
            stroke(cr, 4, col, (1 - p) * 0.85)

    ball, glow = 'face', 0.0
    if st == 'working':
        ball, glow = accent(role), 10 + 8 * math.sin(t * 5)
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

    # gafas: el armazón es más delgado en quien lo lleva discreto
    frame = FRAMES.get(role, 1)
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
        stroke(cr, 7 * frame)
    cr.move_to(-10, 26)
    quad(cr, 0, 21, 10, 26)
    stroke(cr, 6 * frame)
    cr.move_to(-68, 24); cr.line_to(-80, 22)
    cr.move_to(68, 24);  cr.line_to(80, 22)
    stroke(cr, 5 * frame)

    if role in FRONT:
        FRONT[role](cr)

    # cachetes
    blush = BLUSH.get(st, .2) * PALE.get(role, 1)
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

    # lo que trae en las manos mientras trabaja
    if st == 'working':
        PROPS[role](cr, t, motion)

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


# ── engineer ─────────────────────────────────────────────────────────────────

def _hands(cr, t, motion, xs, y=104):
    """Las manos, tecleando."""
    for i, x in enumerate(xs):
        b = -abs(math.sin(t * 13 + i * 1.6)) * 5 * motion
        cr.arc(x, y + b, 7.5, 0, TAU)
        fill(cr, 'face', preserve=True)
        stroke(cr, 3.5)


def _cap(cr):
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


def _laptop(cr, t, motion):
    rrect(cr, -32, 86, 64, 22, 4)
    fill(cr, 'laptop', preserve=True)
    stroke(cr, 3.5)
    cr.arc(0, 97, 4, 0, TAU)
    fill(cr, 'accent')
    rrect(cr, -42, 106, 84, 8, 3)
    fill(cr, 'metal', preserve=True)
    stroke(cr, 3.5)
    _hands(cr, t, motion, (-26, 26))


# ── architect ────────────────────────────────────────────────────────────────

def _pencil(cr, x, y, rot, body):
    """Un lápiz detrás de la oreja, con la punta hacia arriba."""
    cr.save()
    cr.translate(x, y)
    cr.rotate(rot)
    cr.new_path()
    rrect(cr, -4.5, -22, 9, 46, 2)
    fill(cr, body, preserve=True)
    stroke(cr, 3)
    rrect(cr, -4.5, 22, 9, 8, 2)
    fill(cr, '#ff9db0', preserve=True)
    stroke(cr, 3)
    cr.move_to(-4.5, -22)
    cr.line_to(0, -37)
    cr.line_to(4.5, -22)
    cr.close_path()
    fill(cr, '#f1d6a8', preserve=True)
    stroke(cr, 3)
    cr.move_to(-2, -30.5)
    cr.line_to(0, -37)
    cr.line_to(2, -30.5)
    cr.close_path()
    fill(cr, 'line')
    cr.restore()


def _hardhat(cr):
    def dome():
        cr.new_path()
        cr.move_to(-76, 4)
        cr.curve_to(-82, -96, 82, -96, 76, 4)
        quad(cr, 0, 14, -76, 4)
        cr.close_path()

    dome()
    g = cairo.LinearGradient(0, -74, 0, 10)
    g.add_color_stop_rgba(0, *rgba('#5fe0f0'))
    g.add_color_stop_rgba(1, *rgba('#149bb3'))
    cr.set_source(g)
    cr.fill()
    cr.save()
    dome()
    cr.clip()
    # las costillas del casco y un brillo
    for g in (-1, 1):
        cr.move_to(g * 30, -76)
        quad(cr, g * 46, -36, g * 44, 10)
        stroke(cr, 3.5, alpha=.45)
    rrect(cr, -11, -80, 22, 96, 9)
    fill(cr, '#9cf0fb', preserve=True)
    stroke(cr, 4)
    cr.move_to(-56, -30)
    quad(cr, -50, -54, -32, -62)
    cr.set_source_rgba(1, 1, 1, .55)
    cr.set_line_width(5)
    cr.stroke()
    cr.restore()
    dome()
    stroke(cr, 5.5)
    # ala
    cr.new_path()
    rrect(cr, -93, -3, 186, 17, 8.5)
    fill(cr, '#27c3d9', preserve=True)
    stroke(cr, 5)
    cr.move_to(-80, 2)
    cr.line_to(80, 2)
    cr.set_source_rgba(1, 1, 1, .4)
    cr.set_line_width(3)
    cr.stroke()


def _blueprint(cr, t, motion):
    cr.new_path()
    rrect(cr, -44, 86, 88, 28, 3)
    fill(cr, '#2a6fdb', preserve=True)
    stroke(cr, 3.5)
    cr.rectangle(-30, 92, 26, 16)
    cr.move_to(-30, 100); cr.line_to(-4, 100)
    cr.move_to(-17, 92);  cr.line_to(-17, 108)
    cr.move_to(6, 94);    cr.line_to(34, 94)
    cr.move_to(6, 100);   cr.line_to(26, 100)
    cr.move_to(6, 106);   cr.line_to(34, 106)
    cr.set_source_rgba(1, 1, 1, .85)
    cr.set_line_width(1.8)
    cr.stroke()
    # los rollos de los extremos
    for g in (-1, 1):
        ellipse(cr, g * 45, 100, 5.5, 15)
        fill(cr, '#6ea2f5', preserve=True)
        stroke(cr, 3.5)
    _hands(cr, t, motion, (-56, 56))


# ── auditor ──────────────────────────────────────────────────────────────────

def _collar(cr):
    """Cuello de camisa azul claro, con el gafete colgado."""
    for g in (-1, 1):
        cr.new_path()
        cr.move_to(g * 40, 88)
        cr.line_to(0, 99)
        cr.line_to(g * 19, 121)
        cr.line_to(g * 54, 103)
        cr.close_path()
        fill(cr, '#cfe2ff', preserve=True)
        stroke(cr, 4)
    for g in (-1, 1):
        cr.move_to(g * 34, 92)
        cr.line_to(0, 114)
        stroke(cr, 10, preserve=True)
        stroke(cr, 6, ACCENTS['auditor'])
    cr.new_path()
    rrect(cr, -12, 106, 24, 19, 3.5)
    fill(cr, 'face', preserve=True)
    stroke(cr, 3.5)
    rrect(cr, -12, 106, 24, 7, 3)
    fill(cr, ACCENTS['auditor'])
    cr.arc(-5, 119, 2.6, 0, TAU)
    fill(cr, 'metal')
    cr.move_to(0, 117.5)
    cr.line_to(8, 117.5)
    cr.move_to(0, 121)
    cr.line_to(6, 121)
    stroke(cr, 1.6, 'metal')


def _front_cap(cr):
    """Cachucha negra con la visera al frente y el icono </> en la copa."""
    # sombra de barba, de la patilla al mentón
    cr.save()
    squircle(cr, 0, 36, 80, 66, 2.7)
    cr.clip()
    cr.rectangle(-90, 30, 180, 100)
    cr.clip()
    cr.rectangle(-100, -100, 200, 300)
    ellipse(cr, 0, 31, 74, 51)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    fill(cr, '#6f7d99', .32)
    cr.restore()

    def crown():
        cr.new_path()
        cr.move_to(-79, 2)
        cr.curve_to(-86, -98, 86, -98, 79, 2)
        quad(cr, 0, -16, -79, 2)
        cr.close_path()

    # No es negro puro: arriba aclara, para que la copa no se pierda sobre la isla.
    crown()
    g = cairo.LinearGradient(0, -74, 0, 4)
    g.add_color_stop_rgba(0, *rgba('#434a5c'))
    g.add_color_stop_rgba(1, *rgba('#1c1f28'))
    cr.set_source(g)
    cr.fill()
    cr.save()
    crown()
    cr.clip()
    # costuras de los paneles y un brillo
    for g in (-1, 1):
        cr.move_to(g * 4, -76)
        quad(cr, g * 44, -58, g * 50, 0)
    stroke(cr, 3, alpha=.5)
    cr.move_to(-58, -30)
    quad(cr, -50, -54, -30, -63)
    cr.set_source_rgba(1, 1, 1, .2)
    cr.set_line_width(5)
    cr.stroke()
    cr.restore()
    crown()
    stroke(cr, 5.5)
    # </>
    cr.move_to(-11, -52); cr.line_to(-21, -41); cr.line_to(-11, -30)
    cr.move_to(11, -52);  cr.line_to(21, -41);  cr.line_to(11, -30)
    cr.move_to(4.5, -55); cr.line_to(-4.5, -27)
    stroke(cr, 8.5, preserve=True)
    stroke(cr, 4.8, '#a47dff')
    # visera
    cr.new_path()
    cr.move_to(-75, 0)
    quad(cr, 0, -17, 75, 0)
    cr.curve_to(90, 9, 44, 12, 0, 12)
    cr.curve_to(-44, 12, -90, 9, -75, 0)
    cr.close_path()
    fill(cr, '#262a35', preserve=True)
    stroke(cr, 5)
    cr.move_to(-58, 2)
    quad(cr, 0, -9, 58, 2)
    stroke(cr, 3, '#a47dff', .85)


def _clipboard(cr, t, motion):
    """La lista de la auditoría: dos palomitas y un hallazgo."""
    cr.new_path()
    rrect(cr, -30, 82, 60, 40, 5)
    fill(cr, '#4a5370', preserve=True)
    stroke(cr, 3.5)
    rrect(cr, -25, 88, 50, 31, 2.5)
    fill(cr, 'face', preserve=True)
    stroke(cr, 2.2)
    rrect(cr, -10, 78, 20, 9, 3)
    fill(cr, 'metal', preserve=True)
    stroke(cr, 3)
    for i, ok in enumerate((True, True, False)):
        y = 95 + i * 8
        cr.new_path()
        if ok:
            cr.move_to(-20, y); cr.line_to(-17.5, y + 2.6); cr.line_to(-13, y - 2.8)
            stroke(cr, 2.4, 'green')
        else:
            cr.move_to(-20, y - 2.6); cr.line_to(-14, y + 2.6)
            cr.move_to(-14, y - 2.6); cr.line_to(-20, y + 2.6)
            stroke(cr, 2.4, 'red')
        cr.move_to(-8, y)
        cr.line_to(18 - i * 5, y)
        stroke(cr, 2.4, 'metal')
    _hands(cr, t, motion, (-34, 34), 106)


# ── reviewer ─────────────────────────────────────────────────────────────────

def _hair_path(cr):
    cr.new_path()
    cr.move_to(-78, 8)
    quad(cr, -90, -30, -68, -52)
    quad(cr, -76, -64, -72, -78)
    quad(cr, -56, -70, -46, -64)
    quad(cr, -46, -78, -40, -90)
    quad(cr, -28, -78, -18, -70)
    quad(cr, -22, -82, -22, -92)
    quad(cr, -6, -78, 12, -70)
    quad(cr, 22, -82, 34, -88)
    quad(cr, 36, -74, 46, -64)
    quad(cr, 58, -70, 70, -74)
    quad(cr, 66, -60, 68, -50)
    quad(cr, 90, -30, 78, 8)
    quad(cr, 0, 20, -78, 8)
    cr.close_path()


def _eyeshade(cr):
    """Pelo suelto y la banda de la visera de editor."""
    # Tampoco es negro puro: sobre la isla el pelo no se vería.
    _hair_path(cr)
    g = cairo.LinearGradient(0, -92, 0, 10)
    g.add_color_stop_rgba(0, *rgba('#4a5370'))
    g.add_color_stop_rgba(1, *rgba('#1b1e27'))
    cr.set_source(g)
    cr.fill_preserve()
    stroke(cr, 5)
    for x0, y0, cx, cy, x1, y1 in ((-52, -30, -56, -48, -60, -62), (-30, -34, -32, -56, -34, -74),
                                   (22, -34, 26, -56, 30, -72), (48, -30, 54, -46, 58, -58)):
        cr.move_to(x0, y0)
        quad(cr, cx, cy, x1, y1)
    cr.set_source_rgba(1, 1, 1, .26)
    cr.set_line_width(2.4)
    cr.stroke()
    # banda
    cr.move_to(-79, 8)
    quad(cr, 0, 20, 79, 8)
    cr.line_to(77, -8)
    quad(cr, 0, 4, -77, -8)
    cr.close_path()
    fill(cr, '#e0468f', preserve=True)
    stroke(cr, 4.5)
    cr.move_to(-70, -2)
    quad(cr, 0, 9, 70, -2)
    cr.set_source_rgba(1, 1, 1, .35)
    cr.set_line_width(2.5)
    cr.stroke()


def _visor(cr):
    """La visera translúcida, sobre las gafas."""
    cr.new_path()
    cr.move_to(-74, 10)
    quad(cr, 0, 22, 74, 10)
    cr.curve_to(90, 22, 50, 29, 0, 29)
    cr.curve_to(-50, 29, -90, 22, -74, 10)
    cr.close_path()
    fill(cr, ACCENTS['reviewer'], .34, preserve=True)
    stroke(cr, 4)


def _magnifier(cr, t, motion):
    """Una hoja de código y la lupa sobre lo que hay que corregir."""
    cr.new_path()
    rrect(cr, -44, 88, 72, 26, 3)
    fill(cr, 'face', preserve=True)
    stroke(cr, 3.5)
    for i, (x0, w) in enumerate(((-37, 26), (-31, 40), (-31, 22))):
        cr.move_to(x0, 95 + i * 6.5)
        cr.line_to(x0 + w, 95 + i * 6.5)
    stroke(cr, 2.4, 'metal')
    cr.move_to(42, 108)
    cr.line_to(57, 121)
    stroke(cr, 9, preserve=True)
    stroke(cr, 4, ACCENTS['reviewer'])
    cr.new_path()
    cr.arc(31, 97, 15, 0, TAU)
    fill(cr, '#ffd9ec', .78, preserve=True)
    stroke(cr, 5)
    cr.move_to(22, 94)
    cr.line_to(40, 94)
    cr.move_to(22, 101)
    cr.line_to(34, 101)
    stroke(cr, 3.2, 'red')
    cr.new_path()
    cr.arc(24, 90, 3, 0, TAU)
    cr.set_source_rgba(1, 1, 1, .9)
    cr.fill()
    _hands(cr, t, motion, (-54,))


# ── designer ─────────────────────────────────────────────────────────────────

# Los colores con los que pinta: el flequillo teñido y las pinturas de la paleta.
PAINTS = ('#ff5fa2', '#ff9a3d', '#ffd23f', '#3fe0a8', '#4f9bff', '#c86bff')


def _brush(cr):
    """Un pincel detrás de la oreja, con las cerdas hacia arriba y pintura fresca."""
    cr.save()
    cr.translate(89, 4)
    cr.rotate(0.24)
    cr.new_path()
    rrect(cr, -4, -12, 8, 42, 3)
    fill(cr, '#c98b5a', preserve=True)
    stroke(cr, 3)
    rrect(cr, -5, -22, 10, 11, 2)
    fill(cr, 'metal', preserve=True)
    stroke(cr, 3)
    cr.move_to(-5.5, -22)
    quad(cr, -8, -34, 0, -43)
    quad(cr, 8, -34, 5.5, -22)
    cr.close_path()
    fill(cr, PAINTS[0], preserve=True)
    stroke(cr, 3)
    cr.restore()


def _beret(cr):
    """Flequillo teñido de colores y, encima, la boina ladeada."""
    def fringe():
        cr.new_path()
        cr.move_to(-78, 8)
        cr.curve_to(-86, -34, -74, -60, -60, -64)
        cr.line_to(56, -74)
        cr.curve_to(76, -70, 88, -34, 78, 8)
        for cx, cy, x, y in ((70, -8, 60, 6), (52, -12, 42, 4), (32, -14, 22, 8), (12, -12, 2, 2),
                             (-8, -14, -18, 8), (-28, -12, -38, 4), (-48, -12, -58, 8), (-68, -6, -78, 8)):
            quad(cr, cx, cy, x, y)
        cr.close_path()

    fringe()
    g = cairo.LinearGradient(-78, 0, 78, 0)
    for i, color in enumerate(PAINTS):
        g.add_color_stop_rgba(i / (len(PAINTS) - 1), *rgba(color))
    cr.set_source(g)
    cr.fill_preserve()
    stroke(cr, 5)
    for x in (-62, -42, -22, -2, 18, 38, 58):
        cr.move_to(x, -34 - (x + 62) * .1)
        quad(cr, x + 3, -18, x - 2, -4)
    cr.set_source_rgba(1, 1, 1, .34)
    cr.set_line_width(2.4)
    cr.stroke()

    def beret():
        cr.new_path()
        cr.move_to(-90, -24)
        cr.curve_to(-110, -80, -52, -110, 0, -104)
        cr.curve_to(50, -100, 96, -92, 82, -54)
        quad(cr, 4, -26, -90, -24)
        cr.close_path()

    beret()
    g = cairo.LinearGradient(0, -104, 0, -24)
    g.add_color_stop_rgba(0, *rgba('#f590ff'))
    g.add_color_stop_rgba(1, *rgba('#a93fd0'))
    cr.set_source(g)
    cr.fill()
    cr.save()
    beret()
    cr.clip()
    cr.move_to(-74, -52)
    quad(cr, -64, -84, -30, -94)
    cr.set_source_rgba(1, 1, 1, .5)
    cr.set_line_width(6)
    cr.stroke()
    cr.restore()
    beret()
    stroke(cr, 5.5)
    # la banda y el rabito
    cr.new_path()
    cr.move_to(-90, -24)
    quad(cr, 4, -26, 82, -54)
    cr.line_to(80, -43)
    quad(cr, 4, -14, -87, -13)
    cr.close_path()
    fill(cr, '#7a2a9e', preserve=True)
    stroke(cr, 4.5)
    cr.move_to(-36, -101)
    cr.line_to(-42, -114)
    stroke(cr, 8, preserve=True)
    stroke(cr, 3.5, '#a93fd0')


def _dabs(cr):
    """Pintura en el cachete: se le fue la mano."""
    for x, y, r, color in ((-63, 59, 5.5, PAINTS[3]), (-71, 71, 3.6, PAINTS[2]), (-55, 76, 2.6, PAINTS[4])):
        cr.new_path()
        cr.arc(x, y, r, 0, TAU)
        fill(cr, color, preserve=True)
        stroke(cr, 2.2)


def _palette(cr, t, motion):
    """La paleta, con sus pinturas, y el pincel en la otra mano."""
    ellipse(cr, -8, 101, 46, 18)
    fill(cr, '#f1d6a8', preserve=True)
    stroke(cr, 3.5)
    ellipse(cr, -38, 105, 6, 4.5)
    fill(cr, '#8a6a45', preserve=True)
    stroke(cr, 2.5)
    for (x, y), color in zip(((-24, 93), (-9, 91), (6, 92), (20, 96), (24, 107)), PAINTS):
        cr.new_path()
        cr.arc(x, y, 5.2, 0, TAU)
        fill(cr, color, preserve=True)
        stroke(cr, 2)
    _hands(cr, t, motion * .3, (-52,), 108)
    # el pincel, que va y viene
    b = math.sin(t * 6) * 5 * motion
    cr.save()
    cr.translate(52 + b * .4, 104 + b)
    cr.rotate(-0.62)
    cr.new_path()
    rrect(cr, -3.5, -6, 7, 26, 3)
    fill(cr, '#c98b5a', preserve=True)
    stroke(cr, 3)
    rrect(cr, -4.5, -14, 9, 9, 2)
    fill(cr, 'metal', preserve=True)
    stroke(cr, 2.6)
    cr.move_to(-5, -14)
    quad(cr, -7, -24, 0, -31)
    quad(cr, 7, -24, 5, -14)
    cr.close_path()
    fill(cr, ACCENTS['designer'], preserve=True)
    stroke(cr, 2.6)
    cr.restore()
    cr.new_path()
    cr.arc(56 + b * .4, 110 + b, 7.5, 0, TAU)
    fill(cr, 'face', preserve=True)
    stroke(cr, 3.5)


# ── mobile ───────────────────────────────────────────────────────────────────

BEARD = ('#d08a4a', '#a8622c')    # la barba pelirroja, de arriba abajo
KNIT = ('#3f9d92', '#1f5a55')     # el gorro de lana


def _beanie(cr):
    """Barba y bigote de manubrio y, arriba, el gorro de lana caído."""
    # La barba es clara para que la boca, que va encima en oscuro, se siga viendo.
    cr.new_path()
    cr.move_to(-80, 34)
    quad(cr, -66, 58, -40, 63)
    quad(cr, -18, 67, 0, 61)
    quad(cr, 18, 67, 40, 63)
    quad(cr, 66, 58, 80, 34)
    cr.curve_to(88, 86, 46, 118, 0, 118)
    cr.curve_to(-46, 118, -88, 86, -80, 34)
    cr.close_path()
    g = cairo.LinearGradient(0, 40, 0, 118)
    g.add_color_stop_rgba(0, *rgba(BEARD[0]))
    g.add_color_stop_rgba(1, *rgba(BEARD[1]))
    cr.set_source(g)
    cr.fill_preserve()
    stroke(cr, 5)
    for x0, y0, x1, y1 in ((-58, 70, -50, 96), (-34, 84, -26, 108), (34, 84, 26, 108), (58, 70, 50, 96),
                           (0, 96, 0, 112)):
        cr.move_to(x0, y0)
        quad(cr, (x0 + x1) / 2 - 3, (y0 + y1) / 2, x1, y1)
    cr.set_source_rgba(1, 1, 1, .26)
    cr.set_line_width(2.4)
    cr.stroke()
    # el bigote, con las puntas enroscadas
    for g in (-1, 1):
        cr.move_to(g * 1, 63)
        cr.curve_to(g * 12, 55, g * 30, 57, g * 37, 66)
        quad(cr, g * 44, 74, g * 52, 60)
    stroke(cr, 10, preserve=True)
    stroke(cr, 5, '#6b3a17')

    # la punta del gorro, que cuelga hacia atrás
    cr.save()
    cr.translate(-66, -84)
    cr.rotate(-0.7)
    ellipse(cr, 0, 0, 27, 17)
    cr.restore()
    fill(cr, KNIT[1], preserve=True)
    stroke(cr, 5.5)

    def dome():
        cr.new_path()
        cr.move_to(-80, 2)
        cr.curve_to(-92, -70, -74, -110, -22, -106)
        cr.curve_to(40, -104, 92, -78, 80, 2)
        quad(cr, 0, -12, -80, 2)
        cr.close_path()

    dome()
    g = cairo.LinearGradient(0, -106, 0, 4)
    g.add_color_stop_rgba(0, *rgba(KNIT[0]))
    g.add_color_stop_rgba(1, *rgba(KNIT[1]))
    cr.set_source(g)
    cr.fill()
    cr.save()
    dome()
    cr.clip()
    # el tejido, y un brillo
    for x in range(-70, 80, 14):
        cr.move_to(x, -112)
        quad(cr, x * 1.12, -50, x * 1.04, 6)
    stroke(cr, 2.6, alpha=.32)
    cr.move_to(-64, -40)
    quad(cr, -60, -74, -36, -90)
    cr.set_source_rgba(1, 1, 1, .3)
    cr.set_line_width(5)
    cr.stroke()
    cr.restore()
    dome()
    stroke(cr, 5.5)
    # el doblez, con su etiqueta de cuero
    cr.new_path()
    cr.move_to(-82, 6)
    quad(cr, 0, 20, 82, 6)
    cr.line_to(80, -14)
    quad(cr, 0, -2, -80, -14)
    cr.close_path()
    fill(cr, '#55b8ab', preserve=True)
    stroke(cr, 5)
    for x in range(-66, 72, 12):
        cr.move_to(x, -9 + abs(x) * .03)
        cr.line_to(x, 9 - abs(x) * .04)
    stroke(cr, 2.4, alpha=.3)
    cr.new_path()
    rrect(cr, 34, -9, 22, 15, 3)
    fill(cr, ACCENTS['mobile'], preserve=True)
    stroke(cr, 3)
    cr.arc(45, -1.5, 2.2, 0, TAU)
    fill(cr, 'line')


def _phone(cr, t, motion):
    """El teléfono, con una app a medias, y el café al lado."""
    # el café para llevar, con su vapor
    for i in range(2):
        p = (t * .5 * motion + i / 2) % 1
        x = 46 + i * 9
        cr.move_to(x, 82 - p * 10)
        quad(cr, x + 4, 77 - p * 10, x, 72 - p * 10)
        stroke(cr, 2.4, 'metal', math.sin(p * math.pi) * .8)
    cr.new_path()
    cr.move_to(36, 90)
    cr.line_to(62, 90)
    cr.line_to(58, 122)
    cr.line_to(40, 122)
    cr.close_path()
    fill(cr, 'face', preserve=True)
    stroke(cr, 3.2)
    cr.move_to(38.5, 99)
    cr.line_to(59.5, 99)
    cr.line_to(58.2, 111)
    cr.line_to(39.8, 111)
    cr.close_path()
    fill(cr, ACCENTS['mobile'], preserve=True)
    stroke(cr, 2.4)
    rrect(cr, 33.5, 84, 31, 7.5, 3)
    fill(cr, '#4a5370', preserve=True)
    stroke(cr, 3)
    # el teléfono
    cr.new_path()
    rrect(cr, -22, 78, 34, 46, 7)
    fill(cr, '#262a35', preserve=True)
    stroke(cr, 3.5)
    rrect(cr, -18, 83, 26, 36, 3.5)
    fill(cr, 'face')
    rrect(cr, -18, 83, 26, 9, 3.5)
    fill(cr, ACCENTS['mobile'])
    for i, w in enumerate((17, 12)):
        cr.move_to(-14, 98 + i * 6)
        cr.line_to(-14 + w, 98 + i * 6)
    stroke(cr, 2.6, 'metal')
    rrect(cr, -14, 109, 18, 6.5, 3)
    fill(cr, KNIT[0])
    _hands(cr, t, motion, (-22, 13), 114)


# ── devops ───────────────────────────────────────────────────────────────────

HOOD = ('#3a4050', '#15171d')     # la capucha y la chamarra: negro que no se pierde sobre la isla


def _code_mark(cr, x, y, k, color, width):
    """El icono </>, centrado en (x, y) y de tamaño k."""
    cr.move_to(x - 1.1 * k, y - k); cr.line_to(x - 2.1 * k, y); cr.line_to(x - 1.1 * k, y + k)
    cr.move_to(x + 1.1 * k, y - k); cr.line_to(x + 2.1 * k, y); cr.line_to(x + 1.1 * k, y + k)
    cr.move_to(x + .45 * k, y - 1.3 * k); cr.line_to(x - .45 * k, y + 1.3 * k)
    stroke(cr, width * 1.8, preserve=True)
    stroke(cr, width, color)


def _jacket(cr):
    """La capucha por detrás de la cabeza y, abajo, la chamarra negra con sus
    cordones y el </> en el pecho."""
    cr.new_path()
    cr.move_to(-94, 96)
    cr.curve_to(-124, -10, -84, -92, -14, -122)
    quad(cr, 0, -130, 14, -122)
    cr.curve_to(84, -92, 124, -10, 94, 96)
    cr.close_path()
    g = cairo.LinearGradient(0, -118, 0, 96)
    g.add_color_stop_rgba(0, *rgba(HOOD[0]))
    g.add_color_stop_rgba(1, *rgba(HOOD[1]))
    cr.set_source(g)
    cr.fill_preserve()
    stroke(cr, 5.5)
    # los hombros
    cr.new_path()
    cr.move_to(-60, 90)
    cr.line_to(60, 90)
    cr.curve_to(92, 96, 104, 112, 106, 126)
    cr.line_to(-106, 126)
    cr.curve_to(-104, 112, -92, 96, -60, 90)
    cr.close_path()
    fill(cr, HOOD[1], preserve=True)
    stroke(cr, 5)
    cr.move_to(0, 100)
    cr.line_to(0, 126)
    stroke(cr, 3, 'metal', .7)
    for g in (-1, 1):
        cr.move_to(g * 18, 98)
        quad(cr, g * 22, 108, g * 19, 117)
        stroke(cr, 5.5, preserve=True)
        stroke(cr, 2.6, 'face')
        cr.arc(g * 19, 119, 3, 0, TAU)
        fill(cr, ACCENTS['devops'])
    _code_mark(cr, -64, 111, 5.5, ACCENTS['devops'], 2.8)


def _hood(cr):
    """El borde de la capucha, por delante: enmarca la cara y tapa la frente."""
    def rim():
        cr.new_path()
        cr.move_to(-88, 50)
        cr.curve_to(-104, -44, -62, -106, 0, -106)
        cr.curve_to(62, -106, 104, -44, 88, 50)
        cr.curve_to(84, -4, 66, -22, 0, -22)
        cr.curve_to(-66, -22, -84, -4, -88, 50)
        cr.close_path()

    rim()
    g = cairo.LinearGradient(0, -106, 0, 40)
    g.add_color_stop_rgba(0, *rgba('#454c5e'))
    g.add_color_stop_rgba(1, *rgba(HOOD[1]))
    cr.set_source(g)
    cr.fill()
    cr.save()
    rim()
    cr.clip()
    # un brillo
    cr.move_to(-66, -30)
    quad(cr, -62, -70, -36, -88)
    cr.set_source_rgba(1, 1, 1, .18)
    cr.set_line_width(5)
    cr.stroke()
    cr.restore()
    rim()
    stroke(cr, 5.5)
    # el dobladillo de la abertura, más claro: es lo que la hace capucha y no pelo
    cr.move_to(-85, 40)
    cr.curve_to(-80, 2, -62, -15, 0, -15)
    cr.curve_to(62, -15, 80, 2, 85, 40)
    stroke(cr, 9, preserve=True)
    stroke(cr, 4.5, '#7c869c')
    _code_mark(cr, 0, -58, 10, ACCENTS['devops'], 4.6)


def _glow(cr):
    """El código de la pantalla, reflejado en las gafas."""
    for x in (-68, 10):
        cr.new_path()
        rrect(cr, x, 12, 58, 44, 13)
        fill(cr, ACCENTS['devops'], .2)
        for i, w in enumerate((15, 22, 11)):
            cr.move_to(x + 9, 21 + i * 6)
            cr.line_to(x + 9 + w, 21 + i * 6)
        stroke(cr, 2.2, ACCENTS['devops'], .75)


def _terminal(cr, t, motion):
    """Una terminal negra, con el prompt esperando."""
    cr.new_path()
    rrect(cr, -36, 82, 72, 28, 4)
    fill(cr, '#10131a', preserve=True)
    stroke(cr, 3.5)
    rrect(cr, -36, 82, 72, 28, 4)
    stroke(cr, 1.6, ACCENTS['devops'], .55)
    cr.move_to(-27, 91)
    cr.line_to(-21, 96)
    cr.line_to(-27, 101)
    stroke(cr, 2.8, ACCENTS['devops'])
    if (t * 2.2 * max(motion, .01)) % 1 < .6:
        cr.move_to(-15, 101)
        cr.line_to(-5, 101)
        stroke(cr, 2.8, ACCENTS['devops'])
    cr.move_to(2, 92)
    cr.line_to(26, 92)
    cr.move_to(2, 98)
    cr.line_to(18, 98)
    stroke(cr, 2.2, 'metal', .7)
    rrect(cr, -46, 108, 92, 8, 3)
    fill(cr, '#2a2f3a', preserve=True)
    stroke(cr, 3.5)
    _hands(cr, t, motion, (-28, 28))


# ── researcher ───────────────────────────────────────────────────────────────

KHAKI = ('#e6cf9c', '#b8935a')    # el sombrero de explorador, de arriba abajo


def _neckerchief(cr):
    """La pañoleta de explorador, con su nudo."""
    for g in (-1, 1):
        cr.new_path()
        cr.move_to(g * 46, 86)
        cr.line_to(0, 100)
        cr.line_to(g * 16, 126)
        cr.line_to(g * 60, 104)
        cr.close_path()
        fill(cr, ACCENTS['researcher'], preserve=True)
        stroke(cr, 4)
        for x, y in ((g * 34, 98), (g * 26, 110), (g * 44, 106)):
            cr.arc(x, y, 2.2, 0, TAU)
            fill(cr, 'face', .9)
    cr.new_path()
    rrect(cr, -9, 96, 18, 14, 5)
    fill(cr, KHAKI[1], preserve=True)
    stroke(cr, 3.5)


def _explorer_hat(cr):
    """Sombrero de explorador: copa con su hendidura, cinta y ala ancha."""
    def crown():
        cr.new_path()
        cr.move_to(-62, -8)
        cr.curve_to(-70, -64, -48, -96, -18, -94)
        quad(cr, 0, -84, 18, -94)
        cr.curve_to(48, -96, 70, -64, 62, -8)
        quad(cr, 0, 4, -62, -8)
        cr.close_path()

    crown()
    g = cairo.LinearGradient(0, -96, 0, 0)
    g.add_color_stop_rgba(0, *rgba(KHAKI[0]))
    g.add_color_stop_rgba(1, *rgba(KHAKI[1]))
    cr.set_source(g)
    cr.fill()
    cr.save()
    crown()
    cr.clip()
    cr.move_to(0, -86)
    quad(cr, -4, -60, 0, -34)
    stroke(cr, 3, alpha=.3)
    cr.move_to(-48, -34)
    quad(cr, -46, -64, -28, -80)
    cr.set_source_rgba(1, 1, 1, .45)
    cr.set_line_width(5)
    cr.stroke()
    cr.restore()
    crown()
    stroke(cr, 5.5)
    # la cinta
    cr.new_path()
    cr.move_to(-63, -12)
    quad(cr, 0, 0, 63, -12)
    cr.line_to(64, -28)
    quad(cr, 0, -16, -64, -28)
    cr.close_path()
    fill(cr, ACCENTS['researcher'], preserve=True)
    stroke(cr, 4.5)
    # la brújula, prendida en la cinta
    cr.new_path()
    cr.arc(-34, -17, 10, 0, TAU)
    fill(cr, 'face', preserve=True)
    stroke(cr, 3.5)
    cr.move_to(-34, -24)
    cr.line_to(-31, -17)
    cr.line_to(-37, -17)
    cr.close_path()
    fill(cr, 'red')
    cr.move_to(-34, -10)
    cr.line_to(-31, -17)
    cr.line_to(-37, -17)
    cr.close_path()
    fill(cr, 'metal')
    # el ala
    cr.new_path()
    cr.move_to(-104, -2)
    cr.curve_to(-72, -18, 72, -18, 104, -2)
    cr.curve_to(110, 12, 60, 16, 0, 16)
    cr.curve_to(-60, 16, -110, 12, -104, -2)
    cr.close_path()
    g = cairo.LinearGradient(0, -14, 0, 16)
    g.add_color_stop_rgba(0, *rgba(KHAKI[0]))
    g.add_color_stop_rgba(1, *rgba(KHAKI[1]))
    cr.set_source(g)
    cr.fill_preserve()
    stroke(cr, 5)
    cr.move_to(-84, 2)
    quad(cr, 0, -9, 84, 2)
    cr.set_source_rgba(1, 1, 1, .4)
    cr.set_line_width(3)
    cr.stroke()


def _notebook(cr, t, motion):
    """El cuaderno abierto, con lo que va encontrando, y el lápiz que apunta."""
    for g in (-1, 1):
        cr.new_path()
        cr.move_to(0, 88)
        quad(cr, g * 22, 82, g * 44, 88)
        cr.line_to(g * 44, 116)
        quad(cr, g * 22, 110, 0, 116)
        cr.close_path()
        fill(cr, 'face', preserve=True)
        stroke(cr, 3.5)
    cr.move_to(0, 88)
    cr.line_to(0, 116)
    stroke(cr, 3)
    for i in range(3):
        cr.move_to(-37, 94 + i * 6)
        quad(cr, -22, 90 + i * 6, -7, 94 + i * 6)
    stroke(cr, 2.2, 'metal')
    cr.move_to(8, 94)
    quad(cr, 20, 91, 30, 93)
    stroke(cr, 2.2, 'metal')
    # el marcador, y una estrella en lo que importa
    cr.move_to(-30, 84)
    cr.line_to(-30, 98)
    cr.line_to(-26.5, 94.5)
    cr.line_to(-23, 98)
    cr.line_to(-23, 84)
    cr.close_path()
    fill(cr, ACCENTS['researcher'], preserve=True)
    stroke(cr, 2)
    star(cr, 14, 104, 5.5)
    fill(cr, ACCENTS['researcher'], preserve=True)
    stroke(cr, 1.8)
    _hands(cr, t, motion * .3, (-52,), 106)
    # el lápiz, apuntando
    b = math.sin(t * 9) * 3 * motion
    cr.save()
    cr.translate(40 + b, 100 - abs(b) * .6)
    cr.rotate(0.62)
    cr.new_path()
    rrect(cr, -3.5, -22, 7, 26, 2)
    fill(cr, 'yellow', preserve=True)
    stroke(cr, 2.6)
    cr.move_to(-3.5, 4)
    cr.line_to(0, 13)
    cr.line_to(3.5, 4)
    cr.close_path()
    fill(cr, '#f1d6a8', preserve=True)
    stroke(cr, 2.6)
    cr.restore()
    cr.new_path()
    cr.arc(54 + b, 98 - abs(b) * .6, 7.5, 0, TAU)
    fill(cr, 'face', preserve=True)
    stroke(cr, 3.5)


# ── coach ────────────────────────────────────────────────────────────────────

def _tie(cr):
    """Cuello de camisa blanco y corbata del color del coach."""
    for g in (-1, 1):
        cr.new_path()
        cr.move_to(g * 40, 88)
        cr.line_to(0, 99)
        cr.line_to(g * 19, 121)
        cr.line_to(g * 54, 103)
        cr.close_path()
        fill(cr, '#f4f7ff', preserve=True)
        stroke(cr, 4)
    cr.new_path()
    cr.move_to(-7, 104)
    cr.line_to(7, 104)
    cr.line_to(11, 124)
    cr.line_to(0, 133)
    cr.line_to(-11, 124)
    cr.close_path()
    fill(cr, ACCENTS['coach'], preserve=True)
    stroke(cr, 3.5)
    cr.new_path()
    rrect(cr, -8, 94, 16, 13, 4)
    fill(cr, ACCENTS['coach'], preserve=True)
    stroke(cr, 3.5)


def _headset(cr):
    """Pelo peinado, diadema con sus dos auriculares y el micrófono al frente."""
    cr.new_path()
    cr.move_to(-76, 6)
    cr.curve_to(-90, -60, 90, -60, 76, 6)
    quad(cr, 0, -12, -76, 6)
    cr.close_path()
    g = cairo.LinearGradient(0, -50, 0, 6)
    g.add_color_stop_rgba(0, *rgba('#4a5370'))
    g.add_color_stop_rgba(1, *rgba('#1b1e27'))
    cr.set_source(g)
    cr.fill_preserve()
    stroke(cr, 5)
    cr.move_to(-30, -30)
    quad(cr, 0, -40, 40, -26)
    cr.set_source_rgba(1, 1, 1, .26)
    cr.set_line_width(2.4)
    cr.stroke()
    # la diadema
    cr.new_path()
    cr.move_to(-82, 30)
    cr.curve_to(-96, -84, 96, -84, 82, 30)
    stroke(cr, 12, preserve=True)
    stroke(cr, 7, ACCENTS['coach'])
    # los auriculares
    for g in (-1, 1):
        cr.new_path()
        rrect(cr, g * 86 - 10, 20, 20, 36, 9)
        fill(cr, ACCENTS['coach'], preserve=True)
        stroke(cr, 4)
        ellipse(cr, g * 86, 38, 4, 8)
        fill(cr, 'face', .85)
    # el micrófono
    cr.new_path()
    cr.move_to(-88, 54)
    cr.curve_to(-84, 84, -70, 92, -50, 84)
    stroke(cr, 5, preserve=True)
    stroke(cr, 2.4, 'metal')
    ellipse(cr, -48, 84, 7, 5)
    fill(cr, '#4a5370', preserve=True)
    stroke(cr, 3)


def _envelope(cr, t, motion):
    """El sobre de la postulación, con el CV asomando y su sello."""
    b = math.sin(t * 6) * 2.2 * motion
    cr.new_path()
    rrect(cr, -23, 76 + b, 46, 34, 3)
    fill(cr, 'face', preserve=True)
    stroke(cr, 3)
    for i in range(3):
        cr.move_to(-16, 84 + b + i * 6)
        cr.line_to(16 - i * 6, 84 + b + i * 6)
    stroke(cr, 2.2, 'metal')
    cr.new_path()
    rrect(cr, -36, 90, 72, 36, 5)
    fill(cr, '#dfe6f7', preserve=True)
    stroke(cr, 3.5)
    cr.move_to(-35, 92)
    cr.line_to(0, 112)
    cr.line_to(35, 92)
    stroke(cr, 3)
    cr.new_path()
    cr.arc(0, 112, 6.5, 0, TAU)
    fill(cr, ACCENTS['coach'], preserve=True)
    stroke(cr, 2.6)
    cr.move_to(-3, 112)
    cr.line_to(-0.8, 114.4)
    cr.line_to(3.4, 109.6)
    stroke(cr, 2, 'face')
    _hands(cr, t, motion * .6, (-44, 44), 116)


# ── analyst ──────────────────────────────────────────────────────────────────

def _messy_hair(cr):
    """Pelo corto y despeinado, con un brillo en el flequillo."""
    cr.new_path()
    cr.move_to(-78, 8)
    cr.curve_to(-92, -62, 92, -62, 78, 8)
    quad(cr, 0, -16, -78, 8)
    cr.close_path()
    g = cairo.LinearGradient(0, -50, 0, 8)
    g.add_color_stop_rgba(0, *rgba('#7a5a3c'))
    g.add_color_stop_rgba(1, *rgba('#3d2c1e'))
    cr.set_source(g)
    cr.fill_preserve()
    stroke(cr, 5)
    cr.move_to(-30, -28)
    quad(cr, 0, -38, 36, -24)
    cr.set_source_rgba(1, 1, 1, .2)
    cr.set_line_width(2.4)
    cr.stroke()


def _sticky_notes(cr, t, motion):
    """Un bloque de notas adhesivas: una con su casilla marcada, otra por marcar."""
    b = math.sin(t * 5) * 2 * motion
    for i, (x, tilt) in enumerate(((-30, -.1), (-4, .06), (22, -.04))):
        cr.save()
        cr.translate(x + 14, 100 + b * (1 if i == 1 else .4))
        cr.rotate(tilt)
        cr.new_path()
        rrect(cr, -17, -17, 34, 34, 3)
        fill(cr, ACCENTS['analyst'] if i != 1 else 'face', preserve=True)
        stroke(cr, 3)
        cr.rectangle(-11, -10, 7, 7)
        stroke(cr, 2, 'metal')
        if i != 2:
            cr.move_to(-10, -6)
            cr.line_to(-7.5, -3)
            cr.line_to(-2, -12)
            stroke(cr, 2.4, 'metal')
        cr.move_to(1, -6)
        cr.line_to(12, -6)
        cr.move_to(-11, 4)
        cr.line_to(12, 4)
        cr.move_to(-11, 10)
        cr.line_to(5, 10)
        stroke(cr, 2, 'metal')
        cr.restore()
    _hands(cr, t, motion * .6, (-40, 40), 116)


# ── las capas de cada personaje ──────────────────────────────────────────────

HATS = {'engineer': _cap, 'architect': _hardhat, 'auditor': _front_cap, 'reviewer': _eyeshade,
        'designer': _beret, 'mobile': _beanie, 'devops': _hood, 'researcher': _explorer_hat,
        'coach': _headset, 'analyst': _messy_hair}
PROPS = {'engineer': _laptop, 'architect': _blueprint, 'auditor': _clipboard, 'reviewer': _magnifier,
         'designer': _palette, 'mobile': _phone, 'devops': _terminal, 'researcher': _notebook, 'coach': _envelope,
         'analyst': _sticky_notes}
BACK = {'architect': lambda cr: _pencil(cr, 89, 4, 0.24, 'yellow'),
        'auditor': _collar,
        'reviewer': lambda cr: _pencil(cr, -89, 4, -0.24, 'red'),
        'designer': _brush,
        'devops': _jacket,
        'researcher': _neckerchief,
        'coach': _tie,
        'analyst': lambda cr: _pencil(cr, 89, 4, 0.24, '#d9b38c')}
FRONT = {'reviewer': _visor, 'designer': _dabs, 'devops': _glow}
# Grosor del armazón de las gafas, sobre el de siempre: discreto o de pasta.
FRAMES = {'auditor': .64, 'mobile': 1.3}
PALE = {'auditor': .3, 'mobile': .5, 'devops': .5}        # cuánto se le notan los cachetes
