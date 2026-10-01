import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('aos_u2',ROOT/'rootfs/overlays/alasaos_u2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class OptionalU2Tests(TestCase):
    def test_bridge_optional_construction_does_not_open_adb(self):
        connect=mock.Mock(return_value='real-device')
        u2=SimpleNamespace(connect=connect)
        with mock.patch.dict('sys.modules',{'uiautomator2':u2}):
            m.install()
            bridge=u2.connect('alasaos')
            bridge.wait_timeout=10
            connect.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,'RPC is unavailable'):
                bridge.app_start('test.package')
            self.assertEqual(u2.connect('real-serial'),'real-device')
            connect.assert_called_once_with('real-serial')
