# MaaAL

免 root 的 Android 端 [ALAS](https://github.com/LmeSzinc/AzurLaneAutoScript)（AzurLaneAutoScript）运行环境：仅靠 Shizuku（修改版）即可在手机后台虚拟屏里挂机《碧蓝航线》自动化，前台正常使用手机互不干扰。

> 标 `TODO` 的 shizuku-m 获取方式随其分发安排回填；支持机型清单随更多实测持续补充。

[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](./LICENSE)

## 特性

- **免 root**：提权只靠用户自装的 shizuku-m（官方 Shizuku v13.6.0 的修改版，支持离线自连，重启后无需 WLAN/电脑配对）。
- **后台挂机**：游戏跑在后台虚拟屏（1280×720），前台刷别的应用不受影响；悬浮球面板随时启停与看日志。
- **一键安装**：单个 APK 装完即用——Ubuntu rootfs（Python 3.12 + ALAS 官方 master + 补丁集 + PP-OCR 模型）随包内置，首启自动解压部署。
- **开屏热更新**：每次启动检查 ALAS 上游更新（大陆可达镜像，秒级快进）；断网/超时自动降级跳过，绝不阻塞启动。
- **本机 OCR/控制**：截图与触控走本机特权进程桥（延迟 p50 ≈ 30ms），不经过 adb、不需要电脑。

## 工作原理（一图流）

```
┌─ App 进程（Kotlin）────────────────────────────┐
│  挂机页（虚拟屏实时画面 + 运行配置 + 控制面板）     │
│  WebView 控制台（ALAS WebUI :22267）            │
│  挂机页/悬浮窗面板 ──HTTP──> wrapper(:22400)      │
├─ 特权进程（shizuku 拉起）───────────────────────┤
│  虚拟屏 #VID + 截屏/触控注入                     │
│  桥服务 :22300（ping/screencap/click/swipe/shell）│
├─ proot Ubuntu rootfs（App 私有目录，免 root）───┤
│  wrapper.py 监管 → runner（ALAS 调度器）         │
│                  → gui.py（WebUI）              │
│  ALAS ──桥──> 虚拟屏里的游戏                     │
└─────────────────────────────────────────────────┘
```

## 安装

**前置**：一台未 root 的 Android 手机（arm64）+ 自行安装并激活 shizuku-m（获取方式：`TODO`，分发安排另行公布）。

1. 安装 shizuku-m，打开点「启动」（无需连接 WLAN 或电脑）。
2. 安装 MaaAzurLane APK（[Release 页](https://github.com/Shinarin/MaaAL/releases)下载 `MaaAzurLane-v<版本号>-android-arm64.apk`），打开并按引导授权 Shizuku。
3. 等待首启部署完成（解压 rootfs + 热更新检查），自动进入挂机页。
4. 安装《碧蓝航线》（国服 `com.bilibili.azurlane`），在控制台配置后即可从挂机页或悬浮窗「开始挂机」。

**每次手机重启后**：打开 shizuku-m 点「启动」（约 30 秒，可离线），再回到 MaaAL 即可自动恢复。免 root 方案这一步物理不可约，请知悉。

## 使用

- **挂机页 / 悬浮窗 = 控制面**：高频操作都在这两处（同一块面板）——查看环境/调度器状态、「开始挂机 / 停止挂机」、实时日志板。挂机页在 App 内，另可看虚拟屏实时画面 + 选择运行配置（`config/` 下的实例名）；悬浮窗管 App 不在前台时的场景。
- **完整配置回 ALAS 控制台**：ALAS 控制台（WebUI）负责任务配置、计划任务、截图查看等全部能力；改任务参数请去那里，挂机页只选「跑哪个配置」。
- **WebUI 的启动/停止按钮已被锁定**：ALAS 原生 ProcessManager 启停通道在 MaaAL 里由补丁关闭（防双跑抢设备），点击只会在日志里留一条警告——调度请一律走挂机页或悬浮窗。

## 支持机型 / ROM

多 ROM 实测矩阵见 [docs/rom-matrix.md](docs/rom-matrix.md)（持续补充），当前已验证基线：

| 机型 | ROM | Android | 状态 |
|------|-----|---------|------|
| HONOR PPG-AN00 | MagicOS | 16 (API 36) | ✅ 全链路实证（开发基线） |

## 常见问题

**Q: 检测到官方版 Shizuku 怎么办？**
官方版与 shizuku-m 同包名不同签名，不能直接覆盖安装；且官方版每次重启都要 WLAN 配对。按 App 内弹窗引导卸载官方版（不影响本应用数据），再装 shizuku-m 即可。

**Q: 需要电脑吗？**
不需要。安装、激活、更新、挂机全在手机上完成。

**Q: 会被游戏检测吗？**
本项目不修改游戏本体，截图与触控均为系统级能力。使用自动化脚本违反游戏用户协议的风险由使用者自行承担。

## 仓库

- 主仓库（本仓）：[Shinarin/MaaAL](https://github.com/Shinarin/MaaAL)——App + rootfs 构建链 + 补丁集，Release 页附源码（AGPL 义务）。
- shizuku-m：提权组件 fork，分发渠道另行公布。

## 构建与开发

见 [development.md](development.md)（构建命令、仓库结构、阶段账本）与 [docs/roadmap-v3.md](docs/roadmap-v3.md)（开发宪法）。

## 许可

[AGPL-3.0](./LICENSE)。本仓库包含 ALAS（GPL-3.0）补丁与 MaaFwApp（AGPL-3.0）fork 修改，均按各自许可证义务公开源码。
