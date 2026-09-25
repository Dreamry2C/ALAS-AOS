# Handoff 2026-09-25 · 全屏模式落地 + 商店循环定音 + 换源主线定案（mimov2.6pro 阶段快照）

> 接力文档：总体 Plan=`.tmp/2026-09-25-alastofox-migration-plan.md`（含 2026-09-25 追加决策）；逐步流水=`.tmp/2026-09-25-live.md`（[00]–[06]=opus-4.8，[07]起=mimov2.6pro，条目均署名）。

## 已完成（全部署名 mimov2.6pro，commit 均带「署名: mimov2.6pro」）

1. **`fe9835b` 游戏自动钉回虚拟屏**：66 ROM 在游戏自身 Activity 二段跳时把任务拖回 display 0（`Failed to put TaskRecord on display 3`），`app_start_alasaos` 启动后 `am display move-stack` 自动钉回；实机验证自愈闭环（黑屏→重启→钉回→APP LOGIN）。
2. **`62129bf` 主屏全屏模式（PRIMARY）接线 + 商店循环定音**：新增 `DisplayTarget`，HostState 按 `runMode` 设模式，桥 screencap/click/display_info 模式感知，alasaos.py VID=0 全屏语义。商店循环定音=**SHOP_CHECK 资产漂移**（钉版 0.841<0.85 vs AlasToFox 0.999）+ 侧栏 tab 判据同屏误命中 + 页面图缺回链；**实证非 OCR（识别链纯模板匹配 0.85 阈值）、非缩放（两路采集同分）**。
3. **`1500ec4` 设置页补「运行模式」**（此前无 UI 入口）：后台模式=虚拟屏 / 前台模式=主屏全屏。
4. 66 实测（0.1.6-alpha.9/构建77）：**前台模式端到端全绿**——`display mode=PRIMARY display id=0` → 钉屏 `placements=[(2, 0)]` → 页面识别/点击注入正常 → `Schedule exhausted` 正常收队。

## 关键事实（回读必看）

- **52 虚拟屏方案正常**（长期稳定跑游戏）；66 特有 ROM 拖拽问题。商店循环两台都有，与显示模式无关。
- 66 已切「前台模式」运行；52 可继续「后台模式」。
- 66 设备 `/opt/alas/assets/cn/ui/SHOP_CHECK.png` 已热修为 AlasToFox 版（**热更新 git reset 会打回**，正式修复随换源解决）。
- ALAS **自带**进 rootfs（构建期 clone），非解压下载；远程置空落点=构建期 `ALAS_REPO` + 运行期 `alasaos_update.sh`（git://git.lyoko.io + CDN pack）必须关/置空 + deploy.yaml `AutoUpdate:false`。

## 下一步计划（换源主线，详见 Plan 追加决策）

1. **重烘 rootfs：ubuntu-base 20.04（py3.8）**——现 guest 是 24.04/py3.12，与原版依赖（mxnet/cnocr 1.x/numpy 1.16/imageio 2.27）不兼容；`.tmp/构建py3.8版本/` 三份 mxnet whl 全含 aarch64 libmxnet.so（130/107/114MB）待试装，`mxnet_alas-0.0.5` 是重打包版。能 3.8 就 3.8，不行退 3.7。
2. `ALAS_REPO` 指向 `E:\GitRepository\AlasToFox`（用户魔改版，原版特调 OCR=cnocr+mxnet+azur_lane 模型）。
3. 更新源/分支**可配置**（设置→「更新设置」）：源默认打码+小眼睛明文，**留空=默认源 `git://git.lyoko.io/AzurLaneAutoScript`**（★用户最终令：源只有内置默认+用户填写两个，gitee 撤销★）；分支默认 master 可自定义。更新语义=ALAS 老样子 `git fetch + reset --hard`（与 AlasToFox `deploy/git.py` 同款；remote 每次对齐配置源，不做保文件自愈）。用户分支未发布期间先用默认源，发布后在设置填自己的源。
4. 渠道服包名核对（66=`com.bilibili.blhx.qihoo`，上游 server.py 已含）。
5. 编译装 66 实测 + 商店任务（SUPPLY PACK）实证不循环。

## 注意事项

- 不 push/发版、不重启云机、不清碧蓝数据、不改 ALAS 上游（换源后 AlasToFox=用户仓库可改，上游=LmeSzinc 不可改）。
- 临时文件在 `.tmp/`；test 用 `python rootfs/tests/test_alasaos_*.py`（ast 抽函数风格，17 例）。
- 构建：JDK17 `E:\GitRepository\Moontier\.build-tools\jdk17\jdk-17.0.16+8` + `GRADLE_USER_HOME=.tmp/gradle-home` + `.tmp/gradle-dist/gradle-9.4.1`，`assembleDebug`；装机 `adb install -r -d`（后台 nohup 防阻塞）。
