"""Iconos de las imágenes de Docker (Devicon, Dashboard Icons y Simple Icons) y los de interfaz (Lucide).

Cada carpeta de `icons/` trae su licencia. `for_image` busca el icono de una imagen por su nombre; si no hay,
`None` y quien llama dibuja la inicial. Las texturas se guardan en memoria: se rasterizan una sola vez."""

import gi

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')

import os
import re

from gi.repository import Gdk, GdkPixbuf, Gio, GLib

DIR = os.path.join(os.path.dirname(__file__), 'icons')
SCALE = 2                       # se rasteriza al doble: se ve nítido en pantallas de alta densidad
# Lo que se busca dentro del nombre de la imagen → (carpeta, archivo). Lo primero que coincida manda.
BRANDS = (
    # Lo más específico primero: «phpmyadmin» contiene «php», «kibana» no es «elasticsearch».
    ('phpmyadmin', 'dashboard', 'phpmyadmin'), ('pgadmin', 'dashboard', 'pgadmin'), ('adminer', 'dashboard', 'adminer'),
    ('mongo-express', 'dashboard', 'mongo-express'), ('redis-insight', 'devicon', 'redis'),
    ('redis-commander', 'devicon', 'redis'), ('node-exporter', 'devicon', 'prometheus'),
    ('opensearch', 'dashboard', 'opensearch'), ('kibana', 'dashboard', 'kibana'), ('logstash', 'dashboard', 'logstash'),
    ('elasticsearch', 'devicon', 'elasticsearch'), ('meilisearch', 'dashboard', 'meilisearch'),
    ('postgres', 'devicon', 'postgresql'), ('mariadb', 'devicon', 'mariadb'), ('mysql', 'devicon', 'mysql'),
    ('mongo', 'devicon', 'mongodb'), ('redis', 'devicon', 'redis'), ('valkey', 'devicon', 'redis'),
    ('memcached', 'devicon', 'memcached'), ('sqlite', 'devicon', 'sqlite'), ('clickhouse', 'dashboard', 'clickhouse'),
    ('influxdb', 'dashboard', 'influxdb'), ('rabbitmq', 'devicon', 'rabbitmq'), ('kafka', 'dashboard', 'kafka'),
    ('minio', 'dashboard', 'minio'), ('mailpit', 'dashboard', 'mailpit'), ('mailhog', 'dashboard', 'mailpit'),
    ('caddy', 'dashboard', 'caddy'), ('traefik', 'dashboard', 'traefik'), ('haproxy', 'dashboard', 'haproxy'),
    ('nginx', 'devicon', 'nginx'), ('httpd', 'devicon', 'apache'), ('apache', 'devicon', 'apache'),
    ('grafana', 'devicon', 'grafana'), ('prometheus', 'devicon', 'prometheus'), ('alertmanager', 'dashboard', 'alertmanager'),
    ('loki', 'dashboard', 'loki'), ('tempo', 'dashboard', 'tempo'), ('jaeger', 'dashboard', 'jaeger'),
    ('dozzle', 'dashboard', 'dozzle'), ('portainer', 'dashboard', 'portainer'), ('keycloak', 'dashboard', 'keycloak'),
    ('vault', 'dashboard', 'vault'), ('consul', 'dashboard', 'consul'), ('etcd', 'dashboard', 'etcd'),
    ('jupyter', 'devicon', 'jupyter'), ('notebook', 'devicon', 'jupyter'), ('spark', 'devicon', 'apachespark'),
    ('selenium', 'dashboard', 'selenium'), ('metabase', 'dashboard', 'metabase'), ('n8n', 'dashboard', 'n8n'),
    ('ollama', 'dashboard', 'ollama'), ('supabase', 'dashboard', 'supabase'), ('sonarqube', 'dashboard', 'sonarqube'),
    ('jenkins', 'dashboard', 'jenkins'), ('gitea', 'dashboard', 'gitea'), ('wordpress', 'dashboard', 'wordpress'),
    ('vikunja', 'dashboard', 'vikunja'), ('nextcloud', 'dashboard', 'nextcloud'), ('laravel', 'devicon', 'laravel'), ('vite', 'dashboard', 'vite'),
    ('typescript', 'devicon', 'typescript'), ('node', 'devicon', 'nodejs'), ('python', 'devicon', 'python'),
    ('php', 'devicon', 'php'), ('rust', 'devicon', 'rust'), ('golang', 'devicon', 'go'),
    ('temurin', 'devicon', 'java'), ('openjdk', 'devicon', 'java'), ('java', 'devicon', 'java'),
    ('ubuntu', 'devicon', 'ubuntu'), ('debian', 'devicon', 'debian'), ('alpine', 'simple', 'alpine'),
    ('docker', 'devicon', 'docker'),
)
# Imágenes construidas en casa (sin nombre propio) se reconocen por la carpeta del proyecto, si nada más sirvió.
CONTEXT = (('go-starter', 'devicon', 'go'), ('java-starter', 'devicon', 'java'), ('ts-starter', 'devicon', 'typescript'),
           ('-server', 'devicon', 'laravel'), ('larapps', 'devicon', 'laravel'))
# Logos casi negros: sobre un tema oscuro llevan una pastilla clara debajo.
DARK_LOGOS = {('devicon', 'rust'), ('dashboard', 'kafka'), ('dashboard', 'vault'), ('dashboard', 'ollama')}
TINTS = {('simple', 'alpine'): '#0d597f'}     # Simple Icons no trae color: se le pone el de la marca
_cache = {}


def _name(image):
    """«docker.io/library/postgres:16-alpine» → «postgres»: sin registro ni etiqueta."""
    return re.sub(r'[:@].*$', '', (image or '').lower()).rsplit('/', 1)[-1]


def find(*names, where=''):
    """(carpeta, archivo) del primer nombre de imagen o de servicio que se reconozca, o None. `where`: la
    carpeta del proyecto, que solo se mira si el nombre no dijo nada (una imagen construida en casa)."""
    for text in (_name(n) for n in names if n):
        for key, folder, stem in BRANDS:
            if key in text:
                return folder, stem
    place = os.path.basename((where or '').rstrip('/')).lower()
    return next(((folder, stem) for key, folder, stem in CONTEXT if key in place), None)


def for_image(image, service='', where='', size=22):
    """La textura del icono de una imagen, o None si no se reconoce."""
    hit = find(image, service, where=where)
    return load(*hit, size) if hit else None


def load(folder, stem, size, color=None):
    """Un SVG de `icons/<folder>/<stem>.svg` a `size` px. `color` reemplaza `currentColor` (los de Lucide)."""
    key = (folder, stem, size, color)
    if key not in _cache:
        _cache[key] = _render(folder, stem, size, color)
    return _cache[key]


def _render(folder, stem, size, color):
    try:
        with open(os.path.join(DIR, folder, f'{stem}.svg'), encoding='utf-8') as fh:
            svg = fh.read()
    except OSError:
        return None
    tint = color or TINTS.get((folder, stem))
    if tint:
        svg = svg.replace('currentColor', tint)
        if 'stroke=' not in svg and 'fill=' not in svg.split('>', 1)[0]:
            svg = svg.replace('<svg ', f'<svg fill="{tint}" ', 1)
    px = size * SCALE
    try:
        stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(svg.encode()))
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, px, px, True, None)
    except Exception:
        return None
    return Gdk.Texture.new_for_pixbuf(pixbuf)
