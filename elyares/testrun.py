"""Corridas de pruebas: reconocer el comando, leer lo que imprime y seguirlo en vivo.

`is_test()` dice si un comando corre pruebas (pytest, pest, vitest, jest,
`go test`, `cargo test`, `make test`…) y `parse()` saca de lo que imprimió qué
pruebas pasaron, cuáles fallaron y cuáles se saltaron. No pregunta qué
programa es: prueba cada línea contra las formas que usan todos.

Lo que se puede saber depende de lo que el programa imprime. Con una línea
por prueba (`pytest -v`, pest, `go test -v`, cargo) sale la lista entera. Con
puntos (`pytest`, unittest, phpunit) solo se sabe cuántas van, y el nombre de
las que fallan cuando el programa las nombra, casi siempre al final.

En una terminal las pruebas se siguen mientras corren: `shell/elyares.bash`
le pide a tmux que copie a un archivo lo que imprime el pane (`pipe-pane`) y
`Follower` lo relee cada medio segundo. Al terminar, el archivo se borra.
"""

import os
import re
import threading
from dataclasses import dataclass, field

OK, FAIL, SKIP = 'ok', 'fail', 'skip'
MARKS = {OK: '✓', FAIL: '✗', SKIP: '○'}
LIST_LINES = 10           # pruebas que caben en la ficha
POLL_SECS = .5
MAX_SECS = 3600           # una corrida más larga que esto ya no se sigue
MAX_LOG = 2 << 20         # de un archivo más grande solo se lee el final
FLUSH_SECS = .15          # lo que tarda tmux en soltar lo último al cerrar la copia

# El mismo patrón está en shell/elyares.bash (`__ely_test_re`), que es quien
# decide en una terminal: una prueba de tests/ revisa que digan lo mismo.
TEST = re.compile(
    r'(?:^|[\s/;&|(])(?:pytest|py\.test|phpunit|pest|vitest|jest|tox'
    r'|(?:artisan|sail|go|cargo|deno|bun|mvn|composer|make|just|npm|pnpm|yarn)(?: +run)? +test[\w:.-]*'
    r'|-m +unittest)(?=$|[\s;&|)])')

# Lo que deja una terminal además del texto: colores, movimientos del cursor,
# títulos de ventana y otros caracteres de control.
_ESC = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]'
                  r'|\x1b[@-Z\\-_=>]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_TIME = re.compile(r'\s+\(?\d+(?:\.\d+)?\s?m?s\)?$')

_PASS_MARK = re.compile(r'^\s*[✓✔√]\s+(.+)$')                 # pest, jest, vitest, phpunit --testdox
_FAIL_MARK = re.compile(r'^\s*[✕✗✘×⨯]\s+(.+)$')
_SKIP_MARK = re.compile(r'^\s*○\s+(?:skipped\s+)?(.+)$')       # jest
_PYTEST = re.compile(r'^(\S+::.+?) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)(?:\s|$)')
_PYTEST_FAILED = re.compile(r'^(?:FAILED|ERROR) (\S+::.+?)(?: - .*)?$')
_PHPUNIT_FAILED = re.compile(r'^\d+\) (\S+::\S+)')               # la lista de fallos de phpunit
_UNITTEST = re.compile(r'^(\w+) \(([\w.]+)\)(?: \.\.\. (.+))?$')
_UNITTEST_DOC = re.compile(r' \.\.\. (ok|FAIL|ERROR|skipped .*|expected failure|unexpected success)$')
_UNITTEST_FAILED = re.compile(r'^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)')
_GO = re.compile(r'^\s*--- (PASS|FAIL|SKIP): (\S+)')
_GO_PKG = re.compile(r'^ok\s+(\S+)\s+(?:[\d.]+s|\(cached\))')
_CARGO = re.compile(r'^test (.+?) \.\.\. (ok|FAILED|ignored)')
# Una letra por prueba: pytest las trae con su porcentaje; unittest y phpunit, solas.
_DOTS_PYTEST = re.compile(r'^(?:\S+\.py ([.FEsxX]+)(?:\s+\[\s*\d+%\])?|([.FEsxX]+)\s+\[\s*\d+%\])$')
_DOTS = re.compile(r'^([.FEsxSRIWN]+)(?:\s+\d+ / \d+ \(\s*\d+%\))?$')

