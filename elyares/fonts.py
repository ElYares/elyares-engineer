"""La letra de la app: la del sistema o una de las que vienen en `fonts/`.

Todo el texto de la isla y de la ventana pide 'Sans <peso> <tamaño>'. Con una
letra elegida, aquí se cambia eso por su familia y su estilo, y se conserva
solo el tamaño: cada variante (Light, Bold, Italic…) es una opción aparte y
sale tal cual, sin el peso que pedía el texto. El texto de código
(JetBrainsMono Nerd Font) conserva su familia.

La «vista cansada» agranda todo el texto (`TIRED_SCALE`) y lo engrosa un punto;
vale para la letra del sistema y para las elegidas.
"""

SYSTEM = 'Sans'
# (clave, nombre en Ajustes, familia de fontconfig, estilo de Pango, peso CSS, cursiva)
CHOICES = (
    (SYSTEM, 'Predeterminada', SYSTEM, '', 0, False),
    ('Comfortaa Light', 'Comfortaa Light', 'Comfortaa', 'Light', 300, False),
    ('Comfortaa', 'Comfortaa', 'Comfortaa', 'Regular', 400, False),
    ('Comfortaa Bold', 'Comfortaa Bold', 'Comfortaa', 'Bold', 700, False),
    ('Garet', 'Garet Book', 'Garet', 'Book', 400, False),
    ('Garet Heavy', 'Garet Heavy', 'Garet', 'Heavy', 900, False),
    ('Caviar Dreams', 'Caviar Dreams', 'Caviar Dreams', 'Regular', 400, False),
    ('Caviar Dreams Italic', 'Caviar Dreams Italic', 'Caviar Dreams', 'Italic', 400, True),
    ('Caviar Dreams Bold', 'Caviar Dreams Bold', 'Caviar Dreams', 'Bold', 700, False),
    ('Caviar Dreams Bold Italic', 'Caviar Dreams Bold Italic', 'Caviar Dreams', 'Bold Italic', 700, True),
    ('Nerdy Norms', 'Nerdy Norms', 'Nerdy Norms', 'Regular', 400, False),
    ('Dunkin', 'Dunkin', 'Dunkin', 'Regular', 400, False),
    ('Dunkin Italic', 'Dunkin Italic', 'Dunkin', 'Italic', 400, True),
    ('Dunkin Bold', 'Dunkin Bold', 'Dunkin', 'Bold', 700, False),
    ('Dunkin Bold Italic', 'Dunkin Bold Italic', 'Dunkin', 'Bold Italic', 700, True),
    ('Dunkin Sans', 'Dunkin Sans', 'Dunkin Sans', 'Regular', 400, False),
    ('Dunkin Sans Italic', 'Dunkin Sans Italic', 'Dunkin Sans', 'Italic', 400, True),
    ('Dunkin Sans Bold', 'Dunkin Sans Bold', 'Dunkin Sans', 'Bold', 700, False),
    ('Dunkin Sans Bold Italic', 'Dunkin Sans Bold Italic', 'Dunkin Sans', 'Bold Italic', 700, True),
)
_BY_KEY = {c[0]: c for c in CHOICES}

# Cuánto agranda la vista cansada, en %: los tres niveles que ofrece Ajustes.
MIN_PT = 9            # el suelo de la letra dibujada con Cairo: nada se pinta más chico
TIRED_SCALES = (125, 150, 200)
TIRED_SCALE = 1.25
TIRED_GLASS = .9      # el mínimo de opacidad del vidrio con la vista cansada
LIGHT_GLASS = .9      # y con un tema claro: un fondo claro a medias se mezcla con lo de atrás y el texto oscuro se pierde
# Los colores apagados de los widgets, más claros, para que se lean con la vista cansada.
TIRED_MUTED = '#c9d2ea'
# El texto de lo elegido (pestaña, fila): la tinta del tema, no un blanco fijo.
TIRED_INK = '#ffffff'

# El estilo técnico pone toda la letra en monoespaciada, sea cual sea la elegida.
MONO = 'JetBrainsMono Nerd Font'

current = SYSTEM
tired = False
light = False         # el tema de ahora es claro (lo pone `app.load_theme`)
techno = False


def valid(key):
    return key if key in _BY_KEY else SYSTEM


def use(key):
    global current
    current = valid(key)
    return current


def use_scale(pct):
    """El nivel de la vista cansada (125, 150 o 200 %); otro valor deja 125."""
    global TIRED_SCALE
    TIRED_SCALE = (pct if pct in TIRED_SCALES else TIRED_SCALES[0]) / 100
    return round(TIRED_SCALE * 100)


def use_techno(on):
    global techno
    techno = bool(on)
    return techno


def use_tired(on):
    global tired
    tired = bool(on)
    return tired


def glass(alpha):
    """La opacidad de un fondo en vidrio: con la vista cansada o un tema claro, casi opaco, porque lo que
    haya detrás (un fondo claro tras un tema oscuro, o uno oscuro tras uno claro) se come el contraste
    del texto."""
    floor = max(TIRED_GLASS if tired else 0, LIGHT_GLASS if light else 0)
    return max(alpha, floor)


