"""Offline updater regressions using real Git repos (GPT-6 Astra, 2026-10-01).

Run with Python unittest; on Windows set ALASAOS_TEST_BASH to Git Bash.
All test files live under the project .tmp directory. No remote network is used.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEEDS = ROOT / 'rootfs/seeds'


def shell_path(path):
    s = str(path).replace('\\', '/')
    return '/' + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ':' else s


class UpdateTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / '.tmp/updater-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.origin = self.root / 'origin'
        self.alas = self.root / 'alas'
        self.bin = self.root / 'bin'
        for p in (self.origin, self.alas, self.bin):
            p.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1',
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
                        ALASAOS_UPDATE_NO_CDN='1', ALASAOS_UPDATE_TIMEOUT='5',
                        ALASAOS_ALAS_ROOT=shell_path(self.alas), PYTHONDONTWRITEBYTECODE='1')
        self.git(self.origin, 'init', '-q', '-b', 'master')
        self.git(self.origin, 'config', 'user.name', 'Updater Test')
        self.git(self.origin, 'config', 'user.email', 'updater@example.invalid')
        (self.origin / 'payload').write_text('one\n')
        self.git(self.origin, 'add', 'payload')
        self.git(self.origin, 'commit', '-qm', 'fixture')
        self.sha = self.git(self.origin, 'rev-parse', 'HEAD')
        self.git(self.origin, 'branch', 'zenko')
        (self.alas / 'seeds').mkdir()
        (self.alas / 'config').mkdir()
        for name in ['alasaos_update.sh', 'sync_deploy.py', 'update_progress.py']:
            (self.alas / 'seeds' / name).write_bytes((SEEDS / name).read_bytes().replace(b'\r\n', b'\n'))
        (self.alas / 'config/deploy.yaml').write_text('Deploy:\n  Git:\n    Repository: old\n    Branch: master\n  Update:\n    EnableReload: true\n')
        # Deterministic faults, real git for everything else. No private credentials.
        real_git = shell_path(shutil.which('git'))
        (self.bin / 'git').write_text(
            '#!/bin/bash\n'
            'if [[ "$1" == ls-remote && -n "${FAIL_PROBE:-}" ]]; then exit 1; fi\n'
            'if [[ "$1" == fetch && -n "${FAIL_FETCH:-}" ]]; then echo "fatal: test failure" >&2; exit 1; fi\n'
            f'exec "{real_git}" "$@"\n', newline='\n')
        # Native Windows Python cannot execute the extensionless Git Bash fault stub.
        # Keep the real progress wrapper, but run its child through Bash on Windows.
        progress_child = (
            'if [[ "$1" == seeds/update_progress.py ]]; then\n'
            '  shift 2\n'
            f'  exec "{shell_path(sys.executable)}" seeds/update_progress.py -- "$ALASAOS_TEST_BASH" "{shell_path(self.bin / "git")}" "${{@:2}}"\n'
            'fi\n'
        ) if os.name == 'nt' else ''
        (self.bin / 'python3').write_text(
            '#!/bin/bash\n' + progress_child + f'exec "{shell_path(sys.executable)}" "$@"\n', newline='\n')
        for p in self.bin.iterdir():
            p.chmod(0o755)

    def git(self, cwd, *args):
        p = subprocess.run(['git', '-C', str(cwd), *args], env=self.env,
                           text=True, capture_output=True, timeout=15)
        if p.returncode:
            raise AssertionError(p.stderr)
        return p.stdout.strip()

    def update(self, source=None, branch='zenko', **env):
        bash = os.environ.get('ALASAOS_TEST_BASH', shutil.which('bash') or '/bin/bash')
        script = f'export PATH="{shell_path(self.bin)}:$PATH"; exec /bin/bash "$1" "$2" "$3"'
        return subprocess.run([bash, '-c', script, 'updater-test', shell_path(self.alas / 'seeds/alasaos_update.sh'),
                               source or shell_path(self.origin), branch], env=dict(self.env, **env),
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=25)

    def test_first_install_matching_manifest_still_populates_git(self):
        (self.alas / 'BUILD_MANIFEST').write_text('{"alas_commit": "' + self.sha + '"}')
        p = self.update()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.git(self.alas, 'rev-parse', '--verify', 'HEAD'), self.sha)
        self.assertTrue((self.alas / 'payload').exists())

    def test_second_start_keeps_upstream_history(self):
        self.assertEqual(self.update().returncode, 0)
        self.assertEqual(self.update().returncode, 0)
        self.assertEqual(self.git(self.alas, 'rev-parse', '--verify', 'origin/zenko'), self.sha)

    def test_changed_branch_at_same_commit_checks_out_branch(self):
        self.assertEqual(self.update(branch='master').returncode, 0)
        self.assertEqual(self.update(branch='zenko').returncode, 0)
        self.assertEqual(self.git(self.alas, 'symbolic-ref', '--short', 'HEAD'), 'zenko')
        self.assertEqual(self.git(self.alas, 'rev-parse', '--verify', 'origin/zenko'), self.sha)

    def test_failed_new_source_backs_off_on_second_attempt(self):
        self.assertEqual(self.update(FAIL_PROBE='1', FAIL_FETCH='1').returncode, 1)
        p = self.update(FAIL_PROBE='1', FAIL_FETCH='1')
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn('backoff-until-tomorrow', p.stdout)
        p = self.update(branch='master')
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertNotIn('backoff-until-tomorrow', p.stdout)

    def test_probe_failure_falls_back_to_fetch(self):
        p = self.update(FAIL_PROBE='1')
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(self.git(self.alas, 'rev-parse', 'HEAD'), self.sha)

    def test_source_secret_not_written_to_log_or_marker(self):
        secret = 'FAKE_TEST_SECRET'
        p = self.update(source=f'https://test:{secret}@example.invalid/repo', FAIL_PROBE='1', FAIL_FETCH='1')
        self.assertNotIn(secret, p.stdout + p.stderr)
        marker = self.alas / '.alasaos_update_source'
        self.assertTrue(marker.exists())
        self.assertNotIn(secret, marker.read_text())

    def test_stale_commit_marker_does_not_skip_checkout(self):
        self.assertEqual(self.update().returncode, 0)
        (self.origin / 'payload').write_text('two\n')
        self.git(self.origin, 'commit', '-qam', 'second')
        new = self.git(self.origin, 'rev-parse', 'HEAD')
        self.git(self.origin, 'branch', '-f', 'zenko', new)
        (self.alas / '.alasaos_alas_commit').write_text(new)
        self.assertEqual(self.update().returncode, 0)
        self.assertEqual(self.git(self.alas, 'rev-parse', 'HEAD'), new)

    def test_env_fix_restores_retired_webui_overlay_from_current_fork(self):
        rel = 'module/webui/utils.py'
        source = self.origin / rel
        source.parent.mkdir(parents=True)
        source.write_text('class Icon:\n    STOP = "fork-stop"\n')
        self.git(self.origin, 'add', rel)
        self.git(self.origin, 'commit', '-qm', 'fork icon')
        self.git(self.origin, 'branch', '-f', 'zenko', 'HEAD')
        self.assertEqual(self.update().returncode, 0)
        (self.alas / rel).write_text('class Icon:\n    RUN = "old"\n')
        config_before = (self.alas / 'config/deploy.yaml').read_bytes()
        # Avoid importing/installing any host Python dependency in this test.
        (self.bin / 'python3').write_text('#!/bin/bash\necho 2.27.0\n', newline='\n')
        bash = os.environ.get('ALASAOS_TEST_BASH', shutil.which('bash') or '/bin/bash')
        p = subprocess.run([bash, '-c', f'export PATH="{shell_path(self.bin)}:$PATH"; exec /bin/bash "$1"',
                            'seed-test', shell_path(SEEDS / 'env_fix.sh')], env=self.env,
                           capture_output=True, text=True, timeout=25)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.alas / rel).read_bytes(), source.read_bytes())
        self.assertEqual((self.alas / 'config/deploy.yaml').read_bytes(), config_before)


if __name__ == '__main__':
    unittest.main()
