"""Runtime deploy migration regression tests, with no ALAS dependencies."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DeploySeedTests(unittest.TestCase):
    def test_policy_and_source_sync_preserve_user_settings_and_line_endings(self):
        base = ROOT / '.tmp/deploy-seed-tests'
        base.mkdir(parents=True, exist_ok=True)
        for newline in ['\n', '\r\n']:
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory(dir=base) as tmp:
                alas = Path(tmp)
                (alas / 'config').mkdir()
                deploy = alas / 'config/deploy.yaml'
                original = ('# keep comment\nDeploy:\n  Git:\n    Repository: old\n    Branch: master\n'
                            '  Update:\n    EnableReload: false\n    CheckUpdateInterval: 0\n'
                            '  Webui:\n    WebuiPort: 22267\n    Password: retain-test-value\n')
                deploy.write_bytes(original.replace('\n', newline).encode())
                env = dict(os.environ, ALASAOS_ALAS_ROOT=str(alas), PYTHONDONTWRITEBYTECODE='1')
                repo = 'https://test:FAKE_TEST_SECRET@example.invalid/repo'
                commands = [
                    [sys.executable, str(ROOT / 'rootfs/seeds/seed_deploy.py')],
                    [sys.executable, str(ROOT / 'rootfs/seeds/sync_deploy.py'), repo, 'zenko'],
                ]
                for command in commands:
                    p = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    self.assertNotIn('FAKE_TEST_SECRET', p.stdout + p.stderr)
                expected = original.replace('Repository: old', 'Repository: ' + repo).replace(
                    'Branch: master', 'Branch: zenko').replace('EnableReload: false', 'EnableReload: true')
                self.assertEqual(deploy.read_bytes(), expected.replace('\n', newline).encode())
                before = deploy.stat().st_mtime_ns
                for command in commands:
                    subprocess.run(command, env=env, capture_output=True, check=True, timeout=10)
                self.assertEqual(deploy.stat().st_mtime_ns, before)

    def test_missing_deploy_is_not_created(self):
        base = ROOT / '.tmp/deploy-seed-tests'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            env = dict(os.environ, ALASAOS_ALAS_ROOT=tmp, PYTHONDONTWRITEBYTECODE='1')
            for script, args in [('seed_deploy.py', []), ('sync_deploy.py', ['test-source', 'zenko'])]:
                p = subprocess.run([sys.executable, str(ROOT / 'rootfs/seeds' / script), *args],
                                   env=env, capture_output=True, timeout=10)
                self.assertEqual(p.returncode, 0)
            self.assertFalse((Path(tmp) / 'config/deploy.yaml').exists())


if __name__ == '__main__':
    unittest.main()
