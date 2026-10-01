"""Shared ALAS ownership: UI mutations, logs and failures are visible to AOS."""
import ast
import os
import tempfile
import importlib.util
from pathlib import Path
from types import SimpleNamespace
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