_COUNT = re.compile(r'(\d+) (passed|failed|errors?|skipped|ignored|todo|pending|incomplete|xfailed|xpassed)')
_KINDS = {'passed': OK, 'xpassed': OK, 'failed': FAIL, 'error': FAIL, 'errors': FAIL}
_SUM_PYTEST = re.compile(r'^=* ?(.*\d+ \w+.*) in [\d.]+s(?: \([\d:]+\))? ?=*$')
_SUM_TESTS = re.compile(r'^\s*Tests:?\s+(.+)$')                # pest, jest, vitest y phpunit
_SUM_PHPUNIT_OK = re.compile(r'^OK \((\d+) tests?, \d+ assertions?\)')
_SUM_UNITTEST = re.compile(r'^Ran (\d+) tests? in [\d.]+s$')
_SUM_UNITTEST_END = re.compile(r'^(OK|FAILED)(?: \((.+)\))?$')
_SUM_CARGO = re.compile(r'^test result: \w+\. (\d+) passed; (\d+) failed; (\d+) ignored')
_STATUS = {'PASSED': OK, 'XPASS': OK, 'PASS': OK, 'ok': OK, 'FAILED': FAIL, 'ERROR': FAIL,
           'FAIL': FAIL, 'unexpected success': FAIL, 'SKIPPED': SKIP, 'XFAIL': SKIP, 'SKIP': SKIP,
           'ignored': SKIP, 'expected failure': SKIP}


def is_test(command):
    """¿Este comando corre pruebas?"""
    return bool(TEST.search(command or ''))


def clean(raw):
    """Lo que imprimió una terminal, como texto: sin colores ni movimientos del
    cursor. Un retorno de carro (una línea que se reescribe) cuenta como salto."""
    return _ESC.sub('', raw or '').replace('\r\n', '\n').replace('\r', '\n')


@dataclass
class Run:
    items: dict = field(default_factory=dict)     # prueba -> estado, en el orden en que salieron
    dots: dict = field(default_factory=lambda: {OK: 0, FAIL: 0, SKIP: 0})
    totals: dict = None                           # lo que dijo el resumen del programa, si lo hubo

    def count(self, status):
        if self.totals is not None:
            return self.totals[status]
        return max(sum(1 for s in self.items.values() if s == status), self.dots[status])

    @property
    def passed(self):
        return self.count(OK)

    @property
    def failed(self):
        return self.count(FAIL)

    @property
    def skipped(self):
        return self.count(SKIP)

    @property
    def ran(self):
        """¿Se vio alguna prueba? Si no, lo que corrió no eran pruebas o no se entendió."""
        return bool(self.items or self.totals is not None or any(self.dots.values()))

    def _total(self, **counts):
        if self.totals is None:
            self.totals = {OK: 0, FAIL: 0, SKIP: 0}
        for status, n in counts.items():
            self.totals[status] += n


def _name(text):
    return _TIME.sub('', text.strip())


def _method(name, path):
    """`test_a (mod.Clase.test_a)` -> `Clase.test_a`."""
    parts = path.split('.')
    return '.'.join(parts[-2:]) if parts[-1] == name and len(parts) > 1 else f'{parts[-1]}.{name}'


def _counts(text):
    out = {OK: 0, FAIL: 0, SKIP: 0}
    for n, kind in _COUNT.findall(text):
        out[_KINDS.get(kind, SKIP)] += int(n)
    return out


