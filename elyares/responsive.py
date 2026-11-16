"""El modo de una vista según su ancho: compacto, medio o amplio. Sin `gi`: solo la cuenta, para poder probarla.

Un borde con histéresis: cerca de un corte, el modo no cambia hasta pasarse por `HYST` px, así que una ventana
que se arrastra o que cambia de ancho por la barra de desplazamiento no hace parpadear la vista."""

COMPACT, MEDIUM, WIDE = 'compact', 'medium', 'wide'
EDGES = (560, 1150)         # compacto < 560 <= medio < 1150 <= amplio (lista y detalle lado a lado)
HYST = 24


def mode(width, current=None, scale=1.0):
    """El modo para `width` px. `scale`: el aumento de la vista cansada (con 150 % cabe lo de un ancho menor)."""
    wide = width / max(scale, 0.1)
    steps = (COMPACT, MEDIUM, WIDE)
    new = steps[sum(wide >= edge for edge in EDGES)]
    if current in steps and new != current:
        edge = EDGES[min(steps.index(new), steps.index(current))]
        if abs(wide - edge) < HYST:
            return current
    return new
