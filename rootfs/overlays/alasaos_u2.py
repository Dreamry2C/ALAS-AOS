"""Keep optional uiautomator2 construction from opening an unrelated ADB server.

The AOS serial denotes the injected screenshot/input/shell bridge, not an ADB
transport. Optional integrations may construct a u2 object even when disabled.
Do not pretend to support u2 RPC: report it when actually requested.
"""
import functools


class BridgeU2:
    def __init__(self):
        self.wait_timeout = 20.0

    def __getattr__(self, name):
        raise RuntimeError(
            'uiautomator2 RPC is unavailable for the AOS bridge device; '
            'this optional feature requires a real uiautomator2 connection')

    def __call__(self, *args, **kwargs):
        return self.__getattr__('selector')


def install():
    import uiautomator2 as u2
    original = u2.connect

    @functools.wraps(original)
    def connect(serial=None, *args, **kwargs):
        if isinstance(serial, str) and serial.startswith('alasaos'):
            return BridgeU2()
        return original(serial, *args, **kwargs)

    u2.connect = connect
