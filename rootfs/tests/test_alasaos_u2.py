import importlib.util
import ast
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock, skipUnless

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('aos_u2',ROOT/'rootfs/overlays/alasaos_u2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class OptionalU2Tests(TestCase):
    def test_exists_preserves_query_failures(self):
        selector=m.BridgeU2().xpath('//*')
        for error in (ConnectionError('bridge unavailable'), TimeoutError('bridge timeout'),
                      RuntimeError('UI automation already registered'), ValueError('invalid query')):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(selector,'_nodes',side_effect=error):
                    with self.assertRaises(type(error)) as raised:
                        _=selector.exists
                    self.assertIs(raised.exception,error)

    def test_bridge_optional_construction_does_not_open_adb(self):
        connect=mock.Mock(return_value='real-device')
        u2=SimpleNamespace(connect=connect)
        with mock.patch.dict('sys.modules',{'uiautomator2':u2}):
            m.install()
            bridge=u2.connect('alasaos')
            bridge.wait_timeout=10
            connect.assert_not_called()
            self.assertIsInstance(bridge,m.BridgeU2)
            m.install()  # Repeated bootstrap must not stack wrappers.
            self.assertEqual(u2.connect('real-serial'),'real-device')
            connect.assert_called_once_with('real-serial')


class ConnectionTests(TestCase):
    def setUp(self):
        source=ROOT/'rootfs/patches/module/device/connection.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Connection')
        self.functions={}
        for name in ('adb_push','restart_atx','adb_shell'):
            node=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name==name)
            node.decorator_list=[]
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),
                 {'logger':mock.Mock(),'ScriptError':RuntimeError},self.functions)
        self.device=SimpleNamespace(serial='alasaos',alasaos_shell_output=mock.Mock(return_value='done'),
                                    adb_command=mock.Mock(),adb_shell=mock.Mock())

    def test_shell_existing_directory_returns_output_like_adb(self):
        self.device.alasaos_shell=mock.Mock(return_value={
            'ok':False,'code':1,'stdout':'','stderr':'mkdir: File exists\n'})
        output=self.functions['adb_shell'](self.device,'mkdir /sdcard/Documents')
        self.assertEqual(output,'mkdir: File exists')

    def test_shell_missing_file_is_not_a_transport_failure(self):
        self.device.alasaos_shell=mock.Mock(return_value={
            'ok':False,'code':1,'stdout':'','stderr':'rm: No such file\n'})
        output=self.functions['adb_shell'](self.device,'rm missing.txt',stream=True)
        self.assertEqual(output,b'rm: No such file\n')

    def test_shell_timeout_remains_an_error(self):
        self.device.alasaos_shell=mock.Mock(return_value={'ok':False,'error':'shell timeout 10s'})
        with self.assertRaisesRegex(RuntimeError,'shell timeout'):
            self.functions['adb_shell'](self.device,'sleep 100')

    def test_shell_preserves_requested_whitespace(self):
        self.device.alasaos_shell=mock.Mock(return_value={'ok':True,'code':0,'stdout':'line\n','stderr':''})
        self.assertEqual(self.functions['adb_shell'](self.device,['echo','line'],rstrip=False),'line\n')
        self.device.alasaos_shell.assert_called_once_with('echo line',timeout=10)

    def test_file_push_uses_bounded_bridge_chunks_and_quotes_path(self):
        content=bytes(range(256))*200
        with mock.patch('builtins.open',mock.mock_open(read_data=content)):
            self.functions['adb_push'](self.device,'sample.txt',"/sdcard/Documents/test ' quoted.txt")
        commands=[call[0][0] for call in self.device.alasaos_shell_output.call_args_list]
        chunks=[command.split()[2] for command in commands if command.startswith('printf')]
        self.assertEqual(b''.join(base64.b64decode(chunk) for chunk in chunks),content)
        self.assertTrue(all(len(command)<65536 for command in commands))
        self.assertTrue(commands[-2].startswith('mv -f '))
        self.assertTrue(commands[-1].startswith('rm -f '))
        self.device.adb_command.assert_not_called()

    def test_failed_file_push_keeps_destination_and_removes_partial(self):
        self.device.alasaos_shell_output.side_effect=['',RuntimeError('failed'),'']
        with mock.patch('builtins.open',mock.mock_open(read_data=b'content')):
            with self.assertRaisesRegex(RuntimeError,'failed'):
                self.functions['adb_push'](self.device,'sample.txt','/sdcard/Documents/sample.txt')
        commands=[call[0][0] for call in self.device.alasaos_shell_output.call_args_list]
        self.assertFalse(any(command.startswith('mv ') for command in commands))
        self.assertTrue(commands[-1].startswith('rm -f '))

    def test_restart_atx_does_not_start_an_agent_for_aos(self):
        self.functions['restart_atx'](self.device)
        self.device.adb_shell.assert_not_called()

    def test_normal_push_and_restart_keep_the_original_transport(self):
        self.device.serial='real-device'
        self.functions['adb_push'](self.device,'sample.txt','/sdcard/sample.txt')
        self.device.adb_command.assert_called_once_with(['push','sample.txt','/sdcard/sample.txt'])
        self.functions['restart_atx'](self.device)
        self.assertEqual(self.device.adb_shell.call_count,2)