def scaled(size):
    """El tamaño en puntos, con el suelo `MIN_PT` y agrandado si hay vista cansada ('9' -> '11.2')."""
    pt = max(float(size), MIN_PT)
    if tired:
        pt *= TIRED_SCALE
    return f'{pt:.1f}'.rstrip('0').rstrip('.')


def pick(font):
    """'Sans Semi-Bold 11' -> '<familia> <estilo> 11'; el código conserva su familia."""
    size = font.rsplit(' ', 1)[-1]
    has_size = size.isdigit()
    head = font[:-len(size)].rstrip() if has_size else font
    if techno and (head == SYSTEM or head.startswith(SYSTEM + ' ')):
        head = MONO + head[len(SYSTEM):]
    elif current != SYSTEM and (head == SYSTEM or head.startswith(SYSTEM + ' ')):
        _key, _label, family, style, _weight, _italic = _BY_KEY[current]
        head = ' '.join(part for part in (family, style) if part)
    elif tired and head == SYSTEM and has_size:
        head = SYSTEM + ' Medium'
    return ' '.join(part for part in (head, scaled(size) if has_size else '') if part)


# La escala de letra de los widgets (HU-010 T2): cada token es un tamaño en em (1 em = el cuerpo) y, si
# aplica, peso y espaciado. Todo el CSS de la ventana toma de aquí en vez de poner px sueltos; la vista
# cansada agranda la raíz (ver `css()`) y por eso todo sigue al aumento.
TYPE = {
    'caption': dict(size=.82, weight=700, spacing=1),       # versalitas: cabeceras de columna, secciones
    'small': dict(size=.9),                                  # notas, imagen bajo el nombre
    'heading': dict(size=1.15, weight=600),                  # encabezado de grupo
    'title': dict(size=1.45, weight=700),                    # título de la vista
    'figure': dict(size=1.6, weight=700, tnum=True),         # cifras grandes
}


def type_rule(name):
    """Las líneas de CSS de un token: `font-size`, y `font-weight`, `letter-spacing` y `tnum` si los trae."""
    t = TYPE[name]
    out = f'font-size: {t["size"]}em;'
    if 'weight' in t:
        out += f' font-weight: {t["weight"]};'
    if 'spacing' in t:
        out += f' letter-spacing: {t["spacing"]}px;'
    if t.get('tnum'):
        out += ' font-feature-settings: "tnum";'
    return out


def type_css():
    """Una clase `.elyares-<token>` por cada token."""
    return ''.join(f'.elyares-{name} {{ {type_rule(name)} }}\n' for name in TYPE)


def view_scale():
    """Cuánto agranda la vista cansada lo que se ve (1.0 si está apagada): `responsive.mode` lo usa para que
    un ancho de 700 px con letra al 150 % cuente como uno de ~470."""
    return TIRED_SCALE if tired else 1.0


def css():
    """La letra de los widgets; la caja del chat lleva la suya."""
    out = ''
    if techno:
        out += (f'label, button, entry, dropdown, .elyares-pill {{ font-family: "{MONO}"; '
                f'font-style: normal; }}\n')
    elif current != SYSTEM:
        _key, _label, family, _style, weight, italic = _BY_KEY[current]
        out += (f'.elyares-slot label, .elyares-bar label, .elyares-bar button, .elyares-sidebox label, '
                f'.elyares-segments button, .elyares-pill, .elyares-card label, .elyares-btn, .elyares-sources label, '
                f'.elyares-chathead label {{ font-family: "{family}"; font-weight: {weight}; '
                f'font-style: {"italic" if italic else "normal"}; }}\n')
    if tired:
        pct = round(TIRED_SCALE * 100)
        # El aumento va una sola vez, en la raíz: lo demás hereda. En `label, button` se multiplicaba (150 % del
        # botón × 150 % de su etiqueta). La barra de vistas topa en 150 %: su fracción se calcula contra la raíz.
        cap = round(min(pct, 150) / pct * 100)
        out += (f'window, popover, tooltip {{ font-size: {pct}%; }}\n'
                f'.elyares-segments, .elyares-pill {{ font-size: {cap}%; }}\n'
                f'.elyares-segments button, .elyares-pill, .elyares-side, .elyares-sidebox {{ color: {TIRED_MUTED}; }}\n'
                f'.elyares-segments button:checked, .elyares-pill:checked, .elyares-side row:selected {{ color: {TIRED_INK}; }}\n'
                f'.dim-label, .elyares-muted, .elyares-section {{ color: {TIRED_MUTED}; opacity: 1; }}\n'
                f'.elyares-btn:focus-visible, .elyares-segments button:focus-visible, .elyares-side row:focus-visible, '
                f'.elyares-pill:focus-visible, .elyares-card:focus-visible, entry:focus-within, textview:focus-within, '
                f'dropdown:focus-within, switch:focus-visible, checkbutton:focus-visible, button:focus-visible '
                f'{{ outline-width: 3px; }}\n')
    return out
