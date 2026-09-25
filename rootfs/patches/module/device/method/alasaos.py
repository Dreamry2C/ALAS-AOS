"""AlasAos 桥接 method：设备 I/O 全部经 TCP 代理转发到 MaaFwApp 特权进程。

代理（spike/m0/agent/main.py）在手机上监听 127.0.0.1:22300，协议为行分隔 JSON + 二进制帧：
    ping/screencap/click/swipe/ocr/shell，详见代理源文件 docstring。

启用方式：Emulator_Serial 以 "alasaos" 开头（默认 serial 即 "alasaos"），
截图/控制方法选择 "alasaos"。本模块不 import 任何 adb/u2 依赖。

注意：
- MaaFW 截图为 BGR 序，ALAS 图像为 RGB 序，screenshot_alasaos 负责翻通道。
- 游戏必须跑在 MaaFwApp 的虚拟屏上：app_start_alasaos 用 `am start --display <VID>`，
  VID 由代理侧 shell 探测（dumpsys display 找 VIRTUAL displayId），每轮进程缓存一次。
  部分 ROM（云机）会把游戏自身 Activity 二段跳（SplashActivity→MainActivity，caller=游戏
  uid）拦回 display 0（AOSP isCallerAllowedToLaunchOnDisplay：VD owner 是 shell、游戏
  Activity 无 FLAG_ALLOW_EMBEDDED），故启动后用 `am display move-stack` 把任务钉回 VID。
- get_orientation 对桥接固定返回 0（虚拟屏始终横屏 1280x720）。
- dump_hierarchy 反映的是物理屏 UI 树（uiautomator 看不到虚拟屏），仅作兜底。
"""
import json
import re
import socket
import time

import numpy as np

from module.base.decorator import cached_property
from module.exception import RequestHumanTakeover, ScriptError
from module.logger import logger

ALASAOS_DEFAULT_ADDR = '127.0.0.1:22300'


def _display_foreground_package(output: str, display_id: int) -> str:
    """Read only the requested display, including Android 10's unfocused VD."""
    headers = list(re.finditer(
        r'^[ \t]*Display(?:[ \t]*:[ \t]*mDisplayId=|[ \t]+(?:displayId=|mDisplayId=)?)(\d+)\b',
        output, re.MULTILINE))
    for index, header in enumerate(headers):
        if int(header.group(1)) != display_id:
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(output)
        block = output[header.end():end]
        for pattern in (
            r'mCurrentFocus=Window\{[^\n}]*?\s([\w.]+)/[\w.$]+',
            r'mFocusedApp=[^\n]*?ActivityRecord\{[^\n}]*?\s([\w.]+)/[\w.$]+',
        ):
            match = re.search(pattern, block)
            if match:
                return match.group(1)
        return ''
    return ''


def _game_task_placements(output: str, package: str):
    """Parse `dumpsys window windows`; return [(stack_id, display_id), ...] owned by package.

    Each `  Window #N Window{... pkg/activity}:` block carries one
    `mDisplayId=<id> stackId=<id>` line. Multiple windows of the same task
    collapse to one entry.
    """
    placements = []
    seen = set()
    blocks = re.split(r'(?=^\s*Window #\d+ )', output, flags=re.MULTILINE)
    for block in blocks:
        if not re.search(r'Window\{[^}\n]*\s' + re.escape(package) + r'/[\w.$]+\}', block):
            continue
        display = re.search(r'mDisplayId=(\d+)', block)
        stack = re.search(r'stackId=(\d+)', block)
        if not display or not stack:
            continue
        key = (int(stack.group(1)), int(display.group(1)))
        if key not in seen:
            seen.add(key)
            placements.append(key)
    return placements


class AlasAosBridgeError(Exception):
    pass


