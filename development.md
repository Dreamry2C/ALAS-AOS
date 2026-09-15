# Development

## 当前阶段

**阶段〇（Spike 验证）进行中**。开发宪法 `docs/roadmap-v3.md` 已定稿执行；已完成：

- **Spike A（PASS）**：APK 内 proot exec 真机实证 —— `spike/a-proot-exec/`（REPORT.md）。
- **Spike C（PASS）**：幻影进程查杀缓解真机复验 —— 同工程 PHANTOM 模式（REPORT-C.md）。

任何不清楚之处：先读 `docs/roadmap-v3.md`（开发宪法），再读 `handoff/` 最新文件。

## 仓库结构（现状）

- `docs/roadmap-v3.md` — 13 项已确认决策、阶段〇–五、风险登记、m0 平移清单。
- `spike/a-proot-exec/` — **阶段〇 Spike A/C 的独立最小 Android 工程**（`com.maaal.spikea`，纯 Kotlin/无 AndroidX，targetSdk 35/28 可变体）：jniLibs 放 Termux 二进制（proot/busybox）、迷你 rootfs 由 assets 落地；`run-device-ladder.sh`（Spike A 阶梯）、`run-phantom-ab.sh`（Spike C A/B 轮）、`tools/`（dynstr 改写、argv0 shim、探针源码）、`dist/`（APK + 全量真机日志证据）、`REPORT.md` / `REPORT-C.md`。
- `handoff/` — 跨对话接力（按时间取最新）。
- `m0-archive/` — m0 阶段全部成果归档：MaaFwApp fork（`vendor/MaaFwApp` @ b2b0f54）、Termux 补丁集与种子配置（`termux/`）、桥代理与 PP-OCR 模型（`spike/m0/`）、全部 devlog 与研究文档（`docs/`）。v3 的直接复用来源，平移清单见 roadmap-v3 附录 A。
- `.tmp/` — 临时文件（已 gitignore）。`.tmp/alas` 内有 ALAS 官方 master 部分克隆（blob:none），供查源码；`.tmp/spike-a/gradle-home` 为 Spike 构建用的 Gradle 缓存（复用 `shizku-m/build-env` 工具链，写目录留在本仓）。
- 根目录环境配置：`.editorconfig` / `.gitattributes` / `.gitignore` / `.node-version` / `.prettierrc.mjs` / `.vscode/` / `.kimi-code/`。

## 技术栈（规划，源自 v3）

- **Android App**：MaaFwApp fork 减法整理（Kotlin，Gradle，AGPL-3.0）——阶段二复活 m0 基线；保留特权进程（虚拟屏+截屏注入）、TCP 22300 桥（五端点）、WebView 容器、Shizuku 辅助。
- **rootfs**：Ubuntu ARM64 + Python 3 + opencv-headless + onnxruntime + ALAS 官方 master（Gitee 镜像，钉 commit）+ m0 补丁集 + PP-OCR 模型——GitHub Actions ARM64 runner 构建（主仓需公开）。
- **提权**：shizuku-m（官方 v13.6.0 fork，用户自装，不内置）。
- **控制面/OCR**：桥代理五端点（ping/screencap/click/swipe/shell）；in-proc PP-OCR + rpc.py shim。

## 运行与构建

Spike 工程（阶段〇）已有可复现构建/真机流程，两条都在 `spike/a-proot-exec/`：

```bash
export JAVA_HOME=/d/VSCodeCache/shizku-m/build-env/jdk-21.0.2          # 便携工具链（只读）
export GRADLE_USER_HOME="D:/VSCodeCache/maa-alas/.tmp/spike-a/gradle-home"
cd spike/a-proot-exec
./gradlew --no-daemon -Pspike.targetSdk=35 :app:assembleDebug
cp app/build/outputs/apk/debug/app-debug.apk dist/spikea-phantom-target35-debug.apk

bash run-device-ladder.sh AVAY025422002864     # Spike A：exec 阶梯（自动装/跑/收日志）
bash run-phantom-ab.sh A 600                   # Spike C：幻影查杀 A/B 轮（A|B|A2|B1|B2|L|final）
```

前置：`adb` 可达真机、`export MSYS_NO_PATHCONV=1`、`local.properties` 的 `sdk.dir` 指向便携 SDK（细节与坑点见 `debug.md`）。主 App（阶段二起）的构建命令待阶段一/二补充。
