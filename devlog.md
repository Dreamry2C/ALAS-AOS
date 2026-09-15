# Devlog

> 倒序排列，最新在上；按发版版本号分段。

## 未发版

### 2026-09-15 · 阶段〇 Spike C：幻影进程查杀缓解真机复验（PASS）

- 结论：m0 产品化的两条命令在 Android 16 / MagicOS 10 上**仍然有效，且任一条单独生效**；详见 `spike/a-proot-exec/REPORT-C.md`。
  - `settings put global settings_enable_monitor_phantom_procs false` —— 关掉"扫描+记帐+裁剪"整条链（AMS 连幻影记录都不建），**推荐主手段**。
  - `device_config put activity_manager max_phantom_processes 2147483647` —— 只把裁剪阈值顶到天花板，**副手段**。
  - 两条命令本机均可写、无告警（`exit=0` 无输出），`dumpsys activity settings` 立即生效。
- 真机证据（HONOR PPG-AN00 / Android 16 / SELinux Enforcing）：
  - **对照（默认配置，3 轮）**：App 自己 fork 的 proot 树 51 个进程，被 AMS 成批 SIGKILL 掉 20 个（`Trimming phantom processes`，19 busybox + 1 `libproot.so`），压回 31；proot tracer 一死，guest 存活上报中断（`PROOT_EXIT=137`）。三轮命中时刻 **+29s / +43s / +267s**。
  - **缓解（两条都开，35 分钟）**：48 个 guest 长命进程 + proot + sh 全程零伤亡、`Trimming phantom` 零命中（跨 ~7 个节拍）。
  - **可分性**：只开 flag（B1）或只开 cap（B2）各 420s（跨 ≥1 节拍）均全存活；m0 时代两个旧键（`settings_config_disable_monitor_phantom_procs` / `phantom_process_killer_enable`）**无效**——开跑 2 秒即被裁。
- 机制发现（写进 REPORT-C §2，供阶段三参考）：
  - 裁触发点是 **AMS 的 5 分钟节拍**（`CHECK_EXCESSIVE_POWER_USE_MSG` / `POWER_CHECK_INTERVAL`）→ `AppProfiler.updateCpuStatsNow()` → `PhantomProcessList.updateProcessCpuStatesLocked()`；超额子进程最长能活 ~5 分钟才被**整批**收割（**存活实验窗口必须 ≥1 个节拍**，否则把"还没到节拍"误判成"没被杀"）。
  - 配额是**全系统**的（A2 轮实测连坐杀掉 `com.hypergryph.skland` 的幻影，52 − 20 = 32 与配额吻合）。
  - 「幻影」判定 = 读 **App 主进程的 cgroup**（`/sys/fs/cgroup/apps/uid_<uid>/pid_<pid>/cgroup.procs`）；App 自 fork 的树必然计入，Shizuku/shell 域拉起的树不进该 cgroup（同 uid 也不算）。
- 交付：`spike/a-proot-exec/`（MainActivity 新增 PHANTOM 模式 + `run-phantom-ab.sh` 逐轮编排 + `dist/spikea-phantom-target35-debug.apk` + `dist/logs/phantom-*` 全量证据 + REPORT-C.md）。
- 新坑入 `debug.md` 5 条：guest rootfs 缺 `/dev/null` 导致后台作业全灭（且脚本里的 `2>/dev/null` 会造出伪 null 掩盖问题）、toybox grep 不认 `\|`、cgroup.procs 是幻影计数权威口径、proot tracer 被杀后的孤儿 `am force-stop` 收不掉、5 分钟收割节拍陷阱。
- 结束状态：两条缓解命令保持开启（生产态）；实验前见到的两个旧键已恢复原值；`stay_on_while_plugged_in` 已还原为 0。

### 2026-09-15 · 阶段〇 Spike D：ALAS 进程管理 import 面探查（PASS，报告落库）

- 报告全文：`docs/spike-d-wrapper-surface.md`（基线 `.tmp/alas` @ d816310，官方 master）。
- wrapper 主线定型：**不碰 WebUI 的 `ProcessManager`**（multiprocessing 内嵌、state 靠日志文本判定、漂移风险高），采用「薄 runner.py 子进程 import `AzurLaneAutoScript.loop()` + wrapper 管进程组（killpg；ALAS 无 SIGTERM handler，`ProcessManager.stop()` 本身就是 kill）」；兜底=完全不 import（`python alas.py` / `-c` 单行 + 原子写 `./config/<name>.json` + killpg），已证实可行、所需信息齐全。
- 衍生设计点（留阶段三）：**调度器双头管理风险**——WebUI 启停按钮走 ProcessManager，悬浮窗走 wrapper，双跑会抢设备。候选解：wrapper 同进程起 uvicorn(WebUI) + sidecar 薄 HTTP 直调 `ProcessManager.get_manager(name)`（与 WebUI 按钮同对象、状态一致）；兜底接受 WebUI 启停按钮失效并文档警告。
- 更新器锁定七键（`AutoUpdate:false`/`InstallDependencies:false`/`EnableReload:false`/`CheckUpdateInterval:0`/`AutoRestartTime:null`/adb 三键 false）+ 暗路径清单：`KeepLocalChanges` 键在 master **不存在**；唯一 pip 执行点 `deploy/pip.py:153`；`git reset --hard` 会丢本地补丁 → `AutoUpdate:false` 是唯一闸门；`updater.schedule_update()` 无条件挂载，须 `AutoRestartTime:null` 自删。阶段一 rootfs 构建直接照用。
- 环境事实：无头跑也必须能 import pywebio（`config.py` 模块级 import 并猴补丁）；Python 3.14 默认 forkserver 对 WebUI multiprocessing 路径有中风险，runner 方案天然绕开；ALAS 全仓无 Python 版本断言。

