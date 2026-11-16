#!/usr/bin/python3
"""El candado de los agentes de la familia: un hook PreToolUse de Claude Code.

Uso, con el payload del hook por stdin (install.sh lo copia como `elyares-guard`):
  elyares-guard solo-lectura   el Bash de un agente que solo lee: frena el
                               comando que escribe, instala, borra, cambia git,
                               entra a un servidor o toca lo desplegado
  elyares-guard entrega        el Bash del devops: como solo-lectura, y además lo
                               de entregar un cambio: preparar archivos, hacer
                               el commit, subir la rama y abrir o editar su PR,
                               y entrar a un servidor por `ssh` a leer (el
                               comando remoto pasa por las mismas reglas)
  elyares-guard solo-docs      el Edit y el Write de un agente que solo documenta
                               (el architect, el researcher, el coach, el analyst): nada que no sea
                               documentación
  elyares-guard config         el Edit y el Write de cualquier sesión: pregunta
                               antes de tocar la configuración de un linter, un
                               analizador, un formateador o el CI que ya existe

Para frenar sale con 2 y el motivo por stderr, que es lo que lee el agente.
Para preguntar imprime la decisión `ask` y sale con 0.

Frena lo evidente, no es un sandbox: un intérprete en línea (`python -c`), un
script propio o una herramienta que escribe sin decirlo pasan sin que los vea.
Lo que no entiende lo deja pasar, salvo un comando que no se puede partir en
palabras: ese se revisa con una búsqueda más tosca. Escribir en /tmp y en la
carpeta de trabajo de la sesión está permitido: ahí van los informes.
"""
import json
import os
import re
import shlex
import sys

SCRATCH = ('/tmp/', '/var/tmp/', '/dev/')
DEPTH = 5                 # cuántos `sh -c`, `xargs` o `$(…)` anidados se siguen

OPERATOR = re.compile(r'&>>|>>|>&|&>|>\||<<<|<<|<&|&&|\|\||\|&|;;|[;|&()<>]')
SEPARATORS = {';', ';;', '&&', '||', '|', '|&', '&', '(', ')'}
HEREDOC = re.compile(r'<<-?\s*([\'"]?)(\w+)\1([^\n]*)\n.*?\n\s*\2[ \t]*$', re.S | re.M)
SUBSHELL = re.compile(r'\$\(([^()]*)\)|`([^`]*)`')
ASSIGN = re.compile(r'^\w+=')

# Envoltorios: lo que corre es lo que viene después.
WRAPPERS = {'env', 'time', 'nice', 'nohup', 'command', 'exec', 'stdbuf', 'ionice', 'timeout'}
SHELLS = {'sh', 'bash', 'zsh', 'dash'}
ROOT = {'sudo', 'pkexec', 'doas', 'su'}
WRITERS = {'rm', 'rmdir', 'unlink', 'mv', 'ln', 'chmod', 'chown', 'chgrp', 'truncate', 'dd',
           'shred', 'patch'}
TO_DEST = {'cp', 'install', 'mkdir', 'touch', 'tee', 'rsync'}     # pasan si el destino es /tmp
STOPPERS = {'kill', 'pkill', 'killall', 'reboot', 'shutdown', 'poweroff'}
SYSTEM_PACKAGES = {'pacman', 'yay', 'paru', 'apt', 'apt-get', 'dnf', 'brew'}
SQL_CLIENTS = {'psql', 'mysql', 'mariadb', 'sqlite3'}
SQL_WRITE = re.compile(r'\b(insert|update|delete|drop|alter|truncate|create|replace|grant)\b', re.I)
WRITE_FLAGS = {'--fix', '--autofix', '--write'}
SEARCHERS = {'grep', 'egrep', 'fgrep', 'rg', 'ag', 'ack', 'echo', 'printf'}   # buscan `--fix`, no lo usan

