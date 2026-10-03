"""El candado de los agentes: qué comandos deja pasar y cuáles frena."""

import io
import json
import os
import tempfile
import unittest

from elyares import guard


class SoloLectura(unittest.TestCase):
    PASA = [
        'git diff main...HEAD', 'git -C /x/proj log --oneline -5', 'git --no-pager show HEAD~1',
        'B=$(git merge-base HEAD main) && git diff $B', 'git branch --show-current',
        'git branch -a', 'git stash list', 'git config --get user.name', 'git worktree list',
        'rg -n "TODO" src | head -20', 'grep -rn -- --fix .github', 'cat a.txt 2>/dev/null',
        'ls -la; wc -l src/*.py', 'find . -name "*.dart" -newer pubspec.yaml',
        'sed -n 1,20p README.md', 'jq .hooks ~/.claude/settings.json',
        'flutter analyze', 'flutter test test/login_test.dart',
        'dart format --output=none --set-exit-if-changed lib/a.dart', 'dart format -o none lib',
        'npx tsc --noEmit', 'npx eslint src/a.ts', 'npm audit --omit=dev', 'npm test',
        'vendor/bin/pest tests/Feature/XTest.php', 'vendor/bin/pint --test',
        'php artisan test --compact', 'php artisan route:list --except-vendor',
        'php -d memory_limit=1G vendor/bin/phpstan analyse', 'composer audit --locked',
        "docker exec app-1 sh -c 'cd /app && vendor/bin/pest tests/Feature'", 'docker ps',
        'docker compose logs --tail 50 app', 'make test', 'go test ./...', 'govulncheck ./...',
        'gitleaks git --redact --report-path /tmp/gitleaks.json', 'semgrep scan --metrics=off',
        'osv-scanner scan source -r . > /tmp/osv.txt', 'trivy fs . 2>&1 | tee /tmp/trivy.txt',
        'mkdir -p /tmp/auditoria && cp composer.lock /tmp/auditoria/', 'echo listo >&2',
        'command -v flutter', 'timeout 60 flutter analyze', 'FOO=1 env BAR=2 pytest -q',
        'curl -I https://ejemplo.mx', 'curl -s https://ejemplo.mx -o /tmp/pagina.html',
        'systemctl --user status elyares-engineer', 'psql -c "select count(*) from users"',
        "python3 - <<'EOF'\nimport json\nprint(json.load(open('a.json'))['rm'])\nEOF",
        # el cuerpo de un heredoc entre comillas es texto, con sus acentos graves y sus `>`
        "cat > /tmp/nota.md <<'EOF'\nSe abre con `a > b` o `rm x`.\nEOF\nls -l /tmp/nota.md",
        # operación: ver sin tocar
        'make -n update', 'make --dry-run -C api deploy', 'make lint', 'make -j4 test',
        'gh run view 123 --log-failed', 'gh pr view 12', 'gh pr checks', 'gh pr diff 12',
        'gh run list --branch main --workflow ci.yml', 'gh api repos/a/b/actions/runs',
        'gh -R a/b run list', 'gh auth status', 'kubectl get pods -A', 'kubectl -n app logs web',
        'terraform plan', 'terraform validate', 'helm template x ./chart', 'supervisorctl status',
        'crontab -l', 'docker compose config', 'nginx -t', 'caddy validate --config Caddyfile',
        'ansible-playbook site.yml --syntax-check', 'ufw status',
        # investigación: un repo ajeno se clona en /tmp
        'git clone --depth 1 https://github.com/a/b.git /tmp/b', 'git -C /tmp/b log --oneline -3',
        'gh api repos/a/b --jq .stargazers_count', 'curl -sL https://ejemplo.mx/doc.md',
        # la bitácora del vault: detectar, garantizar la estructura e insertar la entrada
        'vaultdocs detect --cwd /x/proj', 'vaultdocs projects', 'vaultdocs project homelab',
        'vaultdocs project homelab --write',
        "sed -i '/<!-- BITACORA:INSERT -->/r /tmp/entrada.md' '/v/10 Projects/homelab/Bitacora/2026-10.md'",
        "grep -q 'BITACORA:INSERT' '/v/10 Projects/homelab/Bitacora/2026-10.md' || { echo FALTA; exit 1; }",
        "grep -c '^## ' '/v/10 Projects/homelab/Bitacora/2026-10.md'",
    ]
    FRENA = [
        'rm -rf build', 'mv a b', 'touch nuevo.txt', 'mkdir docs/x', 'cp a.txt b.txt',
        'echo hola > salida.txt', 'echo hola >> README.md', 'cat a | tee b.txt',
        'ls &> registro.log', "cat <<EOF > src/x.py\nprint(1)\nEOF",
        'sed -i s/a/b/ x.txt', 'sed -ni /a/p x.txt', 'perl -pi -e s/a/b/ x.txt',
        'git add -A', 'git commit -m x', 'git push', 'git checkout -- .', 'git switch -c rama',
        'git stash', 'git reset --hard', 'git branch -D rama', 'git config user.name x',
        'git -C /x/proj clean -fd', 'ls && git restore .', 'true || (cd web; git pull)',
        'npm install', 'npm i left-pad', 'npm audit fix', 'pnpm add x', 'yarn', 'yarn add x',
        'composer install', 'composer require a/b', 'pip install requests', 'uv pip install x',
        'flutter pub get', 'dart pub add http', 'pod install', 'npx expo install expo-camera',
        'go mod tidy', 'cargo add serde', 'sudo pacman -S jq', 'yay -S x',
        'dart format lib', 'flutter clean', 'dart fix --apply', 'npx prettier --write src',
        'npx eslint --fix src', 'semgrep scan --autofix', 'vendor/bin/pint --dirty',
        'php vendor/bin/pint', 'gofmt -w .', 'black src', 'ruff format src',
        'php artisan migrate', 'php artisan db:seed', 'php artisan make:model X',
        "docker exec app-1 sh -c 'cd /app && php artisan migrate:fresh'",
        'docker compose down', 'docker rm app-1', "bash -c 'rm -rf x'", 'eval "rm x"',
        'find . -name "*.log" -delete', 'find . -name "*.log" -exec rm {} \\;',
        'ls | xargs rm', 'ls | xargs -I{} mv {} /x', 'echo "$(rm x)"', 'echo `git push`',
        'env FOO=1 rm x', 'timeout 5 git push', 'nice -n 10 npm install',
        'curl -O https://ejemplo.mx/a.zip', 'curl -X POST https://ejemplo.mx/api',
        'curl -d a=1 https://ejemplo.mx', 'wget https://ejemplo.mx/a.zip',
        'psql -c "delete from users"', 'mysql -e "DROP TABLE x"', 'kill 123',
        'systemctl --user restart elyares-engineer', 'echo x > $SALIDA', 'echo x > ~/x',
        # operación: nada que llegue a un servidor ni cambie su estado
        "ssh ionos 'cd ~/subdomains/x && make update'", "ssh YaresPi 'docker ps'",
        'scp a.sql host:/tmp/', 'sftp host', 'make update', 'make', 'make test deploy',
        'make -C api migrate_force', 'gh pr merge 12 --squash', 'gh workflow run ci.yml',
        'gh secret set X', 'gh api -X DELETE repos/a/b', 'gh api -XPOST repos/a/b/dispatches',
        'gh api repos/a/b/issues -f title=x', 'gh release create v1', 'gh run rerun 1',
        'gh pr checkout 12', 'gh auth token', 'kubectl apply -f x.yaml', 'kubectl delete pod x',
        'terraform apply', 'terraform destroy', 'helm upgrade x ./chart',
        'supervisorctl restart starter_worker:*', 'crontab -e', 'crontab nuevo.txt',
        'certbot renew', 'nginx -s reload', 'caddy reload', 'ansible-playbook site.yml',
        'ufw allow 80',
        'git clone https://github.com/a/b.git', 'git clone https://github.com/a/b.git vendor/b',
        'git clone --depth 1 https://github.com/a/b.git ~/develop/b',
        # de vaultdocs solo `project --write`; el resto escribe dentro de los repos
        'vaultdocs vault --write', 'vaultdocs index --write', 'vaultdocs claude --write',
        # el sed de la bitácora, y nada que se le parezca
        "sed -i '/<!-- BITACORA:INSERT -->/r /tmp/entrada.md' '/v/10 Projects/homelab/homelab - Estado.md'",
        "sed -i '/<!-- BITACORA:INSERT -->/r entrada.md' '/v/10 Projects/homelab/Bitacora/2026-10.md'",
        "sed -i '/<!-- BITACORA:INSERT -->/d' '/v/10 Projects/homelab/Bitacora/2026-10.md'",
        "sed -i '/<!-- BITACORA:INSERT -->/r '\"$ENTRADA\" \"$BITACORA\"",
        "sed -i -e '/<!-- BITACORA:INSERT -->/r /tmp/e.md' -e 's/a/b/' '/v/Bitacora/2026-10.md'",
        # salir de /tmp con `..` no es estar en /tmp
        'echo x > /tmp/../home/elyares/x', 'cp a.txt /tmp/../etc/x', 'touch /tmp/a/../../b',
    ]

    def test_lo_que_lee_pasa(self):
        for command in self.PASA:
            with self.subTest(command):
                self.assertIsNone(guard.check(command))

    def test_lo_que_escribe_se_frena(self):
        for command in self.FRENA:
            with self.subTest(command):
                self.assertIsNotNone(guard.check(command))

    def test_unas_comillas_sin_cerrar_se_revisan_a_lo_bruto(self):
        self.assertIsNotNone(guard.check("echo 'abierta && rm -rf x"))
        self.assertIsNotNone(guard.check('echo "abierta > salida.txt'))
        self.assertIsNone(guard.check("echo 'abierta | wc -l"))
        self.assertIsNone(guard.check('echo "abierta 2>/dev/null >> /tmp/x'))

    def test_la_carpeta_de_trabajo_de_la_sesion_cuenta_como_tmp(self):
        code, err = run('solo-lectura', {'tool_input': {'command': 'echo x > /s/pad/nota.txt'},
                                         'scratchpad_dir': '/s/pad'})
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(run('solo-lectura', {'tool_input': {'command': 'echo x > /s/otro'},
                                              'scratchpad_dir': '/s/pad'})[0], 2)