### 2026-09-15 · 阶段〇 Spike A：APK 内 proot exec 真机实证（PASS，唯一生死线探针）

- 结论：**targetSdk 35 上可行，无需降级**；targetSdk 28 变体全绿保留为后备。详见 `spike/a-proot-exec/REPORT.md`。
- 设备实证（HONOR PPG-AN00 / Android 16 / 4KB 页 / SELinux Enforcing）：
  - `libproot.so`、busybox stub、proot loader、静态 shim 全部可从 `nativeLibraryDir` 直接 exec；proot ptrace 引擎正常（`PROOT_PTRACE_OK`）。
  - `proot -r <filesDir>/rootfs` 可运行 rootfs 内 busybox（多合一）、静态 ELF、动态 ELF，**含客户机内再 `execve` 子进程**——targetSdk 35 全部 PASS（debug 与 release 构建均复现）。
  - 唯一被拦的是 app 进程直接 `execve(filesDir/...)`：35 报 `error=13 Permission denied`，28 允许（预期语义，非缺陷）。
- 工程发现（已固化到 spike 工程与 debug.md）：
  - AGP 与安装器都只认 `lib*.so` 命名；Termux 二进制的版本化 SONAME（`libtalloc.so.2`、`libbusybox.so.1.38.0`）必须做 dynstr 原地改写（新工具 `spike/a-proot-exec/tools/patch-dynstr.py`）。
  - Termux busybox 1.38 是 4KB stub + `libbusybox.so.1.38.0` 载荷；applet 由 `argv[0]` 选择，从 nld 执行需 argv0 shim（`libspike_shim.so`）。
  - `proot -r` 的 rootfs 需自包含：解释器副本必须 +x（否则报 `execve: Permission denied` 极易误判为 SELinux 拦截）；客户机动态库需完整传递闭包。
  - 16KB 页：本机 4KB；全部随包 ELF 的 `PT_LOAD` 对齐 0x4000，`zipalign -c -P 16` 三份 APK 全通过。
- 交付：`spike/a-proot-exec/`（工程 + `dist/` 三份 APK + `dist/logs/` 全量原始证据 + REPORT.md）。
- 未覆盖（留阶段一/五）：真实 Ubuntu rootfs（glibc 解释器分支）复验、长时稳定性、多 ROM 抽检、正式签名后 nld 清单复核。

### 2026-09-15 · 路线图 v3 定稿（三轮设计拷问）

- 产出 `docs/roadmap-v3.md`（v2 的修订版，13 项已确认决策见该文第 0 节）。核心变更：
  - **后台挂机 = 硬需求** → 控制面保留 m0 桥（adb 无法触达虚拟屏，m0 实证 `m0-archive/docs/debug.md:281-285`）；v2 的 adb 四步流水线整体降级为 Spike E 探索项。
  - Spike 清单重排为 A/B′/C/D/E/F，唯一生死线 = Spike A（APK 内 proot exec，有 targetSdk 28 兜底）。
  - OCR 走 m0 备案"C 路线"转正：rootfs 内 onnxruntime + PP-OCR，libMaaCore 业务引擎正式剔除。
- 关键事实核查：
  - shizuku-m = 官方 Shizuku v13.6.0 fork（3 commits），机制为 `tcpip:5555` 通道 + RSA 预授权；**跨开机仍需一次在线激活**（persist 属性被 SELinux 拒），同一开机周期内可离线秒拉起。
  - "fullcn 版 ALAS" = 官方 Releases 的大陆变体（`AlasApp_0.4.10_fullcn.7z`），与官方 master 同架构，差异仅国内镜像源配置；rootfs 取"官方 master 钉 commit（Gitee 镜像）+ fullcn 同款镜像 deploy 配置"。
- 用户决策：shizuku-m 不内置进 APK，README + 应用内引导自装；仓库公开后置（例外：阶段一主仓单独公开，GHA ARM64 runner 免费仅限公共仓）。
- 状态：**等用户确认 v3**，确认后进入阶段〇。