# Los subcomandos que instalan, actualizan o publican.
INSTALLERS = {
    'npm': {'install', 'i', 'ci', 'update', 'uninstall', 'add', 'remove', 'link', 'publish',
            'dedupe', 'prune'},
    'pnpm': {'install', 'i', 'add', 'update', 'up', 'remove', 'rm', 'link', 'publish'},
    'yarn': {'install', 'add', 'remove', 'upgrade', 'up', 'link', 'publish'},
    'bun': {'install', 'add', 'remove', 'update'},
    'composer': {'install', 'update', 'require', 'remove', 'dump-autoload', 'dumpautoload'},
    'pip': {'install', 'uninstall'}, 'pip3': {'install', 'uninstall'},
    'uv': {'add', 'remove', 'sync', 'lock'},
    'cargo': {'add', 'install', 'update', 'remove', 'fix'},
    'go': {'get', 'install', 'generate'},
    'pod': {'install', 'update'}, 'gem': {'install'}, 'bundle': {'install', 'update'},
    'expo': {'install', 'prebuild'}, 'eas': {'build', 'submit', 'update'},
}
# De estos solo pasan los subcomandos que leen.
GIT_READ = {'diff', 'log', 'show', 'status', 'merge-base', 'rev-parse', 'rev-list', 'ls-files',
            'ls-tree', 'blame', 'grep', 'describe', 'cat-file', 'shortlog', 'name-rev',
            'for-each-ref', 'show-ref', 'diff-tree', 'whatchanged', 'reflog', 'check-ignore',
            'check-attr', 'count-objects', 'var', 'version', 'help'}
GIT_LISTS = {      # leen solo con estas banderas, o sin ninguna
    'branch': {'-a', '-r', '-v', '-vv', '--list', '--show-current', '--all', '--remotes',
               '--contains', '--merged', '--no-merged'},
    'tag': {'-l', '--list', '-n', '--contains'},
    'remote': {'-v', 'show', 'get-url'},
    'stash': {'list', 'show'},
    'worktree': {'list'},
    'config': {'--get', '--get-all', '--list', '-l', '--show-origin'},
}
GIT_BARE_WRITES = {'stash', 'config', 'worktree'}      # sin argumentos no listan
GIT_VALUE_FLAGS = {'-C', '-c', '--git-dir', '--work-tree', '--namespace'}
ARTISAN_READ = {'test', 'list', 'about', 'help', 'env', 'route:list', 'config:show', 'model:show',
                'db:show', 'db:table', 'event:list', 'schedule:list'}
DOCKER_READ = {'ps', 'logs', 'inspect', 'images', 'version', 'info', 'top', 'stats', 'port',
               'diff', 'history', 'config', 'ls'}
DOCKER_VALUE_FLAGS = {'-e', '--env', '-u', '--user', '-w', '--workdir', '--env-file', '-f',
                      '--file', '-p', '--project-name'}
SYSTEMCTL_READ = {'status', 'is-active', 'is-enabled', 'is-failed', 'show', 'cat', 'list-units',
                  'list-unit-files', 'list-timers'}
XARGS_VALUE_FLAGS = {'-I', '-n', '-P', '-d', '-L', '-s', '-E'}

# Operación. Un agente que solo lee no entra a ningún servidor ni cambia el
# estado de nada que esté desplegado.
REMOTE = {'ssh', 'scp', 'sftp', 'mosh', 'telnet'}
SSH_VALUE_FLAGS = {'-p', '-i', '-o', '-l', '-J', '-F', '-b', '-c', '-D', '-E', '-e', '-I', '-L',
                   '-m', '-O', '-Q', '-R', '-S', '-W', '-w', '-B', '-P'}
MAKE_READ = {'test', 'tests', 'lint', 'check', 'typecheck', 'analyse', 'analyze', 'stan',
             'phpstan', 'help', 'list'}
MAKE_DRY = {'-n', '--dry-run', '--just-print', '--recon', '-q', '--question', '-p',
            '--print-data-base'}
MAKE_VALUE_FLAGS = {'-C', '-f', '-j', '-I', '-o', '-W'}
GH_READ = {'list', 'view', 'status', 'diff', 'checks', 'watch'}
GH_GROUPS_READ = {'status', 'search', 'help', 'version'}
GH_API_WRITE = {'-f', '-F', '--field', '--raw-field', '--input'}
OPS_READ = {       # de estos solo pasan los subcomandos que consultan
    'kubectl': {'get', 'describe', 'logs', 'top', 'explain', 'version', 'api-resources',
                'api-versions', 'cluster-info', 'diff'},
    'helm': {'list', 'ls', 'status', 'get', 'show', 'template', 'lint', 'version', 'history',
             'search'},
    'terraform': {'plan', 'validate', 'show', 'output', 'version', 'providers', 'graph'},
    'tofu': {'plan', 'validate', 'show', 'output', 'version', 'providers', 'graph'},
    'supervisorctl': {'status', 'avail', 'pid', 'version', 'tail'},
    'certbot': {'certificates', 'show_account'},
    'caddy': {'validate', 'version', 'adapt', 'list-modules', 'environ'},
    'ufw': {'status'},
}
OPS_VALUE_FLAGS = {'-n', '--namespace', '--context', '--kubeconfig', '-c', '--config', '-s'}
ANSIBLE_DRY = {'--syntax-check', '--list-hosts', '--list-tasks', '--version'}

