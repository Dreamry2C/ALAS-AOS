#!/usr/bin/env python3
"""MaaAL v3 · ALAS 进程管理 wrapper（rootfs 内，stdlib only）。

薄 HTTP（127.0.0.1:22400）+ 进程组管理，供 App 悬浮窗 start/stop/日志 使用。
端口选择：避开 m0 桥 22300 与 WebUI 22267。

端点
----
GET  /status        → {"runner_alive": bool, "pid": int|null, "config": str|null,
                       "gui_alive": bool, "gui_pid": int|null,
                       "log_file": str|null, "log_lines": int}
POST /start?config=N → 幂等拉起 runner 子进程（已在跑则直接返回现状）；N = config/ 下的
                       实例配置名（默认 alas），runner.py argv[1] 透传
POST /stop          → 杀进程组：os.killpg(SIGTERM) → 3s → SIGKILL
GET  /logs?tail=N   → ./log/ 下最新 *.txt 的尾部 N 行（默认 200，上限 2000）
GET  /configs       → {"configs": [str]}：config/*.json 去掉 template* 的实例名列表，
                       'alas' 固定排最前；供 App 侧下拉选择运行配置

设计要点（依据 docs/spike-d-wrapper-surface.md 的 Spike D 结论）
----
- wrapper 本体**完全不 import ALAS**，只 subprocess 拉 runner.py（同目录）。
  runner 子进程 preexec_fn=os.setsid 独立进程组，停止用 os.killpg。
- **不碰 ALAS 的 ProcessManager**（双头管理风险：两边都以为自己在管进程，状态互踩）。
  WebUI（gui.py）由 wrapper 作子进程监管（崩溃自动重拉，退避 5s→60s），
  悬浮窗 start/stop 与 WebUI 启停按钮并存的双头问题留阶段四决策
  （候选：wrapper 同进程 uvicorn 直调 ProcessManager.get_manager()）。
  MAAAL_WEBUI=0 可关 WebUI（省内存/调试）。
- 停止语义等同 m0 的 ProcessManager.stop（其本身就是 kill()，无 graceful）：
  ALAS 无 SIGTERM handler，SIGTERM 即默认终止；3s 不死补 SIGKILL。
- 防孤儿（m0 教训）：① 父退出前 atexit + SIGTERM handler 清理 runner；
  ② stdin 管道破裂自尽——monitor 线程阻塞读 stdin，父进程（proot 启动器）死亡
  导致管道 EOF 时，杀掉 runner 进程组并退出。stdin 是 tty（手工调试）时不挂监控。
- 单实例锁：./log/wrapper.lock（fcntl.flock LOCK_EX|LOCK_NB，rootfs 是 Linux），
  锁不住说明已有 wrapper 在跑，直接退出码 2。
- 日志面：ALAS 写 ./log/{YYYY-MM-DD}_{config_name}.txt（module/logger.py:171-177），
  runner import 期另建 {date}_runner.txt；/logs 与 /status 按 mtime 取最新 *.txt，
  不猜文件名（append 打开、整天不换名，见 Spike D §3）。
"""
import atexit
import datetime
import fcntl
import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HOST = '127.0.0.1'
PORT = 22400

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER_PATH = os.path.join(BASE_DIR, 'runner.py')
LOG_DIR = os.path.join(BASE_DIR, 'log')
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
LOCK_PATH = os.path.join(LOG_DIR, 'wrapper.lock')
_STOP_GRACE_SEC = 3.0
# 实例名只许安全字符：它会拼进 runner argv 与日志文件名
_CONFIG_RE = re.compile(r'^[A-Za-z0-9_\-]+$')

_runner = None            # subprocess.Popen | None
_runner_lock = threading.Lock()
_runner_started_at = None  # float | None
_runner_config = None      # str | None：本次拉起跑的实例名，/status 汇报用

_gui = None                # subprocess.Popen | None
_gui_lock = threading.Lock()
_gui_started_at = None
_GUI_BACKOFF_INIT = 5.0    # 重拉退避：5s 起步翻倍，60s 封顶；活过 5 分钟复位
_GUI_BACKOFF_MAX = 60.0
_GUI_HEALTHY_UPTIME = 300.0
_closing = threading.Event()


# ---------------------------------------------------------------- runner 进程组管理

def _runner_alive():
    return _runner is not None and _runner.poll() is None


