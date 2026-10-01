"""Los colores del tema de omarchy.

Salen de `~/.config/omarchy/current/theme/colors.toml`: `accent` para la
mascota y el resto de la paleta para el texto (`paint.py`). Sin omarchy, sin
ese archivo o con un valor que no sea `#rrggbb` no hay color del tema, y la
mascota se queda con los suyos.
"""

import os
import re
import tomllib


def path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'omarchy', 'current', 'theme', 'colors.toml')


def palette():
    """Los colores del tema que sean `#rrggbb`: accent, foreground, color0..15."""
    try:
        with open(path(), 'rb') as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items()
            if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', v)}


def accent():
    return palette().get('accent')
