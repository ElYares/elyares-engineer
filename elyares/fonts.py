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

TIRED_SCALE = 1.25
# Los colores apagados de los widgets, más claros, para que se lean con la vista cansada.
TIRED_MUTED = '#c9d2ea'

current = SYSTEM
tired = False


def valid(key):
    return key if key in _BY_KEY else SYSTEM


def use(key):
    global current
    current = valid(key)
    return current


def use_tired(on):
    global tired
    tired = bool(on)
    return tired


def scaled(size):
    """El tamaño en puntos, agrandado si hay vista cansada ('9' -> '11.2')."""
    if not tired:
        return size
    return f'{float(size) * TIRED_SCALE:.1f}'.rstrip('0').rstrip('.')


def pick(font):
    """'Sans Semi-Bold 11' -> '<familia> <estilo> 11'; el código conserva su familia."""
    size = font.rsplit(' ', 1)[-1]
    has_size = size.isdigit()
    head = font[:-len(size)].rstrip() if has_size else font
    if current != SYSTEM and (head == SYSTEM or head.startswith(SYSTEM + ' ')):
        _key, _label, family, style, _weight, _italic = _BY_KEY[current]
        head = ' '.join(part for part in (family, style) if part)
    elif tired and head == SYSTEM and has_size:
        head = SYSTEM + ' Medium'
    return ' '.join(part for part in (head, scaled(size) if has_size else '') if part)


def css():
    """La letra de los widgets; la caja del chat lleva la suya."""
    out = ''
    if current != SYSTEM:
        _key, _label, family, _style, weight, italic = _BY_KEY[current]
        out += (f'.elyares-slot label, .elyares-bar label, .elyares-bar button, .elyares-sidebox label, '
                f'.elyares-segments button, .elyares-pill, .elyares-card label, .elyares-btn, .elyares-sources label, '
                f'.elyares-chathead label {{ font-family: "{family}"; font-weight: {weight}; '
                f'font-style: {"italic" if italic else "normal"}; }}\n')
    if tired:
        pct = round(TIRED_SCALE * 100)
        out += (f'label, button, entry, dropdown {{ font-size: {pct}%; }}\n'
                f'.elyares-section {{ font-size: 14px; }}\n'
                f'.elyares-segments button, .elyares-pill, .elyares-side, .elyares-sidebox {{ color: {TIRED_MUTED}; }}\n'
                f'.elyares-segments button:checked, .elyares-pill:checked, .elyares-side row:selected {{ color: #ffffff; }}\n'
                f'.dim-label, .elyares-section {{ color: {TIRED_MUTED}; opacity: 1; }}\n'
                f'.elyares-btn:focus-visible, .elyares-segments button:focus-visible, .elyares-side row:focus-visible '
                f'{{ outline-width: 3px; }}\n')
    return out
