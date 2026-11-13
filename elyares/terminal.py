"""La terminal de la ventana: una sesión de tmux por proyecto, en su propio servidor.

El widget de terminal (`terminalpanel.py`) solo se engancha a una sesión; las
sesiones viven en un servidor de tmux aparte (`-L elyares`) lanzado con su propio
scope de systemd. Así `ssh`, un servidor de desarrollo o lo que se haya
levantado sobrevive a `elyares-ctl reload`: sin el scope, el servicio mata todo
su grupo al reiniciarse. El servidor es otro que el de tmux de Yared, así que no
aparece en «Sesiones» ni tropieza con su configuración de sesión.

Ese servidor arranca con su propia configuración (`server_conf`): la de Yared sin sus
plugins de persistencia. Con `continuum` el servidor de la app restauraría, al arrancar
antes que el tmux de Yared tras un reinicio, TODAS las sesiones de Yared dentro de la
app (restaura solo si es el único servidor), y su autoguardado pisaría el mismo
`last`. La app guarda y restaura lo suyo aparte, con `resurrect` y su propia carpeta.

Nada aquí escribe en la terminal: lo que se teclea ahí lo teclea Yared.
"""

import hashlib
import os
import re
import shutil
import subprocess
import uuid

SOCKET = 'elyares'
DATA_DIR = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'), 'elyares-engineer')
RESURRECT_DIR = os.path.join(DATA_DIR, 'resurrect')      # lo guardado de la app: separado del de Yared
CONF = os.path.join(DATA_DIR, 'tmux.conf')               # la configuración con la que arranca su servidor
USER_CONFS = (os.path.expanduser('~/.config/tmux/tmux.conf'), os.path.expanduser('~/.tmux.conf'))
PLUGIN_DIRS = (os.path.expanduser('~/.config/tmux/plugins/tmux-resurrect'),
               os.path.expanduser('~/.tmux/plugins/tmux-resurrect'))
SAVE_EVERY = 300                      # cada cuánto la app guarda sus sesiones, en segundos
# Lo que de la configuración de Yared no entra al servidor de la app: los plugins y su restauración
# automática (ver arriba) y la tabla de atajos que regenera su cheatsheet.
# Las líneas de su configuración que cargan la paleta del tema en tmux: se repiten al cambiar de tema.
THEME_LINES = re.compile(r'omarchy-theme\.sh|tmux-fz style')
PERSISTENCE = re.compile(r'@plugin|@continuum|@resurrect|plugins/tpm/tpm|tmux-keys sync')
# Lo del servicio que no debe llegar a la terminal ni a nvim: `PYTHONPATH` haría que todo `python` que
# se corra ahí importe primero del repo de la isla, y `LD_PRELOAD` carga la librería de la capa.
DROP_ENV = ('PYTHONPATH', 'LD_PRELOAD', 'INVOCATION_ID', 'JOURNAL_STREAM', 'MEMORY_PRESSURE_WATCH',
            'MEMORY_PRESSURE_WRITE', 'NOTIFY_SOCKET', 'WATCHDOG_USEC', 'WATCHDOG_PID')
NVIM = 'nvim'                         # el tipo de sesión que corre nvim en vez de un shell
SIZE = ('-x', '200', '-y', '50')      # tamaño con el que nace la sesión; el cliente la ajusta al engancharse


def session_name(root, kind=''):
    """Un nombre de sesión por carpeta: el de la carpeta y un trozo de su ruta, para que dos
    proyectos que se llamen igual no compartan sesión. tmux no admite «:» ni «.». La de nvim
    lleva su sufijo: es otra sesión de la misma carpeta."""
    root = os.path.realpath(root)
    base = re.sub(r'[^A-Za-z0-9_-]+', '-', os.path.basename(root.rstrip('/')) or 'raiz').strip('-') or 'raiz'
    return f'{base}-{hashlib.sha1(root.encode()).hexdigest()[:6]}' + (f'-{kind}' if kind == NVIM else '')