# La única edición en sitio que pasa: insertar una entrada bajo el marcador de
# una bitácora de mes del vault, que es como escribe /bitacora. Con las dos
# rutas literales: una variable no se puede comprobar.
BITACORA_INSERT = re.compile(r'/<!-- BITACORA:INSERT -->/r (\S+)')
BITACORA_FILE = re.compile(r'/Bitacora/\d{4}-\d{2}\.md')


def bitacora_insert(args, scratch):
    """Si un `sed -i` es exactamente la inserción de una entrada de bitácora."""
    if len(args) != 3 or args[0] != '-i' or '..' in args[2]:
        return False
    script = BITACORA_INSERT.fullmatch(args[1])
    target = BITACORA_FILE.search(args[2])
    return bool(script and writable(script.group(1), scratch) and target and target.end() == len(args[2]))

DOCS = {'.md', '.mdx', '.mmd', '.puml', '.txt', '.rst', '.adoc'}
# La configuración de lo que revisa el código: relajarla es la forma barata de
# que algo pase sin arreglarlo.
CHECKS = re.compile(r'''^(
    \.eslintrc(\..+)? | \.eslintignore | eslint\.config\.[cm]?[jt]s
  | \.prettierrc(\..+)? | \.prettierignore | prettier\.config\.[cm]?[jt]s
  | \.stylelintrc(\..+)? | stylelint\.config\.[cm]?[jt]s | biome\.jsonc?
  | pint\.json | phpstan(-baseline)?\.neon(\.dist)? | phpunit\.xml(\.dist)?
  | \.php-cs-fixer(\.dist)?\.php | analysis_options\.yaml | \.golangci\.(ya?ml|toml)
  | \.?ruff\.toml | \.flake8 | mypy\.ini | checkstyle\.xml
  | \.pre-commit-config\.yaml | lefthook\.ya?ml
)$''', re.X)
WORKFLOW = re.compile(r'(^|/)\.github/workflows/[^/]+\.ya?ml$')


def writable(path, scratch):
    """Si se puede escribir ahí: /tmp, /dev o la carpeta de trabajo de la sesión."""
    return bool(path) and (os.path.normpath(path) + '/').startswith(scratch)   # sin `..` que salga


