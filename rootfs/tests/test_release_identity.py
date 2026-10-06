"""Release artifacts must retain the installed certificate and readable version."""
import importlib.util
import base64
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('release_identity', ROOT / 'app/scripts/release_identity.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


class ReleaseIdentityTests(unittest.TestCase):
    def setUp(self):
        self.sha = hashlib.sha256(b'test certificate').hexdigest()
        self.expected = {'app.signingCertificateSha256': self.sha,
                         'app.versionName': '0.1.6', 'app.versionCode': '103'}
        self.certificate = self.pem(b'test certificate')
        self.badging = "package: name='com.dreamry2c.alasaos' versionCode='103' versionName='0.1.6' platformBuildVersionName='16'\n"

    @staticmethod
    def pem(data):
        return '-----BEGIN CERTIFICATE-----\n' + base64.b64encode(data).decode() + '\n-----END CERTIFICATE-----\n'

    def test_matching_apk_identity(self):
        result = identity.verify_identity(self.certificate, self.badging, self.expected)
        self.assertEqual(result['versionName'], '0.1.6')
        self.assertEqual(result['versionCode'], 103)
        self.assertEqual(result['certificateSha256'], self.sha)

    def test_rejects_different_or_missing_signing_certificate(self):
        for output in ('', self.pem(b'different certificate')):
            with self.subTest(output=bool(output)), self.assertRaisesRegex(ValueError, 'signing certificate'):
                identity.verify_identity(output, self.badging, self.expected)

    def test_rejects_additional_signer_even_if_one_matches(self):
        output = self.certificate + self.pem(b'different certificate')
        with self.assertRaisesRegex(ValueError, 'signing certificate'):
            identity.verify_identity(output, self.badging, self.expected)

    def test_sdk_range_labels_and_repeated_same_certificate(self):
        output = ('Signer (minSdkVersion=33, maxSdkVersion=2147483647) certificate PEM:\n' + self.certificate
                  + 'Signer (minSdkVersion=28, maxSdkVersion=32) certificate PEM:\n' + self.certificate)
        self.assertEqual(identity.verify_identity(output, self.badging, self.expected)['certificateSha256'], self.sha)

    def test_rejects_hash_version_and_old_version_code(self):
        for output in (self.badging.replace("'0.1.6'", "'dfb351a'"), self.badging.replace("'103'", "'102'")):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'APK version'):
                identity.verify_identity(self.certificate, output, self.expected)

    def test_missing_secrets_fail_before_creating_key_file(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'Missing release signing'):
            identity.prepare()


if __name__ == '__main__':
    unittest.main()
