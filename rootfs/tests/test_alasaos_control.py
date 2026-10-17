"""Shared ALAS ownership: UI mutations, logs and failures are visible to AOS."""
import ast
import os
import tempfile
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('aos_control', ROOT/'rootfs/overlays/alasaos_control.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Capture:
    def __init__(self, console): self.console = console
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self): return ''.join(self.console.lines)

class Console:
    def __init__(self, **kwargs): self.lines = []
    def capture(self): return Capture(self)
    def print(self, item): self.lines.append(str(item)+'\n')

class NativeManager:
    def __init__(self, config):
        self.config_name=config; self.alive=False; self.state=2
        self.renderables=[]; self._process=None; self.starts=0
    def start(self, func=None, ev=None):
        if not self.alive:
            self.starts+=1; self.alive=True; self.state=1
            self._process=SimpleNamespace(pid=100+self.starts)
    def stop(self):
        self.alive=False; self.state=2; self.renderables.append('Manual stop')

class SharedControlTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.tmp/control-tests'; base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        previous=os.getcwd(); os.chdir(self.temp.name)
        self.addCleanup(os.chdir,previous)
        Path('log').mkdir()
        self.instances={}
        def get(name):
            return self.instances.setdefault(name, NativeManager(name))
        managers=SimpleNamespace(get_manager=get,
            running_instances=lambda: [m for m in self.instances.values() if m.alive])
        self.control=module.Control(managers, SimpleNamespace(), Console)
        self.control.configs=lambda: ['alas','other']
        self.native=get('alas')
    def test_native_start_and_stop_are_immediately_visible(self):
        self.native.start('alas')
        self.assertTrue(self.control.status()['runner_alive'])
        self.control.stop()
        self.assertFalse(self.native.alive)
        self.control.start('alas')
        self.native.stop()
        self.assertFalse(self.control.status()['runner_alive'])
    def test_repeated_aos_start_does_not_spawn_second_task(self):
        self.control.start('alas'); self.control.start('alas')
        self.assertEqual(self.native.starts,1)
    def test_task_error_remains_visible_without_automatic_restart(self):
        self.native.start('alas')
        self.native.alive=False; self.native.state=3
        self.native.renderables=['device failure']
        Path('log/2026-10-02_alas.txt').write_text('device failure\n')
        Path('log/2026-10-02_alasaos_gui.txt').write_text('Bind task wrong log\n')
        for _ in range(3):
            self.assertEqual(self.control.status()['runner_state'],3)
            self.assertFalse(self.control.status()['runner_wanted'])
            self.assertIn('device failure',self.control.logs())
            self.assertNotIn('Bind task',self.control.logs())
        self.assertEqual(self.native.starts,1)
    def test_ui_started_other_config_selects_its_native_log(self):
        other=self.control.managers.get_manager('other')
        other.renderables=['other task']; other.start()
        Path('log/2026-10-02_other.txt').write_text('other task\n')
        Path('log/2026-10-02_alas.txt').write_text('wrong instance\n')
        self.assertEqual(self.control.status()['config'],'other')
        self.assertEqual(self.control.logs(),'other task')
        other.stop()
        self.assertIn('other task',self.control.logs())
    def test_invalid_config_does_not_start(self):
        for config in ['../config','unknown']:
            with self.assertRaises(ValueError): self.control.start(config)
        self.assertEqual(self.native.starts,0)

    def prepare_configs(self):
        Path('config').mkdir()
        Path('config/alas.json').write_text('{"keep": true}')
        Path('config/other.json').write_text('{"test": true}')
        del self.control.configs

    def test_delete_moves_only_selected_config_and_changes_current(self):
        self.prepare_configs()
        self.control.last_config = 'other'
        self.control.delete_config('other')
        self.assertEqual(self.control.configs(), ['alas'])
        self.assertEqual(self.control.last_config, 'alas')
        saved = list(Path('config/.alasaos-deleted').glob('*/other.json'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(), '{"test": true}')
        self.assertEqual(Path('config/alas.json').read_text(), '{"keep": true}')

    def test_delete_rejects_running_and_last_config(self):
        self.prepare_configs()
        self.native.start()
        with self.assertRaisesRegex(ValueError, 'configuration_running'):
            self.control.delete_config('alas')
        self.assertTrue(Path('config/alas.json').is_file())
        self.control.delete_config('other')
        self.native.stop()
        with self.assertRaisesRegex(ValueError, 'last_configuration'):
            self.control.delete_config('alas')

    def test_double_json_and_broken_files_do_not_allow_deleting_last_usable_config(self):
        self.prepare_configs()
        Path('config/other.json').unlink()
        Path('config/qingao.json.json').write_text('{"Alas": {}}')
        Path('config/broken.json').write_text('{')
        Path('config/list.json').write_text('[]')
        mods = ModuleType('module.submodule.utils')
        mods.get_available_mod = lambda: {'maa', 'fpy'}
        mods.get_mod_dir = lambda name: {'maa': 'AlasMaaBridge', 'fpy': 'AlasFpyBridge'}.get(name)
        Path('config/only.maa.json').write_text('{}')  # No installed mod directory.
        with patch.dict(sys.modules, {'module.submodule.utils': mods}):
            with self.assertRaisesRegex(ValueError, 'last_configuration'):
                self.control.delete_config('alas')
        self.assertTrue(Path('config/alas.json').is_file())
        self.assertFalse(Path('config/.alasaos-deleted').exists())

    def test_delete_current_falls_back_to_usable_config_not_malformed_filename(self):
        self.prepare_configs()
        Path('config/a.json.json').write_text('{}')
        mods = ModuleType('module.submodule.utils')
        mods.get_available_mod = lambda: set()
        mods.get_mod_dir = lambda name: None
        self.control.last_config = 'other'
        with patch.dict(sys.modules, {'module.submodule.utils': mods}):
            self.control.delete_config('other')
        self.assertEqual(self.control.last_config, 'alas')

    def test_malformed_mod_sibling_does_not_count_as_a_usable_fallback(self):
        self.prepare_configs()
        Path('config/other.json.json').write_text('{}')
        mods = ModuleType('module.submodule.utils')
        mods.get_available_mod = lambda: set()
        mods.get_mod_dir = lambda name: None
        with patch.dict(sys.modules, {'module.submodule.utils': mods}):
            with self.assertRaisesRegex(ValueError, 'last_configuration'):
                self.control.delete_config('alas')
        self.assertTrue(Path('config/alas.json').is_file())

    def test_installed_known_mod_counts_as_a_usable_configuration(self):
        self.prepare_configs()
        Path('config/other.json').unlink()
        Path('config/bridge.maa.json').write_text('{}')
        Path('submodule/AlasMaaBridge').mkdir(parents=True)
        mods = ModuleType('module.submodule.utils')
        mods.get_available_mod = lambda: {'maa'}
        mods.get_mod_dir = lambda name: 'AlasMaaBridge'
        with patch.dict(sys.modules, {'module.submodule.utils': mods}):
            self.control.delete_config('alas')
        self.assertEqual(self.control.configs(), ['bridge.maa'])

    def test_delete_rejects_traversal_unknown_and_template(self):
        self.prepare_configs()
        Path('config/template.json').write_text('{}')
        for name in ('../other', '..\\other', 'missing', 'template', ''):
            with self.assertRaises(ValueError):
                self.control.delete_config(name)
        self.assertTrue(Path('config/other.json').is_file())
        self.assertFalse(Path('config/.alasaos-deleted').exists())

    def test_theme_control_and_status(self):
        recorded = []
        self.control.theme_setter = lambda t: recorded.append(t)
        self.assertEqual(self.control.set_theme('dark'), {'theme': 'dark'})
        self.assertEqual(recorded, ['dark'])
        self.assertEqual(self.control.set_theme('default'), {'theme': 'default'})
        self.assertEqual(recorded, ['dark', 'default'])
        with self.assertRaisesRegex(ValueError, 'Invalid theme'):
            self.control.set_theme('blue')
        self.control.state.theme = 'dark'
        self.assertEqual(self.control.status()['theme'], 'dark')

class ConfigWriterTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / '.tmp/control-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        previous = os.getcwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, previous)
        Path('config').mkdir()
        utils = ModuleType('module.config.utils')
        utils.filepath_config = lambda name, mod: str(Path('config') / (
            name + ('' if mod == 'alas' else '.' + mod) + '.json'))
        self.calls = []
        self.updater = type('ConfigUpdater', (), {'write_file': staticmethod(
            lambda name, data, mod='alas': self.calls.append((name, data, mod)))})
        config = ModuleType('module.config.config_updater')
        config.ConfigUpdater = self.updater
        self.modules = patch.dict(sys.modules, {'module.config.utils': utils,
            'module.config.config_updater': config})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        module.install_config_writer()

    def test_double_extension_new_name_and_import_are_canonicalized(self):
        self.updater.write_file('qingao.json.json', {'keep': True})
        # Importing qingao.json.txt makes upstream pass name=qingao, mod=json.
        self.updater.write_file('qingao', {'keep': True}, 'json')
        self.assertEqual(self.calls, [('qingao', {'keep': True}, 'alas'),
                                      ('qingao', {'keep': True}, 'alas')])

    def test_normal_names_mods_and_templates_keep_original_write_semantics(self):
        for name, mod in [('alas', 'alas'), ('中文配置', 'alas'), ('template', 'alas'),
                          ('other', 'maa'), ('other', 'fpy')]:
            self.updater.write_file(name, {}, mod)
        self.assertEqual([(name, mod) for name, _, mod in self.calls],
                         [('alas', 'alas'), ('中文配置', 'alas'), ('template', 'alas'),
                          ('other', 'maa'), ('other', 'fpy')])

    def test_canonicalization_never_overwrites_an_existing_configuration(self):
        Path('config/qingao.json').write_text('original')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.updater.write_file('qingao.json', {'different': True})
        self.assertEqual(Path('config/qingao.json').read_text(), 'original')
        self.assertEqual(self.calls, [])

    def test_invalid_target_never_reaches_the_writer(self):
        for name in ('', '.json', '../other', 'a.b', 'bad/name', '\x00'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.updater.write_file(name, {})
        self.assertEqual(self.calls, [])


class BridgeShellTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((ROOT/'rootfs/patches/module/device/connection.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Connection')
        func=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='adb_shell')
        func.decorator_list=[]
        scope={'remove_shell_warning':lambda v:v}
        exec(compile(ast.Module(body=[func],type_ignores=[]),'bridge-shell','exec'),scope)
        self.call=scope['adb_shell']; self.seen=[]
        def bridge(cmd, timeout): self.seen.append((cmd,timeout)); return 'aarch64\n'
        self.device=SimpleNamespace(serial='alasaos',alasaos_shell_output=bridge)
    def test_text_shell_uses_bridge_and_preserves_strip_contract(self):
        self.assertEqual(self.call(self.device,'uname -m'),'aarch64')
        self.assertEqual(self.call(self.device,'uname -m',rstrip=False),'aarch64\n')
        self.assertEqual(self.seen[0],('uname -m',10))
    def test_argument_quoting_and_completed_stream(self):
        self.assertEqual(self.call(self.device,['echo','a b'],stream=True),b'aarch64\n')
        self.assertEqual(self.seen[0][0],"echo 'a b'")
        with self.assertRaises(NotImplementedError): self.call(self.device,'x',stream=True,recvall=False)
    def test_non_bridge_device_retains_native_adb(self):
        self.device.serial='normal'
        self.device.adb=SimpleNamespace(shell=lambda *a,**k:'native')
        self.assertEqual(self.call(self.device,'uname -m'),'native')
        self.assertFalse(self.seen)

if __name__=='__main__': unittest.main()