class AlasAos:
    _alasaos_sock = None
    _alasaos_req_id = 0

    # ---------------------------------------------------------------- 协议层

    @cached_property
    def alasaos_addr(self) -> str:
        import os
        return os.environ.get('ALASAOS_PROXY_ADDR', ALASAOS_DEFAULT_ADDR)

    def _alasaos_connect(self) -> socket.socket:
        host, _, port = self.alasaos_addr.partition(':')
        sock = socket.create_connection((host, int(port)), timeout=10)
        sock.settimeout(60)
        return sock

    def _alasaos_call(self, payload: dict, frame: bytes = None) -> dict:
        """发送一条请求（可随附一帧二进制），返回响应 dict。连接错误重连重试一次。"""
        AlasAos._alasaos_req_id += 1
        payload = dict(payload)
        payload['id'] = AlasAos._alasaos_req_id

        last_error = None
        for _ in range(2):
            try:
                sock = AlasAos._alasaos_sock
                if sock is None:
                    sock = AlasAos._alasaos_sock = self._alasaos_connect()
                sock.sendall(json.dumps(payload, separators=(',', ':')).encode('utf-8') + b'\n')
                if frame is not None:
                    sock.sendall(frame)
                # 逐字节读响应行：screencap 响应行后紧跟像素帧，大块读会吞帧
                buf = b''
                while not buf.endswith(b'\n'):
                    data = sock.recv(1)
                    if not data:
                        raise AlasAosBridgeError('proxy closed connection')
                    buf += data
                    if len(buf) > 256 * 1024:
                        raise AlasAosBridgeError('response line too long')
                return json.loads(buf.decode('utf-8'))
            except (OSError, AlasAosBridgeError, json.JSONDecodeError) as e:
                last_error = e
                logger.warning(f'AlasAos proxy error: {e}, reconnect')
                try:
                    if AlasAos._alasaos_sock is not None:
                        AlasAos._alasaos_sock.close()
                except OSError:
                    pass
                AlasAos._alasaos_sock = None
        logger.critical(f'AlasAos proxy unreachable: {last_error}')
        raise RequestHumanTakeover

    def _alasaos_call_ok(self, payload: dict, frame: bytes = None) -> dict:
        resp = self._alasaos_call(payload, frame)
        if not resp.get('ok'):
            raise ScriptError(f'AlasAos proxy error: {resp.get("error", "unknown")}')
        return resp

    def _alasaos_read_exact(self, n: int) -> bytes:
        sock = AlasAos._alasaos_sock
        chunks = []
        while n > 0:
            data = sock.recv(min(1048576, n))
            if not data:
                raise AlasAosBridgeError('connection closed mid-frame')
            chunks.append(data)
            n -= len(data)
        return b''.join(chunks)

    # ---------------------------------------------------------------- 截图 / 触控

    def screenshot_alasaos(self) -> np.ndarray:
        resp = self._alasaos_call_ok({'method': 'screencap'})
        raw = self._alasaos_read_exact(int(resp['length']))
        image = np.frombuffer(raw, dtype=np.uint8).reshape(
            int(resp['height']), int(resp['width']), int(resp['channels']))
        # BGR(A) -> RGB（ALAS 图像约定 RGB 序）
        if image.shape[2] >= 3:
            image = image[..., :3][..., ::-1]
        return np.ascontiguousarray(image)

    def click_alasaos(self, x, y):
        self._alasaos_call_ok({'method': 'click', 'x': int(x), 'y': int(y)})

    def long_click_alasaos(self, x, y, duration):
        # 等效长按：原地滑动，duration 单位为秒（ALAS 约定），代理侧为毫秒
        self._alasaos_call_ok({
            'method': 'swipe',
            'x1': int(x), 'y1': int(y), 'x2': int(x), 'y2': int(y),
            'duration': int(duration * 1000),
        })

    def swipe_alasaos(self, p1, p2, duration=0.1):
        self._alasaos_call_ok({
            'method': 'swipe',
            'x1': int(p1[0]), 'y1': int(p1[1]),
            'x2': int(p2[0]), 'y2': int(p2[1]),
            'duration': int(duration * 1000),
        })

    # ---------------------------------------------------------------- shell 通道

    def alasaos_shell(self, cmd: str, timeout: float = 30) -> dict:
        """经代理以 shell uid 执行系统命令，返回 {ok, code, stdout, stderr}。"""
        return self._alasaos_call({'method': 'shell', 'cmd': cmd, 'timeout': timeout})

    def alasaos_shell_output(self, cmd: str, timeout: float = 30) -> str:
        resp = self.alasaos_shell(cmd, timeout)
        if not resp.get('ok'):
            raise ScriptError(f'AlasAos shell failed: {cmd!r}: {resp.get("stderr", "")[:200]}')
        return resp.get('stdout', '')

    @cached_property
    def alasaos_display_id(self) -> int:
        out = self.alasaos_shell_output(
            "dumpsys display | grep -oE 'type=VIRTUAL, [^}]*displayId=[0-9]+' | grep -oE '[0-9]+' | tail -1"
        ).strip()
        if not out.isdigit():
            raise ScriptError(f'AlasAos virtual display not found: {out!r}')
        logger.attr('AlasAos', f'virtual display id={out}')
        return int(out)

    def alasaos_pin_game_to_display(self, package=None, timeout=10.0, interval=0.4):
        """把游戏任务钉回虚拟屏（防游戏自身 Activity 二段跳把任务拖回 display 0）。

        拖回时机在启动后 0.5~2s（SplashActivity→MainActivity），故持续观察；
        连续 5 拍在目标屏（且已拖回过或观察满 3s）即收工。返回最终是否在虚拟屏上。
        """
        package = package or self.package
        vid = self.alasaos_display_id
        start = time.time()
        deadline = start + float(timeout)
        moved = False
        stable = 0
        final = None
        while time.time() < deadline:
            placements = _game_task_placements(
                self.alasaos_shell_output('dumpsys window windows'), package)
            final = placements or None
            if not placements:
                stable = 0
            else:
                all_on_target = True
                for stack_id, display_id in placements:
                    if display_id == vid:
                        continue
                    all_on_target = False
                    stable = 0
                    resp = self.alasaos_shell(f'am display move-stack {stack_id} {vid}')
                    if resp.get('ok'):
                        moved = True
                        logger.attr('AlasAos', f'game stack {stack_id} pinned to display {vid}')
                    else:
                        logger.warning(
                            f'AlasAos pin stack {stack_id} failed: '
                            f'{resp.get("error") or resp.get("stderr") or resp}')
                if all_on_target:
                    stable += 1
            if stable >= 5 and (moved or time.time() - start >= 3.0):
                break
            time.sleep(interval)
        placements = _game_task_placements(
            self.alasaos_shell_output('dumpsys window windows'), package)
        ok = bool(placements) and all(display_id == vid for _, display_id in placements)
        logger.attr('AlasAos', f'game pinned={ok} placements={placements}')
        return ok

    # ---------------------------------------------------------------- App 控制

    def app_start_alasaos(self, package=None, activity=None, wait=True):
        from module.config.server import DICT_PACKAGE_TO_ACTIVITY
        package = package or self.package
        if activity is None:
            activity = DICT_PACKAGE_TO_ACTIVITY.get(package)
            if activity is None:
                raise ScriptError(f'No known activity for package: {package}')
        self.alasaos_shell_output(
            f'am start --display {self.alasaos_display_id} -n {package}/{activity}')
        if wait:
            time.sleep(1)
        self.alasaos_pin_game_to_display(package)

    def app_stop_alasaos(self, package=None):
        self.alasaos_shell_output(f'am force-stop {package or self.package}')

    def app_current_alasaos(self) -> str:
        """只读取目标虚拟屏的焦点，避免把物理屏应用误判为游戏前台。"""
        out = self.alasaos_shell_output('dumpsys window displays')
        vid = self.alasaos_display_id
        current = _display_foreground_package(out, vid)
        logger.attr('App current (alasaos)', current)
        return current

    def get_orientation(self):
        """桥接模式下虚拟屏始终横屏 1280x720，直接返回 0。
        注意：本方法在 AlasAos 混入类上，MRO 先于 Connection 的 adb 实现。"""
        if str(self.serial).startswith('alasaos'):
            self.orientation = 0
            return 0
        return super().get_orientation()

    def dump_hierarchy_alasaos(self):
        """兜底实现：uiautomator dump 看到的是物理屏 UI 树（虚拟屏内容不可见）。
        仅用于不依赖游戏画面的系统级弹窗处理；游戏内 UI 不应走这里。"""
        from lxml import etree
        logger.warning('dump_hierarchy on alasaos reflects the PHYSICAL display, not the virtual one')
        out = self.alasaos_shell_output(
            'uiautomator dump /data/local/tmp/alasaos_ui.xml >/dev/null 2>&1; '
            'cat /data/local/tmp/alasaos_ui.xml', timeout=60)
        self.hierarchy = etree.fromstring(out.encode('utf-8'))
        return self.hierarchy
