# MaaAL

免 root 的 Android 端 [ALAS](https://github.com/LmeSzinc/AzurLaneAutoScript)（AzurLaneAutoScript）运行环境：仅靠 Shizuku（修改版）即可在手机后台虚拟屏里挂机《碧蓝航线》自动化，前台正常使用手机互不干扰。

> ⚠️ 本 README 为阶段五交付草案：标 `TODO-阶段五` 的小节（支持机型清单、仓库地址、shizuku-m 获取方式）随多 ROM 实测与仓库公开回填。

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
│  WebView 控制台（ALAS WebUI :22267）            │
│  悬浮窗面板 ──HTTP──> wrapper(:22400)           │
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

**前置**：一台未 root 的 Android 手机 + 自行安装并激活 shizuku-m（获取方式：`TODO-阶段五`）。

1. 安装 shizuku-m，打开点「启动」（无需连接 WLAN 或电脑）。
2. 安装 MaaAL APK（Release 页下载：`TODO-阶段五`），打开并按引导授权 Shizuku。
3. 等待首启部署完成（解压 rootfs + 热更新检查），自动进入 ALAS 控制台。
4. 安装《碧蓝航线》（国服 `com.bilibili.azurlane`），在控制台配置后即可从悬浮窗「开始挂机」。

**每次手机重启后**：打开 shizuku-m 点「启动」（约 30 秒，可离线），再回到 MaaAL 即可自动恢复。免 root 方案这一步物理不可约，请知悉。

## 使用

- **悬浮窗 = 唯一控制面**：高频操作都在悬浮球面板——查看环境/调度器状态、「开始挂机 / 停止挂机」、实时日志板。
- **完整配置回应用内**：ALAS 控制台（WebUI）负责任务配置、计划任务、截图查看等全部能力。
- ⚠️ **不要用 WebUI 里的启动/停止按钮**（ALAS 原生 ProcessManager 通道）：它与悬浮窗通道并存双跑会抢设备输入，调度请一律走悬浮窗。

## 支持机型 / ROM

`TODO-阶段五`：多 ROM 实测矩阵见 [docs/rom-matrix.md](docs/rom-matrix.md)，当前已验证基线：

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

`TODO-阶段五`（决策 #12：三个仓库公开，发布页附源码链接，AGPL 义务）

- 主仓库（本仓）：App + rootfs 构建链 + 补丁集
- shizuku-m：提权组件 fork
- （分发/资源仓待定）

## 构建与开发

见 [development.md](development.md)（构建命令、仓库结构、阶段账本）与 [docs/roadmap-v3.md](docs/roadmap-v3.md)（开发宪法）。

## 许可

[AGPL-3.0](./LICENSE)。本仓库包含 ALAS（GPL-3.0）补丁与 MaaFwApp（AGPL-3.0）fork 修改，均按各自许可证义务公开源码。
