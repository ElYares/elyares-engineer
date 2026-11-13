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


def palette(file=None):
    """Los colores del tema que sean `#rrggbb`: accent, foreground, color0..15."""
    try:
        with open(file or path(), 'rb') as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items()
            if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', v)}


def terminal_path():
    """El `colors.toml` que sigue la terminal, con la misma regla que la barra de tmux de Yared
    (`omarchy-theme.sh`): el tema solo de terminal (`~/.config/terminal-theme`) si existe y, si no, el de omarchy."""
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    own = os.path.join(base, 'terminal-theme', 'colors.toml')
    return own if os.path.isfile(own) else path()


def terminal_palette():
    """Lo mismo que `palette()`, pero del archivo que sigue la terminal (`terminal_path`)."""
    return palette(terminal_path())


def terminal_stamp():
    """Qué archivo y de cuándo es: cambia cuando se cambia de tema, para recargar la terminal."""
    file = terminal_path()
    try:
        return (os.path.realpath(file), os.stat(file).st_mtime_ns)
    except OSError:
        return (file, 0)


def accent():
    return palette().get('accent')