def parse(text):
    """Las pruebas que se ven en lo que imprimió un programa de pruebas.

    Vale también a medias, con el programa todavía corriendo: da lo que va.
    Si el programa trae su resumen, los números salen de ahí.
    """
    run = Run()
    pending = None      # prueba de unittest cuyo resultado viene en la línea siguiente
    ran = None          # el "Ran N tests" de unittest, que espera su OK o su FAILED
    for line in (text or '').splitlines():
        line = line.rstrip()
        if not line:
            continue
        if pending:
            name, pending = pending, None
            m = _UNITTEST_DOC.search(line)
            if m:
                run.items[name] = _STATUS.get(m[1], SKIP)
                continue
        if ran is not None:
            m = _SUM_UNITTEST_END.match(line)
            if m:
                parts = {k.strip(): n for k, n in re.findall(r'([\w ]+)=(\d+)', m[2] or '')}
                failed = sum(int(parts.get(k, 0)) for k in ('failures', 'errors', 'unexpected successes'))
                skipped = sum(int(parts.get(k, 0)) for k in ('skipped', 'expected failures'))
                run._total(ok=ran - failed - skipped, fail=failed, skip=skipped)
                ran = None
                continue
        m = _SUM_UNITTEST.match(line)
        if m:
            ran = int(m[1])
            continue
        m = _SUM_CARGO.match(line)
        if m:
            run._total(ok=int(m[1]), fail=int(m[2]), skip=int(m[3]))
            continue
        m = _SUM_PHPUNIT_OK.match(line)
        if m:
            run._total(ok=int(m[1]))
            continue
        m = _SUM_TESTS.match(line)
        if m and 'Assertions:' in m[1]:
            # phpunit: "Tests: 8, Assertions: 10, Failures: 1, Skipped: 1."
            nums = {k: int(v) for k, v in re.findall(r'(\w+): (\d+)', line)}
            failed = nums.get('Failures', 0) + nums.get('Errors', 0)
            skipped = nums.get('Skipped', 0) + nums.get('Incomplete', 0)
            run._total(ok=nums.get('Tests', 0) - failed - skipped, fail=failed, skip=skipped)
            continue
        m = m or _SUM_PYTEST.match(line)
        if m and _COUNT.search(m[1]):
            run._total(**_counts(m[1]))
            continue
        m = _PYTEST.match(line)
        if m:
            run.items[m[1]] = _STATUS[m[2]]
            continue
        m = _PYTEST_FAILED.match(line) or _PHPUNIT_FAILED.match(line)
        if m:
            run.items[m[1]] = FAIL
            continue
        m = _UNITTEST_FAILED.match(line)
        if m:
            run.items[_method(m[1], m[2])] = FAIL
            continue
        m = _UNITTEST.match(line)
        if m:
            name = _method(m[1], m[2])
            if m[3] is None:
                pending = name      # trae docstring: el resultado va en la línea siguiente
            else:
                run.items[name] = SKIP if m[3].startswith('skipped') else _STATUS.get(m[3], FAIL)
            continue
        m = _GO.match(line)
        if m:
            run.items[m[2]] = _STATUS[m[1]]
            continue
        m = _GO_PKG.match(line)
        if m:
            # Sin -v, go solo nombra las que fallan: de las demás queda el paquete.
            run.items.setdefault(m[1], OK)
            continue
        m = _CARGO.match(line)
        if m:
            run.items[m[1]] = _STATUS[m[2]]
            continue
        for pattern, status in ((_PASS_MARK, OK), (_FAIL_MARK, FAIL), (_SKIP_MARK, SKIP)):
            m = pattern.match(line)
            if m:
                run.items[_name(m[1])] = status
                break
        else:
            m = _DOTS_PYTEST.match(line)
            dots = (m[1] or m[2]) if m else None
            if dots is None:
                # Sin nada alrededor, una sola letra puede ser cualquier cosa.
                m = _DOTS.match(line)
                dots = m[1] if m and ('.' in m[1] or len(m[1]) > 1) else ''
            run.dots[OK] += dots.count('.')
            run.dots[FAIL] += sum(dots.count(c) for c in 'FE')
            run.dots[SKIP] += sum(dots.count(c) for c in 'sxXSRIWN')
    return run


