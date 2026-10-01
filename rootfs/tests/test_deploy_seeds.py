"""Runtime deploy reader / policy regressions, with no ALAS dependencies."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DeploySeedTests(unittest.TestCase):
    def test_policy_and_source_reader_preserve_user_settings_and_line_endings(self):
        base = ROOT / '.tmp/deploy-seed-tests'
        base.mkdir(parents=True, exist_ok=True)
        for newline in ['\n', '\r\n']:
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory(dir=base) as tmp:
                alas = Path(tmp)
                (alas / 'config').mkdir()
                deploy = alas / 'config/deploy.yaml'
                repo = 'https://test:FAKE_TEST_SECRET@example.invalid/repo'
                original = (f"# keep comment\nDeploy:\n  Git:\n    Repository: '{repo}' # keep inline\n"
                            '    Branch: cloud  # chosen branch\n'
                            '  Update:\n    EnableReload: false\n    CheckUpdateInterval: 0\n'
                            '  Webui:\n    WebuiPort: 22267\n    Password: retain-test-value\n')
                deploy.write_bytes(original.replace('\n', newline).encode())
                env = dict(os.environ, ALASAOS_ALAS_ROOT=str(alas), PYTHONDONTWRITEBYTECODE='1')
                policy = [sys.executable, str(ROOT / 'rootfs/seeds/seed_deploy.py')]
                reader = [sys.executable, str(ROOT / 'rootfs/seeds/sync_deploy.py'), '--read']
                p = subprocess.run(policy, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertNotIn('FAKE_TEST_SECRET', p.stdout + p.stderr)
                expected = original.replace('EnableReload: false', 'EnableReload: true')
                self.assertEqual(deploy.read_bytes(), expected.replace('\n', newline).encode())
                before = deploy.stat().st_mtime_ns
                p = subprocess.run(reader, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(p.stdout.splitlines(), [repo, 'cloud'])  # Private protocol, not a log.
                subprocess.run(policy, env=env, capture_output=True, check=True, timeout=10)
                self.assertEqual(deploy.stat().st_mtime_ns, before)
                self.assertEqual(deploy.read_bytes(), expected.replace('\n', newline).encode())

    def test_missing_deploy_is_not_created_and_reader_fails(self):
        base = ROOT / '.tmp/deploy-seed-tests'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            env = dict(os.environ, ALASAOS_ALAS_ROOT=tmp, PYTHONDONTWRITEBYTECODE='1')
            for script, args, code in [('seed_deploy.py', [], 0), ('sync_deploy.py', ['--read'], 2),
                                       ('sync_deploy.py', ['test-source', 'cloud'], 2)]:
                p = subprocess.run([sys.executable, str(ROOT / 'rootfs/seeds' / script), *args],
                                   env=env, capture_output=True, timeout=10)
                self.assertEqual(p.returncode, code)
            self.assertFalse((Path(tmp) / 'config/deploy.yaml').exists())


if __name__ == '__main__':
    unittest.main()
