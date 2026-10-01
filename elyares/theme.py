"""El color de acento del tema de omarchy.

Sale de `accent` en `~/.config/omarchy/current/theme/colors.toml`. Sin omarchy,
sin ese archivo o con un valor que no sea `#rrggbb` no hay acento, y la mascota
se queda con su azul.
"""

import os
import re
import tomllib


def path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'omarchy', 'current', 'theme', 'colors.toml')


def accent():
    try:
        with open(path(), 'rb') as f:
            value = tomllib.load(f).get('accent')
    except (OSError, ValueError):
        return None
    if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        return value
    return None
