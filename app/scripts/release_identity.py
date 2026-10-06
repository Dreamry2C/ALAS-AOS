#!/usr/bin/env python3
"""Restore CI signing material and verify the public identity of a release APK."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def settings():
    return dict(line.strip().split('=', 1) for line in
                (ROOT / 'app/gradle.properties').read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.lstrip().startswith('#') and '=' in line)


def java_tool(name):
    home = os.environ.get('JAVA_HOME')
    return str(Path(home) / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))) if home else name


def prepare():
    required = ('KEYSTORE_BASE64', 'KEYSTORE_PATH', 'KEYSTORE_PASSWORD', 'KEY_ALIAS', 'KEY_PASSWORD')
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError('Missing release signing configuration: ' + ', '.join(missing))
    path = Path(os.environ['KEYSTORE_PATH']).resolve()
    if not path.is_relative_to(ROOT / '.tmp'):
        raise ValueError('CI signing material must stay in the project .tmp directory')
    if path.exists():
        raise ValueError('Refusing to overwrite existing signing material')
    data = base64.b64decode(os.environ['KEYSTORE_BASE64'], validate=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as output:
            output.write(data)
        path.chmod(0o600)
        result = subprocess.run([java_tool('keytool'), '-exportcert', '-keystore', str(path),
                                 '-storepass:env', 'KEYSTORE_PASSWORD', '-alias', os.environ['KEY_ALIAS']],
                                capture_output=True)
        if result.returncode:
            raise ValueError('Cannot read the configured signing certificate')
        digest = hashlib.sha256(result.stdout).hexdigest()
        if digest != settings()['app.signingCertificateSha256']:
            raise ValueError('Signing certificate does not match existing installations')
    except Exception:
        path.unlink(missing_ok=True)
        raise
    print('Release signing certificate verified: ' + digest)


def verify_identity(cert_output, badging, expected):
    certificates = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$',
                              cert_output, re.MULTILINE)
    if len(certificates) != 1 or certificates[0].lower() != expected['app.signingCertificateSha256']:
        raise ValueError('APK signing certificate does not match existing installations')
    package = re.search(r"^package: name='[^']+' versionCode='(\d+)' versionName='([^']+)'", badging, re.MULTILINE)
    if not package or package.group(1) != expected['app.versionCode'] or package.group(2) != expected['app.versionName']:
        raise ValueError('APK version does not match app/gradle.properties')
    return {'versionName': package.group(2), 'versionCode': int(package.group(1)),
            'certificateSha256': certificates[0].lower()}


def verify(apk):
    sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not sdk:
        raise ValueError('Set ANDROID_HOME or ANDROID_SDK_ROOT to verify the release APK')
    jars = list((Path(sdk) / 'build-tools').glob('*/lib/apksigner.jar'))
    if not jars:
        raise ValueError('Android SDK apksigner is unavailable')
    jar = max(jars, key=lambda p: tuple(map(int, re.findall(r'\d+', p.parent.parent.name))))
    result = subprocess.run([java_tool('java'), '-jar', str(jar), 'verify', '--print-certs', str(apk)],
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError('APK signature verification failed')
    aapt = jar.parent.parent / ('aapt.exe' if os.name == 'nt' else 'aapt')
    metadata = subprocess.run([str(aapt), 'dump', 'badging', str(apk)], capture_output=True, text=True)
    if metadata.returncode:
        raise ValueError('Cannot read APK version metadata')
    identity = verify_identity(result.stdout, metadata.stdout, settings())
    identity['apkBytes'] = apk.stat().st_size
    print(json.dumps(identity, indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            summary.write(f"Release **{identity['versionName']}** (code {identity['versionCode']}); "
                          f"certificate SHA-256: `{identity['certificateSha256']}`.\n\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify'))
    parser.add_argument('--apk', type=Path, default=ROOT / 'app/app/build/outputs/apk/release/app-release.apk')
    args = parser.parse_args()
    try:
        prepare() if args.action == 'prepare' else verify(args.apk)
    except ValueError as error:
        # Only bounded validation messages; raw keytool/apksigner diagnostics stay private.
        print('Release identity check failed: ' + str(error), file=sys.stderr)
        return 1
    except (OSError, KeyError):
        print('Release identity check failed; verify signing inputs and tool availability.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
