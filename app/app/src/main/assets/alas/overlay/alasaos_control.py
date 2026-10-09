"""Loopback adapter to the running ALAS WebUI's own ProcessManager.

No second scheduler, task process, retry policy or independent log selection.
Loaded by the AOS entrypoint; upstream files remain unchanged.
"""
import functools
import json
import io
from pathlib import Path
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class Control:
    def __init__(self, managers, state, console_factory):
        self.managers = managers
        self.state = state
        self.console_factory = console_factory
        self.last_config = 'alas'
        self.lock = threading.RLock()
        self.stop_event = lambda: None
        self._state_cache = {}

    def configs(self):
        from pathlib import Path
        return sorted(p.stem for p in Path('config').glob('*.json')
                      if not p.stem.startswith('template'))

    def current(self):
        running = self.managers.running_instances()
        if running:
            self.last_config = running[0].config_name
        return self.managers.get_manager(self.last_config)

    def delete_config(self, config):
        # Shared with native WebUI starts/stops: a running configuration cannot
        # disappear between the alive check and the atomic move.
        with self.lock:
            if (not config or '/' in config or '\\' in config or '\x00' in config
                    or config not in self.configs()):
                raise ValueError('unknown_configuration')
            path = Path('config') / (config + '.json')
            if path.is_symlink() or path.resolve().parent != Path('config').resolve():
                raise ValueError('unknown_configuration')
            instance = config.rsplit('.', 1)[0] if '.' in config else config
            if any(m.config_name in (config, instance) for m in self.managers.running_instances()):
                raise ValueError('configuration_running')
            remaining = [name for name in self.configs() if name != config]
            if not remaining:
                raise ValueError('last_configuration')
            # Keep a private recovery copy, outside the list of selectable JSONs.
            backup = Path('config/.alasaos-deleted') / uuid.uuid4().hex
            backup.mkdir(parents=True)
            path.rename(backup / path.name)
            if self.last_config in (config, instance):
                self.last_config = remaining[0]
            self._state_cache.pop(instance, None)
            return {'deleted': config}

    def logs(self, count=200):
        # Native run_process sets this instance's file logger before any imports.
        # Restrict selection to that instance; GUI diagnostics can never win.
        manager = self.current()
        pattern = re.compile(r'^\d{4}-\d{2}-\d{2}_' + re.escape(manager.config_name) + r'\.txt$')
        candidates = [p for p in Path('log').glob('*.txt') if pattern.fullmatch(p.name)]
        if not candidates:
            return ''
        path = max(candidates, key=lambda p: p.stat().st_mtime)
        with path.open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 256 * 1024))
            text = stream.read().decode('utf-8', errors='replace')
        return '\n'.join(text.splitlines()[-count:])

    def status(self):
        manager = self.current()
        alive = manager.alive
        latest = manager.renderables[-1] if manager.renderables else None
        key = (alive, id(latest), len(manager.renderables))
        cached = self._state_cache.get(manager.config_name)
        if cached is None or cached[0] != key:
            cached = (key, manager.state)
            self._state_cache[manager.config_name] = cached
        func = getattr(manager, '_alasaos_func', 'alas')
        tool = func in ('Daemon', 'EventStory')
        return dict(runner_alive=alive and not tool,
                    runner_wanted=alive and not tool, runner_respawns=0,
                    runner_state=cached[1],
                    pid=manager._process.pid if alive else None,
                    config=manager.config_name, gui_alive=True,
                    log_lines=len(manager.renderables), log_file=None,
                    tool_alive=alive and tool,
                    tool_name={'Daemon': 'daemon', 'EventStory': 'event_story'}.get(func),
                    tool_pid=manager._process.pid if alive and tool else None)

    def start(self, config, func=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', config) or config not in self.configs():
            raise ValueError('Unknown configuration')
        manager = self.managers.get_manager(config)
        manager.start(func=func, ev=self.stop_event())
        self.last_config = config
        return self.status()

    def stop(self):
        # AOS has a global stop button; use the same stop as WebUI stop-all.
        for manager in list(self.managers.running_instances()):
            manager.stop()
        return self.status()


def render_log(log, renderable):
    # Rich 15 capture consumes output before record/export_html sees it.
    # A private StringIO sink preserves recording through Rich's public API.
    from module.webui.utils import LOG_CODE_FORMAT
    previous = log.console.file
    try:
        log.console.file = io.StringIO()
        log.console.print(renderable)
        return log.console.export_html(theme=log.terminal_theme, clear=True,
                                       code_format=LOG_CODE_FORMAT, inline_styles=True)
    finally:
        log.console.file = previous


def install():
    from module.webui.setting import State
    from module.webui.process_manager import ProcessManager
    from rich.console import Console

    from module.webui.widgets import RichLog
    RichLog.render = render_log

    control = Control(ProcessManager, State, Console)
    def stop_event():
        from module.webui.app import updater
        return updater.event

    control.stop_event = stop_event
    original_start = ProcessManager.start
    original_stop = ProcessManager.stop

    @functools.wraps(original_start)
    def start(manager, func, *args, **kwargs):
        with control.lock:
            # Old browser sessions may still hold a manager after deletion.
            from module.config.utils import filepath_config
            from module.submodule.utils import get_config_mod
            if not Path(filepath_config(manager.config_name, get_config_mod(manager.config_name))).is_file():
                raise ValueError('Unknown configuration')
            if not manager.alive:
                manager._alasaos_func = func or 'alas'
                control.last_config = manager.config_name
            return original_start(manager, func, *args, **kwargs)

    @functools.wraps(original_stop)
    def stop(manager, *args, **kwargs):
        with control.lock:
            return original_stop(manager, *args, **kwargs)

    ProcessManager.start = start
    ProcessManager.stop = stop
    original_init = State.init
    original_clearup = State.clearup
    server = None

    def init(cls):
        nonlocal server
        original_init()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                url = urlparse(self.path)
                query = parse_qs(url.query)
                code = 200
                content_type = 'application/json; charset=utf-8'
                try:
                    with control.lock:
                        if self.command == 'GET' and url.path == '/status':
                            result = control.status()
                        elif self.command == 'GET' and url.path == '/configs':
                            result = {'configs': control.configs()}
                        elif self.command == 'POST' and url.path == '/configs/delete':
                            result = control.delete_config(query.get('config', [''])[0])
                        elif self.command == 'GET' and url.path == '/logs':
                            count = max(1, min(int(query.get('tail', ['200'])[0]), 2000))
                            result = control.logs(count)
                            content_type = 'text/plain; charset=utf-8'
                        elif self.command == 'POST' and url.path in ('/start', '/tool/start'):
                            func = None
                            if url.path == '/tool/start':
                                func = {'daemon': 'Daemon', 'event_story': 'EventStory'}.get(
                                    query.get('name', [''])[0])
                                if func is None:
                                    raise ValueError('Unknown tool')
                            result = control.start(query.get('config', ['alas'])[0], func)
                        elif self.command == 'POST' and url.path in ('/stop', '/tool/stop'):
                            result = control.stop()
                        else:
                            code, result = 404, {'error': 'not found'}
                except ValueError as exc:
                    code, result = 400, {'error': str(exc)}
                except Exception:
                    from module.logger import logger
                    logger.exception('AOS control request failed')
                    code, result = 503, {'error': 'ALAS control unavailable; see GUI diagnostic log'}
                body = (result if isinstance(result, str) else json.dumps(result)).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = handle_request

        server = ThreadingHTTPServer(('127.0.0.1', 22401), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def clearup(cls):
        nonlocal server
        if server is not None:
            server.shutdown()
            server.server_close()
            server = None
        original_clearup()

    State.init = classmethod(init)
    State.clearup = classmethod(clearup)