def clean_env(base=None):
    """El entorno del servicio sin lo que no debe heredar la terminal (`DROP_ENV`)."""
    return {k: v for k, v in (os.environ if base is None else base).items() if k not in DROP_ENV}


def nvim_socket(name):
    """Donde escucha el nvim de esa sesión, para pedirle que abra un archivo."""
    return os.path.join(os.environ.get('XDG_RUNTIME_DIR') or '/tmp', f'elyares-{name}.sock')


def _tmux(*args, **kw):
    return subprocess.run(['tmux', '-L', SOCKET, *args], capture_output=True, text=True, timeout=10, **kw)


def without_plugins(text):
    """La configuración de tmux de Yared sin las líneas de plugins y persistencia (`PERSISTENCE`)."""
    return ''.join(line for line in text.splitlines(keepends=True) if not PERSISTENCE.search(line))


def _plugin():
    """La carpeta del plugin `tmux-resurrect`, o '' si no está instalado."""
    return next((d for d in PLUGIN_DIRS if os.path.exists(os.path.join(d, 'resurrect.tmux'))), '')


def server_conf():
    """Escribe (si cambió) la configuración del servidor de la app y devuelve su ruta, o '' si no se pudo."""
    base = ''
    for path in USER_CONFS:
        try:
            with open(path, encoding='utf-8') as fh:
                base = without_plugins(fh.read())
            break
        except OSError:
            continue
    plugin = _plugin()
    text = ('# Lo genera elyares-engineer cada vez que arranca su servidor de tmux: no lo edites.\n'
            '# Es tu configuración sin plugins ni restauración automática, más resurrect con carpeta propia.\n'
            + base + '\n')
    if plugin:
        text += (f"set -g @resurrect-dir '{RESURRECT_DIR}'\n"
                 "set -g @resurrect-capture-pane-contents 'on'\n"
                 f"run-shell '{os.path.join(plugin, 'resurrect.tmux')}'\n")
    try:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        try:
            with open(CONF, encoding='utf-8') as fh:
                same = fh.read() == text
        except OSError:
            same = False
        if not same:
            with open(CONF, 'w', encoding='utf-8') as fh:
                fh.write(text)
    except OSError:
        return ''
    return CONF


_themed = [None]        # con qué versión del tema se cargó por última vez la paleta de tmux


def reload_theme(stamp):
    """Vuelve a cargar en el servidor de la app la paleta del tema (las líneas `THEME_LINES` de la
    configuración de Yared) cuando `stamp` cambió: la barra de tmux solo la lee al arrancar."""
    if stamp == _themed[0]:
        return False
    first = _themed[0] is None
    _themed[0] = stamp
    if first or not server_running():
        return False                # la primera vez el servidor acaba de arrancar con el tema de ahora
    for path in USER_CONFS:
        try:
            with open(path, encoding='utf-8') as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for line in lines:
            m = THEME_LINES.search(line) and re.match(r'\s*run-shell(?:\s+-b)?\s+["\'](.+)["\']\s*$', line)
            if m:
                try:
                    _tmux('run-shell', m.group(1))
                except (OSError, subprocess.SubprocessError):
                    pass
        break
    return True


def server_running():
    try:
        return _tmux('list-sessions').returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _script(name):
    plugin = _plugin()
    path = os.path.join(plugin, 'scripts', name) if plugin else ''
    return path if path and os.path.exists(path) else ''


