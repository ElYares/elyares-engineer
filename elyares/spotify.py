"""Spotify para la isla: qué suena y los botones, por MPRIS con `playerctl`.

No usa la API web de Spotify (ni cuenta de desarrollador, ni tokens): el cliente de escritorio se
anuncia en D-Bus como `org.mpris.MediaPlayer2.spotify` y `playerctl` lo lee y lo controla. MPRIS
solo da la canción de ahora (título, artista, álbum, portada, posición), no la playlist.

`Watcher.read()` devuelve lo último que se supo y pregunta de nuevo cada EVERY segundos en un hilo,
igual que `containers.Watcher`. La portada se baja una vez a `COVER_DIR` y se guarda por URL.
"""

import hashlib
import os
import subprocess
import threading
import time
import urllib.request

PLAYER = 'spotify'
EVERY = 1.0                       # segundos entre preguntas
TIMEOUT = 3
COVER_DIR = os.path.expanduser('~/.cache/elyares-engineer/spotify')
COVER_MAX = 2_000_000             # bytes: una portada de Spotify pesa ~30 KB
SEP = '\x1f'
FORMAT = SEP.join('{{%s}}' % key for key in (
    'status', 'artist', 'title', 'album', 'mpris:artUrl', 'position', 'mpris:length'))
ACTIONS = {'play': 'play-pause', 'next': 'next', 'prev': 'previous'}


def parse(text):
    """La salida de `playerctl metadata --format FORMAT` a un dict, o None si no se entiende.

    `position` y `length` vienen en microsegundos; aquí salen en segundos."""
    parts = text.rstrip('\n').split(SEP)
    if len(parts) != 7 or not parts[0]:
        return None
    status, artist, title, album, art, pos, length = parts

    def seconds(value):
        try:
            return max(0.0, int(value) / 1_000_000)
        except ValueError:
            return 0.0

    return dict(playing=status == 'Playing', status=status, artist=artist, title=title, album=album,
                art=art, position=seconds(pos), length=seconds(length))


def _run(args, timeout=TIMEOUT):
    try:
        done = subprocess.run(['playerctl', '-p', PLAYER, *args], capture_output=True, text=True,
                              timeout=timeout, errors='replace')
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def snapshot():
    """Lo que suena ahora, o None si Spotify no está abierto (o no hay `playerctl`)."""
    out = _run(['metadata', '--format', FORMAT])
    return parse(out) if out else None


def control(action):
    """Un botón: `play`, `next` o `prev`. Devuelve si `playerctl` lo aceptó."""
    verb = ACTIONS.get(action)
    return bool(verb) and _run([verb]) is not None


def cover_path(url):
    """Dónde se guarda la portada de esa URL (el nombre sale de su hash, nunca de la URL)."""
    return os.path.join(COVER_DIR, hashlib.sha256(url.encode()).hexdigest()[:24])


def fetch_cover(url):
    """Baja la portada (solo http/https y si pesa poco) y devuelve su ruta, o None. Si ya está, no la baja."""
    if url.startswith('file://'):
        path = url[7:]
        return path if os.path.isfile(path) else None
    if not url.startswith(('https://', 'http://')):
        return None
    path = cover_path(url)
    if os.path.isfile(path):
        return path
    try:
        with urllib.request.urlopen(url, timeout=6) as resp:      # noqa: S310 (esquema ya comprobado)
            data = resp.read(COVER_MAX + 1)
        if not data or len(data) > COVER_MAX:
            return None
        os.makedirs(COVER_DIR, exist_ok=True)
        with open(path + '.part', 'wb') as fh:
            fh.write(data)
        os.replace(path + '.part', path)
    except (OSError, ValueError):
        return None
    return path


class Watcher:
    """`read()` devuelve lo último que se supo: None si Spotify no está abierto."""

    def __init__(self):
        self.data = None
        self.loaded = False             # ya contestó una vez: antes de eso la vista no dice «cerrado»
        self.at = 0.0
        self.busy = False
        self.covers = {}                # url -> ruta en disco, o None si no se pudo bajar
        self.fetching = set()

    def read(self):
        now = time.monotonic()
        if not self.busy and now - self.at >= EVERY:
            self.busy, self.at = True, now
            threading.Thread(target=self._fetch, daemon=True).start()
        return self.data

    def refresh(self):
        self.at = 0.0

    def cover(self):
        """La ruta de la portada de lo que suena, o None si aún no baja o no hay."""
        url = (self.data or {}).get('art')
        if not url:
            return None
        if url not in self.covers and url not in self.fetching:
            self.fetching.add(url)
            threading.Thread(target=self._cover, args=(url,), daemon=True).start()
        return self.covers.get(url)

    def _cover(self, url):
        try:
            self.covers[url] = fetch_cover(url)
        finally:
            self.fetching.discard(url)

    def _fetch(self):
        try:
            self.data = snapshot()
        finally:
            self.loaded = True
            self.busy = False
