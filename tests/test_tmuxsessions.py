import unittest
from unittest import mock

from elyares import tmuxsessions

PANES = '\n'.join([
    'api\t1\tedit\t%1\tnvim\t/p/api',
    'api\t2\tclaude\t%2\tclaude\t/p/api',
    'api\t2\tclaude\t%3\tbash\t/p/api',
    'web\t1\tedit\t%4\tbash\t/p/web',
    '_ssh-x\t1\tssh\t%5\tssh\t/',
])


class SnapshotTest(unittest.TestCase):
    def test_groups_panes_by_session_and_window(self):
        with mock.patch.object(tmuxsessions.actions, '_run', return_value=PANES):
            got = tmuxsessions.snapshot()
        self.assertEqual([s['name'] for s in got], ['api', 'web'])      # la oculta _ssh no cuenta
        self.assertEqual([w['name'] for w in got[0]['windows']], ['edit', 'claude'])
        self.assertEqual(len(got[0]['windows'][1]['panes']), 2)

    def test_no_server_is_empty(self):
        with mock.patch.object(tmuxsessions.actions, '_run', return_value=''):
            self.assertEqual(tmuxsessions.snapshot(), [])


class MergeTest(unittest.TestCase):
    def test_marks_the_most_urgent_claude(self):
        with mock.patch.object(tmuxsessions.actions, '_run', return_value=PANES):
            got = tmuxsessions.snapshot()
        tmuxsessions.merge(got, [('%2', 'working', ['auditor', 'reviewer']), ('%3', 'waiting', ['auditor'])])
        self.assertEqual(got[0]['windows'][1]['state'], 'waiting')
        self.assertEqual(got[0]['windows'][0]['state'], '')
        self.assertEqual(got[0]['windows'][1]['agents'], ['auditor', 'reviewer'])
        self.assertEqual((got[0]['state'], got[0]['claudes']), ('waiting', 2))
        self.assertEqual((got[1]['state'], got[1]['claudes']), ('', 0))


class JumpTest(unittest.TestCase):
    def test_switches_client_then_selects_window(self):
        calls = []
        with mock.patch.object(tmuxsessions.actions, '_run', side_effect=lambda *a, **k: calls.append(a) or ''), \
                mock.patch.object(tmuxsessions.actions, '_real_clients', return_value=[(5, '/dev/pts/1', 'web')]):
            tmuxsessions.jump('api', '2')
        self.assertIn(('tmux', 'switch-client', '-c', '/dev/pts/1', '-t', '=api'), calls)
        self.assertIn(('tmux', 'select-window', '-t', '=api:2'), calls)


if __name__ == '__main__':
    unittest.main()
