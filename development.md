# Development

## 当前阶段

**阶段二（宿主外壳）已收官**：M2-a 基线绿 → M2-b 减法剔除（−19.6k 行）→ M2-c 特权进程内 Kotlin 桥（TCP 22300 五端点）→ M2-d HostState 接管外壳状态 + 悬浮球/FGS 脱钩 RunnerPort，DoD 真机验证 6/6（2026-09-16）。**下一步：阶段三（管道穿透与生命周期）**。阶段一 M1 已交付：rootfs 构建链 GHA 四连迭代至绿，v4 artifact 为交付基准；M1-d 真机复验 WebUI/MANIFEST 已过，**油数 100 帧验收待用户把游戏点到出击菜单页**。

- 开发宪法：`docs/roadmap-v3.md`（13 项决策、阶段〇–五、风险登记）。
- 阶段二工作底稿：`docs/stage2-maafwapp-inventory.md`（减法三栏清单 / 新桥设计 / VD flag 核查）。
- 任何不清楚之处：先读 roadmap，再读 `handoff/` 最新文件（当前 `2026-09-16-m2.md`）。

## 仓库结构（现状）

- `app/` — 阶段二主战场：MaaFwApp fork 复活副本（b2b0f54 + m0 WebView 6 处改动固化 + 构建修复：Aliyun 镜像、floatingx-compose 显式声明）。
- `rootfs/` — 阶段一资产：`build/build-rootfs.sh`（GHA ARM64 构建脚本）、`patches/`（ALAS 补丁集，含 `module/device/method/maaal.py` 桥客户端）。
- `.github/workflows/` — rootfs 构建 workflow（手动触发；`ALAS_REF` 默认 master 浮动，manifest 记录解析后 commit）。
- `docs/` — `roadmap-v3.md`、`stage2-maafwapp-inventory.md`、`spike-d-wrapper-surface.md`。
- `spike/` — 阶段〇交付：`a-proot-exec/`（Spike A/C 工程+报告）、`e-adb-virtual-display/`（Spike E/B′）。
- `m0-archive/`（gitignore，本地只读）— m0 全部成果归档：MaaFwApp fork、termux 补丁/种子、桥代理、OCR 模型、m0 devlog。
- 账册（根目录）：`devlog.md`（倒序流水）、`debug.md`（坑与解法）、`development.md`（本文件）、`handoff/`（跨对话接力，取最新）。
- `.tmp/`（gitignore）— 构建缓存（`gradle-home`）、实验物、rootfs artifact、ALAS 部分克隆。

## 技术栈（规划，源自 v3）

- **Android App**：MaaFwApp fork 减法整理（Kotlin，Gradle，AGPL-3.0）——保留特权进程（虚拟屏+截屏注入）、TCP 22300 桥（五端点，Kotlin 重写）、WebView 容器、Shizuku 辅助。
- **rootfs**：Ubuntu 24.04 ARM64 + Python 3.12 + opencv-headless + onnxruntime + ALAS 官方 master（GitHub，BUILD_MANIFEST 钉 commit）+ m0 补丁集 + PP-OCR 模型——GitHub Actions ARM64 runner 构建。
- **提权**：shizuku-m（官方 v13.6.0 fork，用户自装，不内置）。
- **控制面/OCR**：桥代理五端点（ping/screencap/click/swipe/shell）；in-proc PP-OCR + rpc.py shim。

## 运行与构建

### 主 App（`app/`，阶段二起）

```bash
export JAVA_HOME='D:\VSCodeCache\shizku-m\build-env\jdk-17.0.2'
export GRADLE_USER_HOME='D:\VSCodeCache\maa-alas\.tmp\gradle-home'
cd app && cmd //c 'gradlew.bat assembleDebug --console=plain'
# APK → app/app/build/outputs/apk/debug/app-debug.apk
```

- SDK 由 `app/local.properties`（gitignored）指向 `C:\Users\da270\AppData\Local\Android\Sdk`（cmake 3.22.1 + ndk 28.2 齐）。
- 坑：dl.google.com 间歇握手断 → settings 已加 Aliyun 镜像（官方源兜底）；floatingx 的 compose 包必须显式声明 `floatingx-compose`（两坑详见 debug.md 2026-09-16 条目）。

### rootfs（阶段一）

- GHA workflow 手动触发（主仓需公开）；产物 `rootfs.tar.xz` + BUILD_MANIFEST。
- **交付基准 = v4 artifact**（run 34997038262，sha256 `b506a62e…745a`；含 cached-property 修复）。
- 真机部署链（M1-d 实证）：PC `repack-linkfree.py` 去硬链接重打包 → push → 设备 busybox tar 解 + `chmod -R a+x` → proot harness（nld loader + 显式 guest PATH + `-b /dev,/proc,/sys`）。

### Spike 工程（阶段〇，存档）

两条可复现流程都在 `spike/a-proot-exec/`：

```bash
export JAVA_HOME=/d/VSCodeCache/shizku-m/build-env/jdk-21.0.2          # 便携工具链（只读）
export GRADLE_USER_HOME="D:/VSCodeCache/maa-alas/.tmp/spike-a/gradle-home"
cd spike/a-proot-exec
./gradlew --no-daemon -Pspike.targetSdk=35 :app:assembleDebug
cp app/build/outputs/apk/debug/app-debug.apk dist/spikea-phantom-target35-debug.apk

bash run-device-ladder.sh AVAY025422002864     # Spike A：exec 阶梯（自动装/跑/收日志）
bash run-phantom-ab.sh A 600                   # Spike C：幻影查杀 A/B 轮（A|B|A2|B1|B2|L|final）
```

前置：`adb` 可达真机、`export MSYS_NO_PATHCONV=1`（细节与坑点见 `debug.md`）。
