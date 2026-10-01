# Development

## 当前阶段

v3 主线已完成阶段三、阶段四应用内实现，阶段五验证进行中。当前任务及未完成项以 `.local/dev/handoff/2026-10-01-astra-handoff.md` 为准，历史进度查 `.local/dev/devlog.md`，本文件不重复维护任务流水。

运行期采用原版 cnocr 1.2.2 + mxnet 1.9.1 + azur_lane 模型，后台虚拟屏模式。旧路线图中的 PP-OCR/前台说明属于历史决策，下列结构与技术栈按现状维护。

- 开发宪法：`docs/roadmap-v3.md`（13 项决策、阶段〇–五、风险登记）。
- 阶段二工作底稿：`docs/stage2-maafwapp-inventory.md`（减法三栏清单 / 新桥设计 / VD flag 核查）。
- 任何不清楚之处：先读 roadmap，再读 `.local/dev/handoff/` 最新文件（当前 `2026-10-01-astra-handoff.md`）；详细动作与任务计划查交接所指的单份 live.md。

## 仓库结构（现状）

- `app/` — 阶段二/三主战场：MaaFwApp fork 复活副本（b2b0f54 + m0 WebView 6 处改动固化 + 构建修复）。阶段三新增：
  - `app/src/main/java/.../provision/`（首启 rootfs 解压，M3-a）与 `.../proot/`（ProotHost 会话宿主 / AlasOverlay 资产覆盖 / AlasUpdater 热更新，M3-b）。
  - `app/src/main/prootLibs/arm64-v8a/`（proot 九件套，Spike A 钉版入库）+ `app/src/main/assets/alas/`（wrapper/runner/seed/alasaos_update.sh/rpc.py + patches 全量，运行时幂等铺 /opt/alas）。
  - `app/src/main/assets/rootfs/`（rootfs.tar.xz 随包，gitignore 不入库；BUILD_MANIFEST 入库）。
- `rootfs/` — `build/build-rootfs.sh`（GHA ARM64 构建脚本）、`patches/`（ALAS 适配补丁，含桥客户端）、`overlays/`（wrapper.py / alasaos_gui.py / alasaos_control.py / alasaos_u2.py；runner.py 为旧入口，当前不使用）、`seeds/`（deploy.yaml / seed_config.py / seed_deploy.py / sync_deploy.py / alasaos_update.sh 等）。运行资产在 `app/app/src/main/assets/alas/` 有对应副本，修改须同步。
- `alasaos_gui.py` — AOS 自有入口，预加载 adbutils 后运行原版 gui.py，规避换源后 fake PIL 导入顺序冲突；原 TaskHandler.stop 保护也在入口内存适配。退役的 utils.py 整文件覆盖由 env_fix 恢复当前源原版，避免冻结新分支图标和接口；不修改上游业务逻辑。EnableReload=true 时 wrapper 管 GUI 父进程，父进程管理实际 WebUI 子进程，WebUI 另有 multiprocessing.Manager 共享状态进程；它们并非多套挂机。任务由 ALAS 原生 ProcessManager 创建，AOS 不再启动独立 runner 或强制重拉任务。
- `alasaos_control.py` — GUI子进程内的loopback控制适配（22401）；AOS 22400转发到它，两端共用原版ProcessManager的启停与状态。日志只取当前实例原生文件，GUI诊断单独保留；Rich15 HTML日志空输出通过公开Console API内存适配。
- `alasaos_u2.py` — 桥接serial不是ADB transport；允许未使用的可选u2对象构造，实际uiautomator2 RPC明确报不支持，普通serial仍走原库。截图/输入/普通shell走连接桥。
- 主Activity固定竖屏；点游戏预览时临时横屏，退出恢复竖屏，不修改整台手机的旋转偏好。
- 就绪检查超时明确显示原因，后台继续检测同一会话；服务迟到恢复后转为RUNNING，避免永久停在“准备中”。
- `seed_deploy.py` 每次启动校正 EnableReload；`sync_deploy.py` 在更新成功/最新时同步 Repository/Branch。更新器按源/分支散列记录尝试，保留远端引用，以真实 HEAD 验证本地代码；Force restart 只重启 WebUI，AOS 重启才执行换源和 overlay 铺设。
- ProotHost 的长会话和短命令均把 app 私有 `files/proot-tmp/shm` 绑定为 guest `/dev/shm`，支持 Python multiprocessing 信号量；会话清理沿用 proot-tmp。
- `.github/workflows/` — rootfs 构建 workflow（手动触发；`ALAS_REF` 默认 master 浮动，manifest 记录解析后 commit）。
- `docs/` — `roadmap-v3.md`、`stage2-maafwapp-inventory.md`、`spike-d-wrapper-surface.md`。
- `spike/` — 阶段〇交付：`a-proot-exec/`（Spike A/C 工程+报告）、`e-adb-virtual-display/`（Spike E/B′）。
- `m0-archive/`（gitignore，本地只读）— m0 全部成果归档：MaaFwApp fork、termux 补丁/种子、桥代理、OCR 模型、m0 devlog。
- 本地账册（`.local/dev/`，不入 Git）：`.local/dev/devlog.md`（倒序流水）、`.local/dev/debug.md`（坑与解法）、`.local/dev/handoff/`（跨对话接力，取最新）。
- `.local/dev/`（gitignore）— devlog/debug/handoff/live/TODO，保存本机开发记录；不作为可删除缓存。每项连续任务只用一份含目标、计划、断点与即时结果的 live.md。缺少本地记录的新克隆从本文件/roadmap/Git 历史恢复项目结构。
- `.tmp/`（gitignore）— 构建缓存、测试原始输出和历史证据包；清理前保留 live 所引用的必要恢复证据。历史临时脚本可能硬编码旧日志路径，复用前改成 `.local/dev/live/`。