def start_runner(config_name='alas'):
    """幂等：已在跑直接返回现状（不发新配置）。返回 (alive, pid, started_now)。"""
    global _runner, _runner_started_at, _runner_config
    with _runner_lock:
        if _runner_alive():
            return True, _runner.pid, False
        _runner = subprocess.Popen(
            [sys.executable, RUNNER_PATH, config_name],
            cwd=BASE_DIR,
            preexec_fn=os.setsid,  # 独立进程组，停止走 os.killpg
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,  # ALAS 日志走 ./log/ 文件，不走管道
            stderr=subprocess.DEVNULL,
        )
        _runner_started_at = time.time()
        _runner_config = config_name
        return True, _runner.pid, True


def stop_runner():
    """SIGTERM → 3s → SIGKILL，杀整个进程组。返回 (was_alive, exit_code)。"""
    global _runner, _runner_config
    with _runner_lock:
        if not _runner_alive():
            return False, _runner.returncode if _runner else None
        pgid = os.getpgid(_runner.pid)
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.time() + _STOP_GRACE_SEC
        while time.time() < deadline and _runner.poll() is None:
            time.sleep(0.05)
        if _runner.poll() is None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _runner.wait(timeout=5)
        code = _runner.returncode
        _runner = None
        _runner_config = None
        return True, code


# ---------------------------------------------------------------- WebUI（gui.py）监管

def _gui_alive():
    return _gui is not None and _gui.poll() is None


def _start_gui_once():
    """拉起一次 gui.py（端口由 config/deploy.yaml 的 WebuiPort 定，默认 22267）。
    uvicorn 输出追加到 ./log/gui.out（gui.py 自身的 ALAS 日志另走 {date}_gui.txt）。"""
    global _gui, _gui_started_at
    os.makedirs(LOG_DIR, exist_ok=True)
    out = open(os.path.join(LOG_DIR, 'gui.out'), 'ab')
    _gui = subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, 'gui.py')],
        cwd=BASE_DIR,
        preexec_fn=os.setsid,  # 独立进程组，清理走 os.killpg
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=subprocess.STDOUT,
    )
    _gui_started_at = time.time()


def _stop_gui():
    """SIGTERM → 3s → SIGKILL 杀 gui 进程组。幂等：没在跑直接返回。"""
    global _gui
    with _gui_lock:
        if not _gui_alive():
            return
        pgid = os.getpgid(_gui.pid)
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.time() + _STOP_GRACE_SEC
        while time.time() < deadline and _gui.poll() is None:
            time.sleep(0.05)
        if _gui.poll() is None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _gui.wait(timeout=5)
        _gui = None


def _gui_supervisor():
    """崩溃重拉循环：wait() 阻塞到 gui 死亡；活过 5 分钟视为健康、退避复位，
    否则退避翻倍（5s→60s 封顶）。_closing 置位（关停）后不重拉直接退出。"""
    backoff = _GUI_BACKOFF_INIT
    while not _closing.is_set():
        with _gui_lock:
            try:
                _start_gui_once()
                proc = _gui
                print(f'MaaAL wrapper: gui.py started pid={proc.pid}', flush=True)
            except OSError as e:
                print(f'MaaAL wrapper: gui spawn failed: {e}', file=sys.stderr, flush=True)
                proc = None
        if proc is None:
            if _closing.wait(backoff):
                break
            backoff = min(backoff * 2, _GUI_BACKOFF_MAX)
            continue
        proc.wait()
        if _closing.is_set():
            break
        uptime = time.time() - (_gui_started_at or time.time())
        backoff = _GUI_BACKOFF_INIT if uptime > _GUI_HEALTHY_UPTIME \
            else min(backoff * 2, _GUI_BACKOFF_MAX)
        print(f'MaaAL wrapper: gui.py exited code={proc.returncode} '
              f'uptime={uptime:.0f}s, respawn in {backoff:.0f}s', flush=True)
        if _closing.wait(backoff):
            break


def _cleanup():
    """父退出前清理：atexit + SIGTERM 都汇到这里。先置 _closing 让监管循环退出，
    再杀 runner 与 gui，防止 supervisor 在我们杀完又重拉。"""
    _closing.set()
    if _runner_alive():
        stop_runner()
    _stop_gui()


def _on_signal(signum, frame):
    _cleanup()
    # 按信号语义退出：128+signum
    sys.exit(128 + signum)


def _stdin_watchdog():
    """stdin 管道 EOF = 父进程已死 → 杀进程组自我了断（m0 孤儿教训）。"""
    try:
        sys.stdin.buffer.read()
    except (OSError, ValueError):
        pass
    _cleanup()
    os._exit(0)