def listing(run, n=LIST_LINES):
    """Las líneas de la ficha: primero las que fallaron, luego las últimas que
    corrieron. Cada una con su marca: ✓, ✗ o ○."""
    failed = [name for name, status in run.items.items() if status == FAIL]
    rest = [(name, status) for name, status in run.items.items() if status != FAIL]
    lines = [f'{MARKS[FAIL]} {name}' for name in failed[:n]]
    if len(failed) > n:
        lines[-1] = f'{MARKS[FAIL]} … y {len(failed) - n + 1} más que fallaron'
    room = n - len(lines)
    return lines + [f'{MARKS[status]} {name}' for name, status in rest[-room:]] if room else lines


def results(run):
    """Una corrida como datos planos, para mandarla en un mensaje."""
    return {'ran': run.ran, 'passed': run.passed, 'failed': run.failed, 'skipped': run.skipped,
            'lines': listing(run)}


def log_path(pane):
    """El archivo donde tmux copia lo que imprime un pane mientras corren pruebas.

    Sale del id del pane y nunca de lo que diga un mensaje: elyares-engineer lee y
    borra este archivo, y quien escriba en el socket no debe elegir cuál.
    """
    if not re.fullmatch(r'%\d+', pane or ''):
        return ''
    base = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    return os.path.join(base, f'elyares-tests-{pane[1:]}.log')


def read(path):
    """Lo que hay en el archivo, ya como texto limpio. '' si no existe."""
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - MAX_LOG))
            return clean(f.read().decode(errors='replace'))
    except OSError:
        return ''


class Follower:
    """Sigue las pruebas que corren en las terminales y avisa de cómo van.

    `start` y `finish` reciben los mensajes `cmd-start` y `cmd-done` de la
    terminal. Lo que se va sabiendo sale por `emit` como el mismo mensaje con
    `results` dentro.
    """

    def __init__(self, emit, interval=POLL_SECS, flush=FLUSH_SECS):
        self.emit, self.interval, self.flush = emit, interval, flush
        self.live = {}          # alerta -> el aviso que para a quien la sigue
        self.ended = {}         # alerta -> cuándo terminó su último comando
        self.lock = threading.Lock()

    def start(self, msg):
        """Empieza a seguir una corrida. False si no hay nada que seguir."""
        sid, path = str(msg.get('session_id') or ''), log_path(msg.get('pane'))
        if not path:
            return False
        try:
            at = float(msg.get('at') or 0)
        except (TypeError, ValueError):
            at = 0
        stop = threading.Event()
        with self.lock:
            # Un comando que acaba al instante: su final puede llegar antes
            # que su principio, y la alerta se quedaría "corriendo" para siempre.
            if at and at <= self.ended.get(sid, 0):
                return False
            if sid in self.live:
                self.live[sid].set()
            self.live[sid] = stop
        threading.Thread(target=self._follow, args=(msg, path, stop), daemon=True,
                         name='pruebas').start()
        return True

    def _follow(self, msg, path, stop):
        seen, waited = None, 0
        while not stop.wait(self.interval) and waited < MAX_SECS:
            waited += self.interval
            res = results(parse(read(path)))
            if res['ran'] and res != seen:
                seen = res
                # Otra vez, por si terminó mientras se leía: el final manda.
                if not stop.is_set():
                    self.emit({**msg, 'results': res})

    def finish(self, msg):
        """El comando terminó. True si eran pruebas que se copiaron a un
        archivo: el mensaje volverá por `emit` con sus resultados."""
        sid, path = str(msg.get('session_id') or ''), log_path(msg.get('pane'))
        try:
            at = float(msg.get('at') or 0)
        except (TypeError, ValueError):
            at = 0
        with self.lock:
            if at:
                self.ended[sid] = at
            stop = self.live.pop(sid, None)
        if stop:
            stop.set()
        if not path or not os.path.exists(path):
            return False

        def last():
            threading.Event().wait(self.flush)
            res = results(parse(read(path)))
            try:
                os.unlink(path)
            except OSError:
                pass
            self.emit({**msg, 'results': res})

        threading.Thread(target=last, daemon=True, name='pruebas-fin').start()
        return True