def run(mode, payload):
    """(código de salida, lo que salió por stderr) de una llamada al hook."""
    out, err = io.StringIO(), io.StringIO()
    code = guard.main([mode], io.StringIO(json.dumps(payload)), out, err)
    return code, err.getvalue() or out.getvalue()


class Hook(unittest.TestCase):
    def test_frenar_es_salir_con_2_y_decir_por_que(self):
        code, said = run('solo-lectura', {'tool_input': {'command': 'git push'}})
        self.assertEqual(code, 2)
        self.assertIn('`git push`', said)

    def test_el_devops_ademas_entrega(self):
        for command in ('git add elyares/app.py tests/test_island.py', 'git commit -F /tmp/commit-msg-1.txt',
                        'git commit -m "feat: x"', 'git push', 'git push -u origin feat/x', 'git fetch origin',
                        'git switch -c feat/x', 'git checkout -b feat/x v2',
                        'gh pr create --base v2 --title x --body-file /tmp/pr-body.md',
                        'gh pr edit 12 --title x', 'git status && git diff --stat', 'make test',
                        # con la cuenta que ve el repositorio, sin cambiar la de la máquina
                        'GH_TOKEN=$(gh auth token --user ElYares) gh pr create --base main --title x',
                        'GH_TOKEN=$(gh auth token --user ElYares) gh repo view ElYares/x --json name'):
            self.assertEqual(run('entrega', {'tool_input': {'command': command}}), (0, ''), command)
        for command in ('git add -A', 'git add .', 'git commit --amend', 'git commit -m x --no-verify',
                        'git commit -am x', 'git push --force', 'git push -f origin feat/x',
                        'git push --force-with-lease', 'git push origin :feat/x', 'git push origin +feat/x',
                        'git push --delete origin feat/x', 'git reset --hard', 'git checkout -- .',
                        'git checkout main', 'git rebase v2', 'git merge v2', 'git clean -fd', 'git stash',
                        'gh pr merge 12', 'gh pr close 12', 'gh auth switch --user ElYares', 'gh auth logout', 'gh release create v3', 'rm -rf build',
                        'ssh prod', 'make deploy', 'npm install', "bash -c 'git push --force'"):
            code, said = run('entrega', {'tool_input': {'command': command}})
            self.assertEqual(code, 2, command)
            self.assertIn('lee y entrega', said)
        # Lo de entregar sigue frenado para los que solo leen.
        self.assertEqual(run('solo-lectura', {'tool_input': {'command': 'git commit -m x'}})[0], 2)
        self.assertEqual(run('solo-lectura', {'tool_input': {'command': 'gh pr create'}})[0], 2)

    def test_lo_que_no_entiende_lo_deja_pasar(self):
        self.assertEqual(guard.main(['solo-lectura'], io.StringIO('no es json')), 0)
        self.assertEqual(run('solo-lectura', {})[0], 0)
        self.assertEqual(run('otro-modo', {'tool_input': {'command': 'rm x'}}), (0, ''))

    def test_el_architect_solo_escribe_documentacion(self):
        for path in ('/x/docs/ARQUITECTURA.md', '/x/docs/adr/0001.md', '/x/diagrama.mmd'):
            self.assertEqual(run('solo-docs', {'tool_input': {'file_path': path}}), (0, ''))
        for path in ('/x/app/Models/User.php', '/x/phpstan.neon', '/x/package.json', '/x/Makefile'):
            code, said = run('solo-docs', {'tool_input': {'file_path': path}})
            self.assertEqual(code, 2)
            self.assertIn(os.path.basename(path), said)


class Configuracion(unittest.TestCase):
    def ask(self, path):
        code, said = run('config', {'tool_input': {'file_path': path}})
        self.assertEqual(code, 0)
        return bool(said) and json.loads(said)['hookSpecificOutput']['permissionDecision'] == 'ask'

    def test_pregunta_antes_de_tocar_lo_que_revisa_el_codigo(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, '.github/workflows'))
            for name in ('phpstan.neon', 'phpstan-baseline.neon', 'pint.json', 'phpunit.xml',
                         'analysis_options.yaml', '.eslintrc.js', 'eslint.config.mjs',
                         '.prettierrc', '.eslintignore', '.golangci.yml', '.github/workflows/ci.yml'):
                path = os.path.join(d, name)
                open(path, 'w').close()
                with self.subTest(name):
                    self.assertTrue(self.ask(path))

    def test_crearla_o_tocar_otra_cosa_no_pregunta(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(self.ask(os.path.join(d, 'phpstan.neon')))      # aún no existe
            for name in ('composer.json', 'tsconfig.json', 'app.php', 'README.md'):
                path = os.path.join(d, name)
                open(path, 'w').close()
                with self.subTest(name):
                    self.assertFalse(self.ask(path))


if __name__ == '__main__':
    unittest.main()
