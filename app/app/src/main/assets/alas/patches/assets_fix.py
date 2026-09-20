#!/usr/bin/env python3
"""AlasAos 资产热修补：按 Button 名重写 assets.py 里的 cn area/color/button。

为什么不整文件覆盖 assets.py：该文件由上游 dev_tools/button_extract 生成，
每次上游资产更新都会整体重排。整文件覆盖会在 apply_patches 时把上游新资产
打回旧版；按名修补则在上游更新后仍能重放我们的本地校准。

覆盖时机：apply_patches.sh 在 cp 完 PNG 模板后调用本脚本。

每项：(assets_py 相对路径, Button 名, area, color, button)。值为 None 的字段不改。
颜色为 RGB（ALAS 资产约定，与 load_image 的 PIL 读取一致）。

校准记录（2026-08-29，M2 实测，设备 bilibili 服 1280x720 虚拟屏）：
- SHOP_CHECK：商店页标题 UI 改版，字号变大/底色变化，颜色检测 B 通道差 28.6 超阈。
  模板与色值按真机商店页重录。
- DAILY_SKIP：每日副本详情弹窗「快速挑战」拆为「单次」+「N 次」双按钮，
  旧 area (1003,295,1102,349) 落在「N 次」按钮上会一次误耗 3 次挑战机会。
  上游 daily_enter 语义是"点一次清完"，与多次按钮对齐：
  检测区收窄到多次按钮左半固定文字「快速挑战」（避开变化的"N 次"），
  点击区覆盖整个多次按钮。单次按钮排版（文字居中）与本区不冲突。
  待验证：剩余次数为 1 时多次按钮是否仍存在（若消失需单次按钮兜底）。
"""
import re
import sys

FIXES = [
    ('module/ui/assets.py', 'SHOP_CHECK',
     None, (96, 104, 117), None),
    ('module/daily/assets.py', 'DAILY_SKIP',
     (1005, 300, 1100, 350), (124, 157, 204), (1000, 297, 1155, 355)),
    # 主线准备页「立即前往」：新版双按钮布局（作战委托|立即前往）使按钮右移 ~100px。
    ('module/map/assets.py', 'MAP_PREPARATION',
     (965, 495, 1100, 545), (243, 211, 132), (955, 485, 1110, 552)),
    # 船坞排序箭头：位置未变，渲染轻微变暗致点亮态色差 11-12 略超阈值 10。
    # 两态点亮色实测一致 (180,197,219)；降序色取自降序态截图。
    ('module/retire/assets.py', 'SORT_ASC',
     None, (180, 197, 219), None),
    ('module/retire/assets.py', 'SORT_DESC',
     None, (180, 197, 219), None),
    # BATTLE_STATUS_D 曾按带立绘结算页重录，后查明真因为游戏设置「展示结算角色=开」
    # 改变结算页布局；关闭该设置后恢复上游原版资产（已 git checkout 回滚，不入 FIXES）。
    # S/A/B/C 胜利评级资产在无立绘布局下的匹配性待下次真实结算时验证。
]


def rebuild_section(sec, new_cn):
    return re.sub(r"'cn': \([^)]+\)", f"'cn': {new_cn}", sec, count=1)


def apply_fix(alas_dir, rel_path, name, area, color, button):
    path = f'{alas_dir}/{rel_path}'
    lines = open(path).readlines()
    for i, line in enumerate(lines):
        if line.startswith(f'{name} = '):
            def section(field):
                m = re.search(field + r"=\{(.*?)\}(?=, \w+=|\)\n?$)", line)
                if not m:
                    raise RuntimeError(f'{name}: section {field} not found')
                return m.group(1)

            file_m = re.search(r"file=\{(.+)\}\)\n?$", line)
            if not file_m:
                raise RuntimeError(f'{name}: file section not found')

            area_sec = rebuild_section(section('area'), area) if area else section('area')
            color_sec = rebuild_section(section('color'), color) if color else section('color')
            button_sec = rebuild_section(section('button'), button) if button else section('button')
            lines[i] = (f"{name} = Button(area={{{area_sec}}}, color={{{color_sec}}}, "
                        f"button={{{button_sec}}}, file={{{file_m.group(1)}}})\n")
            open(path, 'w').writelines(lines)
            print(f'[assets_fix] {name} @ {rel_path}:{i + 1}')
            return
    raise RuntimeError(f'{name} not found in {rel_path}')


def main():
    alas_dir = sys.argv[1] if len(sys.argv) > 1 else f'{__import__("os").path.expanduser("~")}/alas'
    for rel_path, name, area, color, button in FIXES:
        apply_fix(alas_dir, rel_path, name, area, color, button)


if __name__ == '__main__':
    main()
