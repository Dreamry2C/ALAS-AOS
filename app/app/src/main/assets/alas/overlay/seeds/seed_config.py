#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MaaAL：由 config/template.json 生成 config/alas.json 并注入桥接配置。

在 ~/alas 根目录下运行：python seed_config.py
幂等：config/alas.json 已存在时不覆盖（改配置请走 WebUI）。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
# 允许从任意目录运行：脚本在 termux/ 下，ALAS 根目录取 ~/alas
ALAS = os.environ.get('MAAAL_ALAS_ROOT', os.path.expanduser('~/alas'))

SRC = os.path.join(ALAS, 'config', 'template.json')
DST = os.path.join(ALAS, 'config', 'alas.json')

OVERRIDES = {
    # Alas.Emulator
    ('Alas', 'Emulator', 'Serial'): 'maaal',
    ('Alas', 'Emulator', 'PackageName'): 'com.bilibili.azurlane',
    ('Alas', 'Emulator', 'ScreenshotMethod'): 'maaal',
    ('Alas', 'Emulator', 'ControlMethod'): 'maaal',
    # 省电与稳定：截图去抖动关闭（虚拟屏无噪点）
    ('Alas', 'Emulator', 'ScreenshotDedithering'): False,
}


def main():
    if os.path.exists(DST):
        print(f'{DST} already exists, skip')
        return
    with open(SRC, encoding='utf-8') as f:
        cfg = json.load(f)
    for (menu, group, arg), value in OVERRIDES.items():
        cfg[menu][group][arg] = value
    with open(DST, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f'seeded {DST} with maaal bridge config')


if __name__ == '__main__':
    sys.exit(main())
