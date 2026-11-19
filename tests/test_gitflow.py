"""El flujo de ramas: la cadena del CLAUDE.md, el padre y el abuelo, los pasos y las órdenes."""

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from elyares import gitflow

CHAIN = ['main', 'develop', 'v2', 'v2-<tema>']


def git(root, *args):
    subprocess.run(['git', '-C', root, '-c', 'user.name=t', '-c', 'user.email=t@t', *args], check=True,
                   capture_output=True)


def commit(root, name):
    with open(os.path.join(root, name), 'w') as f:
        f.write(name)
    git(root, 'add', name)
    git(root, 'commit', '-m', f'feat: {name}')


class Repo(unittest.TestCase):
    """Un repositorio de verdad con su remoto: main, v2 (un commit más que main) y v2-x (otro más)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.remote = os.path.join(self.tmp.name, 'remote.git')
        self.root = os.path.join(self.tmp.name, 'work')
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', self.remote], check=True)
        os.mkdir(self.root)
        subprocess.run(['git', 'init', '-q', '-b', 'main', self.root], check=True)
        git(self.root, 'remote', 'add', 'origin', self.remote)
        commit(self.root, 'a')
        git(self.root, 'push', '-q', '-u', 'origin', 'main')
        git(self.root, 'switch', '-q', '-c', 'v2')
        commit(self.root, 'b')
        git(self.root, 'push', '-q', '-u', 'origin', 'v2')
        git(self.root, 'switch', '-q', '-c', 'v2-x')
        commit(self.root, 'c')
        conf = os.path.join(self.tmp.name, 'conf')
        os.mkdir(conf)
        patch = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': conf})
        patch.start()
        self.addCleanup(patch.stop)


class Cadena(unittest.TestCase):
    def test_lee_la_cadena_con_cualquiera_de_las_dos_flechas_y_con_comillas_de_codigo(self):
        self.assertEqual(gitflow.parse_chain('`main` ← develop <- v2 ← v2-<tema>'), CHAIN)
        self.assertEqual(gitflow.parse_chain('solo una'), [])
        self.assertEqual(gitflow.parse_chain('main ← v2 ← v2-<tema>   (una nota que no es rama)'), ['main', 'v2', 'v2-<tema>'])

    def test_la_cadena_sale_de_la_linea_flujo_de_git_del_claude_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, 'CLAUDE.md'), 'w') as f:
                f.write('# x\n\nOtra cosa: a ← b\nFlujo de git: main ← develop ← v2 ← v2-<tema>\n')
            self.assertEqual(gitflow.declared_chain(tmp), CHAIN)
            self.assertEqual(gitflow.declared_chain(os.path.join(tmp, 'nada')), [])


class Remoto(unittest.TestCase):
    def test_el_dueno_y_el_repo_salen_de_cualquier_forma_de_url_incluido_un_alias_de_ssh(self):
        for url in ('git@github.com:ElYares/patio.git', 'git@github-personal:ElYares/patio.git',
                    'https://github.com/ElYares/patio.git', 'https://github.com/ElYares/patio', 'ssh://git@github.com/ElYares/patio.git'):
            with mock.patch.object(gitflow, '_git', return_value=url + '\n'):
                self.assertEqual(gitflow._slug('/x'), 'ElYares/patio', url)
        with mock.patch.object(gitflow, '_git', return_value='\n'):
            self.assertEqual(gitflow._slug('/x'), '')


class Padre(Repo):
    def test_una_rama_del_patron_tiene_a_v2_de_padre_y_pregunta_por_develop_que_no_existe(self):
        flow = gitflow.resolve(self.root, CHAIN)
        self.assertEqual((flow.branch, flow.parent, flow.grand, flow.ask), ('v2-x', 'v2', 'main', 'develop'))
        self.assertEqual(flow.options, ['v2', 'main'])

    def test_la_respuesta_a_la_pregunta_se_recuerda_y_develop_deja_de_preguntarse(self):
        gitflow.remember(self.root, 'develop', 'main')
        flow = gitflow.resolve(self.root, CHAIN)
        self.assertIsNone(flow.ask)
        self.assertEqual((flow.parent, flow.grand), ('v2', 'main'))

    def test_si_develop_existe_es_el_abuelo(self):
        git(self.root, 'push', '-q', 'origin', 'main:develop')
        git(self.root, 'fetch', '-q')
        flow = gitflow.resolve(self.root, CHAIN)
        self.assertEqual((flow.parent, flow.grand, flow.ask), ('v2', 'develop', None))

    def test_una_rama_fuera_del_patron_cuelga_de_la_mas_cercana(self):
        git(self.root, 'switch', '-q', '-c', 'feat/otra')
        flow = gitflow.resolve(self.root, CHAIN)
        self.assertEqual(flow.parent, 'v2')                  # nació de v2-x, que nació de v2

    def test_v2_tiene_a_main_de_padre_si_develop_no_existe_ni_esta_sustituida(self):
        git(self.root, 'switch', '-q', 'v2')
        flow = gitflow.resolve(self.root, CHAIN)
        self.assertEqual((flow.branch, flow.parent, flow.ask), ('v2', 'main', 'develop'))

    def test_sin_cadena_declarada_el_padre_es_la_rama_principal(self):
        flow = gitflow.resolve(self.root)
        self.assertEqual((flow.parent, flow.declared), ('main', False))


class Pasos(Repo):
    def keys(self, steps):
        return [(s.key, s.state) for s in steps]

    def setUp(self):
        super().setUp()
        gitflow.remember(self.root, 'develop', 'main')

    def test_sin_subir_el_pr_espera_y_con_cambios_sin_commitear_se_ofrece_pedir_el_commit(self):
        with open(os.path.join(self.root, 'sucio'), 'w') as f:
            f.write('x')
        flow = gitflow.resolve(self.root, CHAIN)
        with mock.patch.object(gitflow, 'account', return_value='yo'):
            steps = gitflow.status(self.root, flow)
        self.assertEqual(self.keys(steps)[:4], [('commit', 'todo'), ('push', 'todo'), ('pr', 'wait'), ('merge', 'wait')])
        self.assertEqual(steps[0].go, 'Sugerir mensaje')
        self.assertEqual(steps[1].go, 'Subir')

    def test_subida_la_rama_se_ofrece_el_pr_y_con_el_pr_abierto_el_merge(self):
        flow = gitflow.resolve(self.root, CHAIN)
        ok, said = gitflow.act(self.root, flow, 'push')
        self.assertTrue(ok, said)
        with mock.patch.object(gitflow, 'account', return_value='yo'), \
                mock.patch.object(gitflow, 'find_pr', return_value=None):
            steps = gitflow.status(self.root, flow)
            self.assertEqual(self.keys(steps)[1:4], [('push', 'done'), ('pr', 'todo'), ('merge', 'wait')])
            self.assertEqual(steps[2].go, 'Abrir PR')
        with mock.patch.object(gitflow, 'account', return_value='yo'), \
                mock.patch.object(gitflow, 'find_pr', return_value={'number': 7, 'state': 'OPEN', 'url': ''}):
            steps = gitflow.status(self.root, flow)
            self.assertEqual(self.keys(steps)[2:4], [('pr', 'done'), ('merge', 'todo')])
            self.assertEqual(steps[3].go, 'Mergear')

    def test_un_pr_viejo_ya_mergeado_no_cuenta_si_la_rama_tiene_commits_nuevos(self):
        flow = gitflow.resolve(self.root, CHAIN)
        gitflow.act(self.root, flow, 'push')
        old = {'number': 3, 'state': 'MERGED', 'url': ''}
        with mock.patch.object(gitflow, 'account', return_value='yo'), \
                mock.patch.object(gitflow, 'find_pr', return_value=old):
            steps = gitflow.status(self.root, flow)
        self.assertEqual(self.keys(steps)[2], ('pr', 'todo'))        # v2-x tiene un commit que v2 no

    def test_el_pr_se_abre_con_gh_contra_el_padre_y_lleva_la_firma_y_nunca_se_borra_la_rama(self):
        flow = gitflow.resolve(self.root, CHAIN)
        with mock.patch.object(gitflow, 'account', return_value='yo'), \
                mock.patch.object(gitflow.github, '_gh', return_value='https://github.com/x/y/pull/9\n') as gh:
            ok, said = gitflow.act(self.root, flow, 'pr')
        self.assertTrue(ok)
        args = gh.call_args.args
        self.assertEqual(args[1:3], ('pr', 'create'))
        self.assertEqual(args[args.index('--base') + 1], 'v2')
        self.assertEqual(args[args.index('--head') + 1], 'v2-x')
        self.assertIn(gitflow.SIGNATURE, args[args.index('--body') + 1])

    def test_el_merge_usa_merge_normal_y_nunca_delete_branch(self):
        flow = gitflow.resolve(self.root, CHAIN)
        calls = []

        def fake(acct, *args):
            calls.append(args)
            return 'ok'

        with mock.patch.object(gitflow, 'account', return_value='yo'), \
                mock.patch.object(gitflow, 'find_pr', return_value={'number': 7, 'state': 'OPEN', 'url': ''}), \
                mock.patch.object(gitflow.github, '_gh', side_effect=fake):
            ok, said = gitflow.act(self.root, flow, 'merge')
        self.assertTrue(ok, said)
        self.assertIn('--merge', calls[0])
        self.assertNotIn('--delete-branch', calls[0])

    def test_el_pr_del_padre_al_abuelo_viejo_ya_mergeado_no_cuenta_si_el_padre_tiene_commits_nuevos(self):
        flow = gitflow.resolve(self.root, CHAIN)
        gitflow.act(self.root, flow, 'push')
        old = {'number': 117, 'state': 'MERGED', 'url': ''}
        with mock.patch.object(gitflow, 'account', return_value='yo'), \
                mock.patch.object(gitflow, 'find_pr', return_value=old):
            steps = {s.key: s for s in gitflow.status(self.root, flow)}
        self.assertEqual((steps['gpr'].state, steps['gpr'].go), ('todo', 'Abrir PR'))   # v2 tiene un commit que main no
        self.assertIn('por subir', steps['gpr'].note)
        self.assertEqual(steps['gmerge'].state, 'wait')

    def test_con_varios_commits_el_titulo_del_pr_es_la_rama_y_con_uno_su_asunto(self):
        commit(self.root, 'd')
        title, body = gitflow._title_and_body(self.root, 'v2', 'v2-x')
        self.assertEqual(title, 'v2-x → v2 (2 commits)')           # no el asunto del primero, que no resume a los demás
        self.assertIn('- feat: c', body)
        self.assertIn(gitflow.SIGNATURE, body)
        git(self.root, 'reset', '-q', '--hard', 'HEAD~1')
        self.assertEqual(gitflow._title_and_body(self.root, 'v2', 'v2-x')[0], 'feat: c')

    def test_tras_el_merge_la_rama_destino_local_se_pone_al_dia_si_avanza_limpio(self):
        flow = gitflow.resolve(self.root, CHAIN)
        other = os.path.join(self.tmp.name, 'otro')
        subprocess.run(['git', 'clone', '-q', self.remote, other], check=True)
        git(other, 'switch', '-q', 'v2')
        commit(other, 'merge-simulado')
        git(other, 'push', '-q', 'origin', 'v2')                    # lo que haría GitHub al mergear
        before = gitflow._git(self.root, 'rev-parse', 'v2').strip()
        with mock.patch.object(gitflow, 'account', return_value='yo'), \
                mock.patch.object(gitflow, 'find_pr', return_value={'number': 7, 'state': 'OPEN', 'url': ''}), \
                mock.patch.object(gitflow.github, '_gh', return_value='ok'):
            self.assertTrue(gitflow.act(self.root, flow, 'merge')[0])
        self.assertNotEqual(gitflow._git(self.root, 'rev-parse', 'v2').strip(), before)
        self.assertEqual(gitflow.current_branch(self.root), 'v2-x')   # y sin cambiar de rama a quien trabaja

    def test_sin_pr_abierto_no_se_mergea_y_sin_cuenta_de_gh_se_dice(self):
        flow = gitflow.resolve(self.root, CHAIN)
        with mock.patch.object(gitflow, 'account', return_value='yo'), mock.patch.object(gitflow, 'find_pr', return_value=None):
            self.assertFalse(gitflow.act(self.root, flow, 'merge')[0])
        with mock.patch.object(gitflow, 'account', return_value=''):
            self.assertIn('gh', gitflow.act(self.root, flow, 'pr')[1])

    def test_crear_la_rama_nace_del_padre_y_rechaza_nombres_raros(self):
        git(self.root, 'switch', '-q', 'v2')
        ok, said = gitflow.create_branch(self.root, 'v2-nueva', 'main')
        self.assertTrue(ok, said)
        self.assertEqual(gitflow.current_branch(self.root), 'v2-nueva')
        self.assertFalse(gitflow.create_branch(self.root, 'a b; rm -rf', 'main')[0])


if __name__ == '__main__':
    unittest.main()