def words(command):
    """El comando en palabras y operadores sueltos (`>>`, `&&`, `|`…), sin los
    cuerpos de los heredoc. ValueError si las comillas no cierran."""
    lexer = shlex.shlex(HEREDOC.sub(r' \3', command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    out = []
    for token in lexer:
        if token and all(c in '();<>|&' for c in token):
            out.extend(OPERATOR.findall(token))
        else:
            out.append(token)
    return out


def segments(tokens):
    """Los comandos simples de una línea: lo que hay entre `;`, `&&`, `|`…"""
    current = []
    for token in tokens:
        if token in SEPARATORS:
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def redirect(segment, scratch):
    """El motivo si una redirección escribe fuera de /tmp, o None."""
    for i, token in enumerate(segment):
        if '>' not in token or not OPERATOR.fullmatch(token):
            continue
        target = segment[i + 1] if i + 1 < len(segment) else ''
        if '&' in token and (target.isdigit() or target == '-'):
            continue                                  # 2>&1: no es un archivo
        if not writable(target, scratch):
            return f'redirige la salida a `{target}`'
    return None


def strip(segment):
    """El comando sin sus redirecciones ni las variables que lleva delante."""
    out, skip = [], False
    for token in segment:
        if skip:
            skip = False
        elif OPERATOR.fullmatch(token):
            skip = True                               # el operador y su destino
            if out and out[-1].isdigit():
                out.pop()                             # el 2 de `2>`
        elif not (not out and ASSIGN.match(token)):
            out.append(token)
    return out


def after_options(args, value_flags=()):
    """Los argumentos desde el primero que no es una opción."""
    i = 0
    while i < len(args) and (args[i].startswith('-') or ASSIGN.match(args[i])):
        i += 2 if args[i] in value_flags else 1
    return args[i:]


# Modo `entrega`: además de leer, deja preparar, commitear, subir y abrir el
# PR. Lo prende `main`; no va como argumento porque `check` y `simple` se
# llaman una a otra por una docena de sitios.
DELIVERS = False
GIT_ADD_ALL = {'-A', '--all', '-u', '--update', '.'}        # lo que barre con todo: se prepara por ruta
GIT_COMMIT_NO = {'--amend', '--no-verify', '-n', '-a', '--all'}
GIT_PUSH_NO = {'-f', '--force', '--force-with-lease', '--force-if-includes', '-d', '--delete', '--mirror',
               '--all', '--tags', '--prune'}
GH_PR_DELIVER = {'create', 'edit'}


def git_delivery(sub, rest):
    """De un `git` que cambia el repositorio: None si es de los de entregar
    un cambio (preparar por ruta, commit, subir la rama, rama nueva, traer),
    o por qué así no pasa. '' si no es de entregar."""
    flags = {a.split('=')[0] for a in rest if a.startswith('-')}
    flags |= {f'-{c}' for a in rest if re.fullmatch(r'-[a-zA-Z]{2,}', a) for c in a[1:]}     # -am es -a y -m
    if sub == 'fetch':
        return None
    if sub == 'add':
        return 'prepara los archivos por su ruta, no todos a la vez' if GIT_ADD_ALL & set(rest) else None
    if sub == 'commit':
        bad = sorted(GIT_COMMIT_NO & flags)
        return f'`git commit {bad[0]}` reescribe, barre o se salta las verificaciones' if bad else None
    if sub == 'push':
        if GIT_PUSH_NO & flags or any(a.startswith('+') or a.startswith(':') for a in rest):
            return '`git push` forzado, o que borra ramas o las sube todas, no es de una entrega'
        return None
    if sub in ('switch', 'checkout') and rest[:1] in (['-c'], ['-b']) and len(rest) <= 3:
        return None                                   # una rama nueva, desde aquí o desde otra
    return ''


def git(args, scratch):
    args = after_options(args, GIT_VALUE_FLAGS)
    if not args or args[0] in GIT_READ:
        return None
    sub, rest = args[0], args[1:]
    if DELIVERS:
        reason = git_delivery(sub, rest)
        if reason != '':
            return reason
    if sub == 'clone':                                # un repo ajeno, para leerlo: solo en /tmp
        named = [a for a in rest if not a.startswith('-') and not a.isdigit()]     # origen y destino
        return None if len(named) == 2 and writable(named[1], scratch) else '`git clone` fuera de /tmp'
    if sub in GIT_LISTS and (rest[0] in GIT_LISTS[sub] if rest else sub not in GIT_BARE_WRITES):
        return None
    return f'`git {sub}` cambia el repositorio'


def make(args):
    if MAKE_DRY & set(args):
        return None
    targets, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in MAKE_VALUE_FLAGS:
            skip = True
        elif not a.startswith('-') and not ASSIGN.match(a):
            targets.append(a)
    if not targets:
        return '`make` a secas corre el target por omisión, que puede cambiar cosas'
    for target in targets:
        if target not in MAKE_READ:
            return f'`make {target}` puede cambiar cosas; `make -n {target}` enseña qué haría'
    return None


def gh(args):
    args = after_options(args, {'-R', '--repo'})
    if not args or args[0] in GH_GROUPS_READ:
        return None
    group, rest = args[0], args[1:]
    if group == 'api':
        for i, a in enumerate(rest):
            method = rest[i + 1] if a in ('-X', '--method') and i + 1 < len(rest) else a[2:] if a.startswith('-X') else ''
            if method and method.upper() != 'GET':
                return f'`gh api -X {method}` modifica GitHub'
            if a in GH_API_WRITE:
                return '`gh api` con campos modifica GitHub'
        return None
    verb = after_options(rest, {'-R', '--repo'})[:1]
    if verb and verb[0] in GH_READ:
        return None
    if DELIVERS and group == 'pr' and verb and verb[0] in GH_PR_DELIVER:
        return None                                   # abrir el PR de la rama, o corregir su título y cuerpo
    if DELIVERS and group == 'auth' and verb == ['token']:
        return None                                   # para un solo comando: GH_TOKEN=$(gh auth token --user X) gh …
    return f'`gh {group} {verb[0] if verb else ""}` cambia algo en GitHub o en este repositorio'


def docker(args, scratch, depth):
    args = after_options(args, DOCKER_VALUE_FLAGS)
    if args[:1] == ['compose']:
        args = after_options(args[1:], DOCKER_VALUE_FLAGS)
    if not args or args[0] in DOCKER_READ:
        return None
    if args[0] != 'exec':
        return f'`docker {args[0]}` cambia contenedores'
    inner = after_options(args[1:], DOCKER_VALUE_FLAGS)[1:]      # sin el contenedor
    return simple(inner, scratch, depth + 1)


def ssh(args, scratch, depth):
    """`ssh host comando`: pasa si el comando remoto también es de solo lectura."""
    rest = after_options(args, SSH_VALUE_FLAGS)[1:]               # sin el host
    if not rest:
        return '`ssh` sin un comando abre una sesión interactiva'
    reason = check(' '.join(rest), scratch, depth + 1)
    return f'en el servidor, {reason}' if reason else None


def scp(args, scratch):
    """`scp host:ruta local`: solo para traer algo a /tmp; subir cambia el servidor."""
    paths = [a for a in after_options(args, SSH_VALUE_FLAGS) if not a.startswith('-')]
    if len(paths) < 2 or ':' in paths[-1] or not writable(paths[-1], scratch):
        return '`scp` solo trae archivos del servidor, y a /tmp'
    return None


def simple(segment, scratch, depth=0):
    """El motivo por el que un comando simple no es de solo lectura, o None."""
    reason = redirect(segment, scratch)
    if reason or depth > DEPTH:
        return reason
    args = strip(segment)
    if not args:
        return None
    name, rest = os.path.basename(args[0]), args[1:]

    if name in ROOT:
        return f'`{name}` corre con otros permisos'
    if name in WRAPPERS:
        rest = after_options(rest, {'-n', '-u', '-s', '-k'})
        return simple(rest[1:] if name == 'timeout' else rest, scratch, depth + 1)
    if name in SHELLS and '-c' in rest:
        return check(' '.join(rest[rest.index('-c') + 1:][:1]), scratch, depth + 1)
    if name == 'eval':
        return check(' '.join(rest), scratch, depth + 1)
    if name == 'xargs':
        return simple(after_options(rest, XARGS_VALUE_FLAGS), scratch, depth + 1)
    if name == 'find':
        if '-delete' in rest:
            return '`find -delete` borra archivos'
        for flag in ('-exec', '-execdir', '-ok', '-okdir'):
            if flag in rest:
                return simple(rest[rest.index(flag) + 1:], scratch, depth + 1)
        return None
    if name in SEARCHERS:
        return None

    if name in WRITERS or name in STOPPERS:
        return f'`{name}` modifica archivos o procesos'
    if name in TO_DEST:
        targets = [a for a in rest if not a.startswith('-')]
        every = name in ('mkdir', 'touch', 'tee')
        if not all(writable(t, scratch) for t in (targets if every else targets[-1:] or [''])):
            return f'`{name}` escribe fuera de /tmp'
        return None
    if name == 'sed' and any(re.match(r'-[a-zA-Z]*i|--in-place', a) for a in rest):
        return None if bitacora_insert(rest, scratch) else '`sed -i` edita el archivo'
    if name == 'perl' and any(re.match(r'-[pnlae0]*i', a) for a in rest):
        return '`perl -i` edita el archivo'
    if name in ('awk', 'gawk') and 'inplace' in rest:
        return '`awk -i inplace` edita el archivo'
    if name == 'git':
        return git(rest, scratch)
    if name == 'docker':
        return docker(rest, scratch, depth)
    if name in SYSTEM_PACKAGES:
        return f'`{name}` instala o quita paquetes del sistema'
    if name == 'systemctl':
        sub = after_options(rest)[:1]
        return None if not sub or sub[0] in SYSTEMCTL_READ else f'`systemctl {sub[0]}` cambia un servicio'
    if name in REMOTE:
        if DELIVERS and name == 'ssh':
            return ssh(rest, scratch, depth)
        if DELIVERS and name == 'scp':
            return scp(rest, scratch)
        return f'`{name}` se conecta a otro equipo'
    if name == 'make':
        return make(rest)
    if name == 'gh':
        return gh(rest)
    if name in OPS_READ:
        sub = after_options(rest, OPS_VALUE_FLAGS)[:1]
        return None if not sub or sub[0] in OPS_READ[name] else f'`{name} {sub[0]}` cambia lo que está desplegado'
    if name == 'crontab' and rest != ['-l']:
        return '`crontab` sin `-l` cambia las tareas programadas'
    if name == 'nginx' and '-s' in rest:
        return '`nginx -s` manda una señal al servidor web'
    if name in ('ansible', 'ansible-playbook') and not (ANSIBLE_DRY & set(rest)):
        return f'`{name}` ejecuta sobre servidores'

    sub = after_options(rest)
    if name == 'yarn' and not sub:
        return '`yarn` a secas instala dependencias'
    if name in INSTALLERS and sub and sub[0] in INSTALLERS[name]:
        return f'`{name} {sub[0]}` instala o cambia dependencias'
    if name == 'uv' and sub[:2] == ['pip', 'install']:
        return '`uv pip install` instala dependencias'
    if name == 'npm' and sub[:2] == ['audit', 'fix']:
        return '`npm audit fix` cambia dependencias'
    if name == 'go' and sub[:2] == ['mod', 'tidy']:
        return '`go mod tidy` reescribe go.mod'
    if name == 'npx' and sub:
        return simple(sub, scratch, depth + 1)
    if name in ('flutter', 'dart'):
        if sub[:1] == ['pub'] and sub[1:2] and sub[1] in ('get', 'upgrade', 'add', 'remove', 'downgrade'):
            return f'`{name} pub {sub[1]}` cambia dependencias'
        if sub[:1] in (['clean'], ['create']):
            return f'`{name} {sub[0]}` modifica el proyecto'
        if sub[:2] == ['fix', '--apply'] or (sub[:1] == ['fix'] and '--apply' in sub):
            return '`dart fix --apply` reescribe el código'
        if sub[:1] == ['format'] and not re.search(r'(--output|-o)[= ]?none', ' '.join(sub)):
            return '`dart format` sin `--output=none` reescribe los archivos'
    if name == 'artisan' or (name == 'php' and sub[:1] and os.path.basename(sub[0]) == 'artisan'):
        command = after_options(sub if name == 'artisan' else sub[1:])[:1]
        if command and command[0] not in ARTISAN_READ:
            return f'`artisan {command[0]}` puede cambiar la aplicación o su base de datos'
        return None
    if name == 'php' and sub:
        return simple(sub, scratch, depth + 1)        # php vendor/bin/pint
    if name in SQL_CLIENTS and SQL_WRITE.search(' '.join(rest)):
        return f'`{name}` con una sentencia que escribe en la base de datos'
    if name == 'curl':
        for i, a in enumerate(rest):
            if a in ('-O', '--remote-name') or re.fullmatch(r'-[a-zA-Z]*O', a):
                return '`curl -O` descarga un archivo aquí'
            if a in ('-o', '--output') or re.fullmatch(r'-[a-zA-Z]*o', a):
                if not writable(rest[i + 1] if i + 1 < len(rest) else '', scratch):
                    return '`curl -o` escribe fuera de /tmp'
            if a in ('-d', '-F', '--form', '-T') or a.startswith('--data'):
                return '`curl` con datos modifica un servidor'
            if a in ('-X', '--request') and rest[i + 1:i + 2] and rest[i + 1].upper() not in ('GET', 'HEAD', 'OPTIONS'):
                return f'`curl -X {rest[i + 1]}` modifica un servidor'
        return None
    if name == 'wget' and not ({'-O-', '-qO-'} & set(rest) or ' '.join(rest).count('-O -')):
        return '`wget` descarga un archivo aquí'

    if name == 'vaultdocs' and sub[:1] == ['project']:
        return None                                   # el esqueleto del proyecto en el vault: no pisa nada
    if WRITE_FLAGS & set(rest):
        return f'`{name}` con `{sorted(WRITE_FLAGS & set(rest))[0]}` reescribe archivos'
    if name in ('gofmt', 'goimports') and '-w' in rest:
        return f'`{name} -w` reescribe archivos'
    if name == 'pint' and '--test' not in rest:
        return '`pint` sin `--test` reformatea el código'
    if name == 'php-cs-fixer' and 'fix' in rest and '--dry-run' not in rest:
        return '`php-cs-fixer fix` sin `--dry-run` reformatea el código'
    if name == 'black' and not ({'--check', '--diff'} & set(rest)):
        return '`black` sin `--check` reformatea el código'
    if name == 'ruff' and sub[:1] == ['format'] and not ({'--check', '--diff'} & set(rest)):
        return '`ruff format` sin `--check` reformatea el código'
    return None


CRUDE = re.compile(r'''(^|[;&|(]\s*)(rm|rmdir|mv|ln|chmod|chown|truncate|dd|sudo|git\s+(add|commit|push|
    pull|merge|rebase|reset|checkout|switch|restore|stash|clean))\b
    | (?<![0-9&>=-])>>?(?!>)(?!\s*(&|/tmp/|/dev/))''',
                   re.X | re.M)


def check(command, scratch=SCRATCH, depth=0):
    """El motivo por el que una línea de Bash no es de solo lectura, o None."""
    try:
        tokens = words(command)
    except ValueError:                                # comillas sin cerrar: a lo bruto
        return 'parece escribir, y no se pudo analizar con detalle' if CRUDE.search(command) else None
    for segment in segments(tokens):
        reason = simple(segment, scratch, depth)
        if reason:
            return reason
    if depth < DEPTH:                                 # lo que va en $(…) o entre acentos graves
        # El cuerpo de un heredoc entre comillas (<<'EOF') es texto: ahí no corre nada.
        quoted = HEREDOC.sub(lambda m: f' {m.group(3)}' if m.group(1) else m.group(0), command)
        for inner in SUBSHELL.findall(quoted):
            reason = check(inner[0] or inner[1], scratch, depth + 1)
            if reason:
                return reason
    return None


def docs_only(path):
    """El motivo por el que un agente que solo documenta no puede escribir ese
    archivo, o None."""
    ext = os.path.splitext(path)[1].lower()
    return None if ext in DOCS else f'`{os.path.basename(path)}` no es documentación ({", ".join(sorted(DOCS))})'


def protected(path):
    """Si es la configuración, ya existente, de algo que revisa el código."""
    if not (CHECKS.match(os.path.basename(path)) or WORKFLOW.search(path)):
        return False
    return os.path.exists(path)


def main(argv=None, stdin=None, out=None, err=None):
    argv = sys.argv[1:] if argv is None else argv
    out, err = out or sys.stdout, err or sys.stderr
    try:
        payload = json.load(stdin or sys.stdin)
    except ValueError:
        return 0
    mode = argv[0] if argv else ''
    tool_input = payload.get('tool_input') or {}
    path = tool_input.get('file_path') or ''
    if mode in ('solo-lectura', 'entrega'):
        global DELIVERS
        DELIVERS = mode == 'entrega'
        scratch = SCRATCH + tuple(d.rstrip('/') + '/' for d in [payload.get('scratchpad_dir')] if d)
        reason = check(tool_input.get('command') or '', scratch)
        if reason:
            does = 'lee y entrega (commit, push y PR)' if DELIVERS else 'solo lee'
            print(f'elyares-guard: este agente {does}, y el comando no pasó: {reason}. No lo '
                  'rodees: si de verdad hace falta, dilo en tu informe para que lo haga el '
                  'engineer. Para un archivo temporal usa /tmp.', file=err)
            return 2
    elif mode == 'solo-docs':
        reason = docs_only(path) if path else None
        if reason:
            print(f'elyares-guard: este agente solo escribe documentación: {reason}. Lo que '
                  'haya que cambiar en el código o la configuración va en tu informe.', file=err)
            return 2
    elif mode == 'config' and path and protected(path):
        json.dump({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'ask',
            'permissionDecisionReason':
                f'{os.path.basename(path)} configura una verificación del código (linter, '
                'analizador, formateador, pruebas o CI). Relajarla para que algo pase está '
                'prohibido por el estándar: confirma solo si el cambio es intencional.'}}, out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