def _arm_stdin_watchdog():
    # 只有 stdin 是管道（FIFO）时才挂监控：父进程死亡 → 管道 EOF → 自尽。
    # tty（手工调试）没有"父进程管道"语义；/dev/null（如 Java Redirect.DISCARD）
    # 读即 EOF，挂上会立即自尽——两者都不挂。
    try:
        if sys.stdin is not None and not sys.stdin.isatty() \
                and stat.S_ISFIFO(os.fstat(sys.stdin.fileno()).st_mode):
            threading.Thread(target=_stdin_watchdog, daemon=True).start()
    except (OSError, ValueError):
        pass


def _acquire_instance_lock():
    """单实例锁：返回锁文件对象（引用防 GC 关 fd），已有实例则 sys.exit(2)。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    fd = open(LOCK_PATH, 'a', encoding='utf-8')
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f'MaaAL wrapper: another instance holds {LOCK_PATH}', file=sys.stderr)
        sys.exit(2)
    fd.write(str(os.getpid()))
    fd.flush()
    return fd


# ---------------------------------------------------------------- 配置实例发现

def _list_configs():
    """config/ 下的实例配置名：*.json 去掉 template*（template.json/.maa/.fpy 等），
    去扩展名排序，'alas' 固定排最前。与 WebUI 配置下拉的来源同一层。"""
    try:
        names = []
        for p in os.listdir(CONFIG_DIR):
            if not p.endswith('.json'):
                continue
            stem = p[:-len('.json')]
            if stem.startswith('template'):
                continue
            names.append(stem)
    except FileNotFoundError:
        return []
    names.sort()
    if 'alas' in names:
        names.remove('alas')
        names.insert(0, 'alas')
    return names


# ---------------------------------------------------------------- 日志读取

def _latest_log_file():
    """./log/ 下 mtime 最新的 *.txt；没有则 None。"""
    try:
        candidates = [os.path.join(LOG_DIR, p) for p in os.listdir(LOG_DIR) if p.endswith('.txt')]
    except FileNotFoundError:
        return None
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def _tail_lines(path, n):
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 256 * 1024))  # 尾部窗口，足够覆盖 2000 行日志
            data = f.read().decode('utf-8', errors='replace')
    except OSError:
        return []
    return data.splitlines()[-n:]


def _count_lines(path):
    try:
        count = 0
        with open(path, 'rb') as f:
            for _ in f:
                count += 1
        return count
    except OSError:
        return 0


# ---------------------------------------------------------------- HTTP 面

class _Handler(BaseHTTPRequestHandler):
    server_version = 'MaaALWrapper/3.0'

    def log_message(self, fmt, *args):  # 静音访问日志
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, text, code=200):
        body = text.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/status':
            log_file = _latest_log_file()
            self._json({
                'runner_alive': _runner_alive(),
                'pid': _runner.pid if _runner_alive() else None,
                'config': _runner_config if _runner_alive() else None,
                'started_at': datetime.datetime.fromtimestamp(_runner_started_at).isoformat()
                if _runner_alive() and _runner_started_at else None,
                'gui_alive': _gui_alive(),
                'gui_pid': _gui.pid if _gui_alive() else None,
                'gui_started_at': datetime.datetime.fromtimestamp(_gui_started_at).isoformat()
                if _gui_alive() and _gui_started_at else None,
                'log_file': log_file,
                'log_lines': _count_lines(log_file) if log_file else 0,
            })
        elif url.path == '/configs':
            self._json({'configs': _list_configs()})
        elif url.path == '/logs':
            qs = parse_qs(url.query)
            try:
                n = min(int(qs.get('tail', ['200'])[0]), 2000)
            except ValueError:
                n = 200
            log_file = _latest_log_file()
            if not log_file:
                self._text('')
            else:
                self._text('\n'.join(_tail_lines(log_file, n)))
        else:
            self._json({'error': 'not found'}, code=404)

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == '/start':
            qs = parse_qs(url.query)
            config_name = qs.get('config', ['alas'])[0] or 'alas'
            if not _CONFIG_RE.match(config_name):
                self._json({'error': 'invalid config name'}, code=400)
                return
            alive, pid, started_now = start_runner(config_name)
            self._json({'runner_alive': alive, 'pid': pid, 'started_now': started_now,
                        'config': _runner_config if alive else None})
        elif url.path == '/stop':
            was_alive, code = stop_runner()
            self._json({'runner_alive': False, 'was_alive': was_alive, 'exit_code': code})
        else:
            self._json({'error': 'not found'}, code=404)


def main():
    _lock_fd = _acquire_instance_lock()  # noqa: F841 - 引用防 GC
    atexit.register(_cleanup)
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    _arm_stdin_watchdog()
    if os.environ.get('MAAAL_WEBUI', '1') != '0':
        threading.Thread(target=_gui_supervisor, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    print(f'MaaAL wrapper: listening on http://{HOST}:{PORT}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