def save():
    """Guarda las sesiones de la app (resurrect, en su carpeta). True si guardó; sin servidor no hace nada."""
    script = _script('save.sh')
    if not script or not server_running():
        return False
    try:
        return _tmux('run-shell', script).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def restore():
    """Restaura lo guardado en un servidor recién arrancado. Va antes de que nada se enganche:
    al terminar, resurrect cambia a los clientes a la sesión que tenían guardada."""
    script = _script('restore.sh')
    if not script or not os.path.exists(os.path.join(RESURRECT_DIR, 'last')):
        return False
    try:
        return subprocess.run(['tmux', '-L', SOCKET, 'run-shell', script], capture_output=True, text=True,
                              timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _pin_server():
    """Un servidor que ya corría con la configuración completa (de antes de este cambio) trae `continuum`:
    se le apaga el autoguardado y la restauración, que pisarían lo de Yared."""
    for option, value in (('@continuum-save-interval', '0'), ('@continuum-restore', 'off')):
        try:
            _tmux('set-option', '-g', option, value)
        except (OSError, subprocess.SubprocessError):
            pass


def has(name):
    try:
        return _tmux('has-session', '-t', f'={name}').returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure(root, kind=''):
    """Deja viva la sesión de esa carpeta (con `kind='nvim'`, la que corre nvim).
    Devuelve (nombre, '') o (nombre, por qué no se pudo)."""
    name = session_name(root, kind)
    if not shutil.which('tmux'):
        return name, 'No está instalado tmux'
    if kind == NVIM and not shutil.which('nvim'):
        return name, 'No está instalado nvim'
    if not os.path.isdir(root):
        return name, 'La carpeta del proyecto ya no existe'
    fresh = not server_running()
    if not fresh:
        _pin_server()
    sock = nvim_socket(name)
    if kind == NVIM and has(name) and not os.path.exists(sock):
        # La sesión de nvim existe pero nvim no escucha (se restauró sin `--listen`, o murió): se rehace.
        try:
            _tmux('kill-session', '-t', f'={name}')
        except (OSError, subprocess.SubprocessError):
            pass
        fresh = fresh or not server_running()   # si era la última sesión, el servidor murió: el que sigue es nuevo
    if has(name):
        return name, ''
    # La carpeta va por `cwd=`, no por `-c`: tmux pasa lo de `-c` por sus formatos y un `#(comando)` en el
    # nombre de la carpeta se ejecutaría (probado con tmux 3.8).
    conf = server_conf() if fresh else ''
    cmd = ['tmux', '-L', SOCKET, *(['-f', conf] if conf else []), 'new-session', '-d', '-s', name, *SIZE]
    if kind == NVIM:
        try:
            os.remove(sock)             # un socket viejo (la sesión murió) impide que el nuevo nvim escuche
        except OSError:
            pass
        cmd += ['nvim', '--listen', sock]
    if shutil.which('systemd-run'):
        # Con scope propio: el servidor no cuelga del servicio y sobrevive al reload.
        cmd = ['systemd-run', '--user', '--scope', '--quiet', f'--unit=elyares-tmux-{os.getpid()}-{uuid.uuid4().hex[:8]}', *cmd]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=root, env=clean_env())
    except (OSError, subprocess.SubprocessError) as err:
        return name, str(err)
    if out.returncode != 0:
        return name, (out.stderr or out.stdout).strip() or 'tmux no pudo crear la sesión'
    if fresh:
        restore()       # lo restaurado trae sus sesiones de nvim sin `--listen`: se rehacen al abrirlas (arriba)
    return name, ''


def attach_argv(name):
    """El comando que engancha un cliente a la sesión (lo corre el widget de terminal)."""
    return ['tmux', '-L', SOCKET, 'attach-session', '-t', f'={name}']


def open_in_nvim(root, path):
    """Pide al nvim de esa carpeta que abra un archivo del proyecto. Lo manda el clic de Yared
    en la lista; no escribe en la terminal: habla con nvim por su socket. (ok, por qué no)."""
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        return False, 'Nombre de archivo no válido'       # un salto de línea parte el nombre en nvim
    full = os.path.realpath(os.path.join(root, path))
    if not full.startswith(os.path.realpath(root) + os.sep):
        return False, 'Fuera del proyecto'
    sock = nvim_socket(session_name(root, NVIM))
    if not os.path.exists(sock):
        return False, 'nvim aún no está listo'
    try:
        out = subprocess.run(['nvim', '--server', sock, '--remote', full], capture_output=True, text=True,
                             timeout=5)
    except (OSError, subprocess.SubprocessError) as err:
        return False, str(err)
    return out.returncode == 0, out.stderr.strip()
