#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AlasAos：把 config/deploy.yaml 的 Repository/Branch 同步成「当前更新源」。

由 alasaos_update.sh 在更新成功/确认最新后调用：
    python3 seeds/sync_deploy.py <REPO> <BRANCH>

为什么要这个（2026-10-01 opus5）：
  ALAS 自带「更新器」WebUI 读 config/deploy.yaml 的 Repository 跑 git log 做
  本地/上游对比。AOS 换源后现场 git remote 已是用户源，但 deploy.yaml 仍是旧源
  → 更新器界面本地/上游全空。把这两键同步成当前源，界面就能正确对比。

与 seed_deploy.py 分工：seed_deploy 管「静态策略键」(EnableReload 等)，本脚本管
  「跟随用户换源的两键」(Repository/Branch)。两边各改各的键、互不覆盖。

用行级正则替换（保留 ALAS poor_yaml 的注释/行结构/原行尾 CRLF 或 LF，不用 PyYAML
  回写以免丢注释）。失败只打印、退出 0，绝不阻塞更新流程。

注意：用户私有 gitee 源不在 ALAS deploy/config.py::config_redirect 的改写名单
  （那名单只含 LmeSzinc 官方的几个 gitee/coding 镜像），写进去不会被 ALAS 改回。
"""
import os
import re
import sys

ALAS = os.environ.get('ALASAOS_ALAS_ROOT', os.path.expanduser('~/alas'))
DEPLOY = os.path.join(ALAS, 'config', 'deploy.yaml')


def _set_key(text, key, want):
    """把 'key: <旧值>' 行的值改成 want，保留缩进与行尾。返回 (新文本, 是否改动)。"""
    pattern = re.compile(
        r'^(?P<indent>[ \t]*)' + re.escape(key) + r'(?P<sep>:[ \t]*)(?P<val>.*?)(?P<eol>\r?)$',
        re.MULTILINE,
    )
    changed = [False]

    def _repl(m):
        if m.group('val').strip() == want:
            return m.group(0)
        changed[0] = True
        return f"{m.group('indent')}{key}{m.group('sep')}{want}{m.group('eol')}"

    new_text, n = pattern.subn(_repl, text)
    if n == 0:
        print(f'sync_deploy: key {key} not present, skip')
        return text, False
    return new_text, changed[0]


def main(argv):
    if len(argv) < 3:
        print('sync_deploy: usage: sync_deploy.py <REPO> <BRANCH>')
        return 0
    repo, branch = argv[1], argv[2]
    if not repo or not branch:
        print('sync_deploy: empty repo/branch, skip')
        return 0
    if not os.path.isfile(DEPLOY):
        print(f'sync_deploy: {DEPLOY} not found, skip')
        return 0
    try:
        with open(DEPLOY, encoding='utf-8', newline='') as f:
            text = f.read()
    except Exception as e:  # noqa: BLE001
        print(f'sync_deploy: read failed ({e}), skip')
        return 0

    text, c1 = _set_key(text, 'Repository', repo)
    text, c2 = _set_key(text, 'Branch', branch)
    if not (c1 or c2):
        print('sync_deploy: deploy.yaml already matches current source')
        return 0
    try:
        with open(DEPLOY, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        # GPT-6 Astra: the URL may carry credentials; never copy it to app logs.
        print('sync_deploy: deploy.yaml Repository/Branch synchronized')
    except Exception as e:  # noqa: BLE001
        print(f'sync_deploy: write failed ({e}), skip')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