@skipUnless(importlib.util.find_spec('lxml'), 'Selector tests require the ALAS lxml dependency')
class SelectorTests(TestCase):
    XML = '''<hierarchy><node class="android.widget.LinearLayout" resource-id="com.example.app:id/toolbar"
             display-id="2" window-id="7" node-path="0">
             <node class="android.widget.ImageView" text="first" display-id="2" window-id="7" node-path="0/0"/>
             <node class="android.widget.ImageView" text="执行" display-id="2" window-id="7" node-path="0/1"/>
             </node><node class="android.widget.EditText" resource-id="com.example.app:id/file" text="old"
             display-id="0" window-id="9" node-path="1"/></hierarchy>'''

    def setUp(self):
        self.device=m.BridgeU2()
        self.device.dump_hierarchy=mock.Mock(return_value=self.XML)
        self.device._call=mock.Mock(return_value={'ok':True})

    def test_class_xpath_uses_last_child_and_its_display(self):
        self.device.xpath('//*[@resource-id="com.example.app:id/toolbar"]/android.widget.ImageView[last()]').click()
        self.device._call.assert_called_once_with(method='ui',action='click',display_id=2,window_id=7,
                                                 node_path='0/1',resource_id='',class_name='android.widget.ImageView',text='执行')

    def test_resource_selector_replaces_unicode_text(self):
        selector=self.device(resourceId='com.example.app:id/file')
        self.assertTrue(selector.exists)
        selector.send_keys('/sdcard/Documents/测试.txt')
        self.assertEqual(self.device._call.call_args[1]['value'],'/sdcard/Documents/测试.txt')
        self.assertEqual(self.device._call.call_args[1]['display_id'],0)
        self.assertEqual(self.device._call.call_args[1]['action'],'set_text')

    def test_exists_does_not_wait_and_missing_click_times_out(self):
        selector=self.device.xpath('//*[contains(@text,"missing")]')
        self.assertFalse(selector.exists)
        with self.assertRaisesRegex(RuntimeError,'selector not found'):
            selector.click(timeout=0)
        self.device._call.assert_not_called()

    def test_click_requeries_instead_of_using_exists_snapshot(self):
        selector=self.device(resourceId='com.example.app:id/file')
        self.assertTrue(selector.exists)
        self.device.dump_hierarchy.return_value='<hierarchy/>'
        with self.assertRaisesRegex(RuntimeError,'selector not found'):
            selector.click(timeout=0)
        self.device._call.assert_not_called()

    def test_unsupported_selector_fails_explicitly(self):
        with self.assertRaises(NotImplementedError):
            self.device(resourceIdMatches='.*')

    def test_multiple_launchers_avoid_resolver(self):
        self.device._shell=mock.Mock(side_effect=[
            'android/com.android.internal.app.ResolverActivity\n',
            'com.example.app/.MainActivity\ncom.example.app/.ActivityMain\n','Starting: Intent'])
        self.device.app_start('com.example.app')
        self.assertEqual(self.device._shell.call_args[0][0],'am start --user current -n com.example.app/.MainActivity')

    def test_reset_uses_bridge(self):
        self.device.reset_uiautomator()
        self.device._call.assert_called_once_with(method='ui',action='reset')

    def test_malformed_hierarchy_and_xpath_are_reported(self):
        from lxml import etree
        self.device.dump_hierarchy.return_value='<hierarchy'
        with self.assertRaises(etree.XMLSyntaxError):
            _=self.device(text='missing').exists
        self.device.dump_hierarchy.return_value=self.XML
        with self.assertRaises(etree.XPathError):
            _=self.device.xpath('//*[').exists
