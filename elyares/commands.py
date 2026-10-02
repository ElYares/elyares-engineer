"""Los comandos y atajos que la isla enseña para consultar.

Con el cursor sobre la pastilla de una fuente, su burbuja trae además sus
comandos (los de devherd, los de coffe…). La pastilla "?" trae los de la
propia mascota: los atajos de teclado, lo que hace cada clic y sus órdenes de
terminal.

Los comandos salen de `commands.toml`, junto a este archivo, y de
`~/.config/elyares-mascota/commands.toml` si existe: una sección de ahí
reemplaza a la de aquí. Los atajos de teclado no se escriben en ningún lado:
se le preguntan a Hyprland, así que siempre son los que de verdad hay.

Es solo para mirar: nada de aquí corre un comando.
"""

import os
import tomllib

HELP = 'help'             # la pastilla "?": no es una fuente
BIND_PREFIX = 'Mascota:'  # con esto empieza la descripción de sus atajos en Hyprland
# Los modificadores de un atajo de Hyprland, en el orden en que se dicen.
MODS = ((64, 'SUPER'), (1, 'SHIFT'), (4, 'CTRL'), (8, 'ALT'))


def default_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'commands.toml')


def user_path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'elyares-mascota', 'commands.toml')


def _read(path):
    """Las secciones de un archivo: {sección: [(comando, qué hace)]}."""
    try:
        with open(path, 'rb') as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return {}
    return {name: [(cmd, text) for cmd, text in items.items() if isinstance(text, str)]
            for name, items in data.items() if isinstance(items, dict)}


def load():
    """Los comandos de cada sección, con lo del usuario encima de lo del repo."""
    return {**_read(default_path()), **_read(user_path())}


def combo(modmask, key):
    """Un atajo como se dice: `SUPER ALT + Y`."""
    mods = [name for bit, name in MODS if modmask & bit]
    return ' '.join(mods) + (' + ' if mods else '') + str(key)


def shortcuts(binds):
    """Los atajos de la mascota que hay en Hyprland: [(atajo, qué hace)].

    `binds` es lo que contesta `hyprctl binds -j`. Son los que llevan
    "Mascota:" en su descripción (`bindd`), en el orden del archivo.
    """
    out = []
    for b in binds if isinstance(binds, list) else []:
        text = b.get('description') if isinstance(b, dict) else None
        if isinstance(text, str) and text.startswith(BIND_PREFIX):
            text = text[len(BIND_PREFIX):].strip()
            out.append((combo(b.get('modmask') or 0, b.get('key') or ''), text[:1].upper() + text[1:]))
    return out


def reference(key, sections, binds=None):
    """Lo que se consulta en la burbuja de una pastilla, como filas:
    ('head', título) y ('cmd', comando, qué hace). [] si no hay nada."""
    if key != HELP:
        blocks = [('Comandos', sections.get(key) or [])]
    else:
        blocks = [('Teclado', shortcuts(binds)), ('Ratón', sections.get('raton') or []),
                  ('Terminal', sections.get('mascota') or [])]
    rows = []
    for title, items in blocks:
        if items:
            rows.append(('head', title))
            rows += [('cmd', cmd, text) for cmd, text in items]
    return rows