## 技术栈（现状）

- **Android App**：MaaFwApp fork 减法整理（Kotlin，Gradle，AGPL-3.0）——保留特权进程（虚拟屏+截屏注入）、TCP 22300 桥（五端点，Kotlin 重写）、WebView 容器、Shizuku 辅助。
- **rootfs**：Ubuntu 24.04 ARM64 + Python 3.12 + numpy 1.26.4 + opencv-headless 4.10.0.84 + cnocr 1.2.2 / mxnet 1.9.1，原版 azur_lane 模型；ALAS 官方 master 烘焙，运行时可在设置中换源/分支。由 GitHub Actions ARM64 runner 构建，精简产物约283MB。
- **提权**：shizuku-m（官方 v13.6.0 fork，用户自装，不内置）。
- **控制面/OCR**：桥代理五端点（ping/screencap/click/swipe/shell）；原版 cnocr 特调模型，UseOcrServer=false；PP-OCR 已退役。

## 运行与构建

### 主 App（`app/`，阶段二起）

```powershell
$env:JAVA_HOME='E:/GitRepository/Moontier/.build-tools/jdk17/jdk-17.0.16+8'
$env:GRADLE_USER_HOME='E:/GitRepository/ALAS-AOS/.tmp/gradle-home'
$env:TEMP='E:/GitRepository/ALAS-AOS/.tmp/build-tmp'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
& '.tmp/gradle-dist/gradle-9.4.1/bin/gradle.bat' -p app :app:assembleDebug --offline --no-daemon --console=plain
# APK → app/app/build/outputs/apk/debug/app-debug.apk
```

- 2026-10-01 本机验证的 SDK：`app/local.properties`（gitignored）指向 `E:/GitRepository/Moontier/.build-tools/android-sdk`；复用现有 JDK/SDK，不修改外部工具链。旧机器的 da270 SDK / shizku-m 便携工具链是备用历史路径，使用前确认存在。
- versionCode 按 Git 提交计数，versionName 按 tag 距离生成。同一未提交工作区可多次构建出相同版本号，调试安装以 APK SHA256 区分，不用旧版本号推断已安装哪份代码。
- 坑：dl.google.com 间歇握手断 → settings 已加 Aliyun 镜像（官方源兜底）；floatingx 的 compose 包必须显式声明 `floatingx-compose`（两坑详见 .local/dev/debug.md 2026-09-16 条目）。

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

前置：`adb` 可达真机、`export MSYS_NO_PATHCONV=1`（细节与坑点见 `.local/dev/debug.md`）。

## Git 分支与本地记录

`main` 仅同步 `upstream/main`（Shinarin/ALAS-AOS），开发在 `alas-aos`，推送到 Dreamry2C/ALAS-AOS 的同名分支。开发日志/坑点/交接/现场记录集中在 `.local/dev/`，不随仓库克隆传播；后续功能清单见本地 `.local/dev/TODO.md`。公共结构与发布文档仍正常版本管理。
