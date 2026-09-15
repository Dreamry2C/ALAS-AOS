# Devlog

> 倒序排列，最新在上；按发版版本号分段。

## 未发版

### 2026-09-16 · M4-a 收官 ✅：悬浮窗直连 wrapper 薄 HTTP —— 调度器状态行 + 开始/停止挂机 + 半透明日志板

- **代码**：`proot/AlasRunController.kt`（新）——4s 轮询 wrapper 薄 HTTP（GET /status → reachable/runnerAlive/pid/guiAlive/logLines；POST /start、/stop（busy 置位，读超时 12s 覆盖 SIGTERM→3s→SIGKILL）；GET /logs?tail=80 纯文本），Koin 单例挂 `postCreate` 全程轮询，Mutex 互斥刷新。`OverlayPanel` 改版：三行环境状态 + 「ALAS 调度器」状态行（环境未就绪/运行中·pid/已停止）+ 半透明黑底日志板（Monospace 10sp/行高 13，`LaunchedEffect(linesCount, lines.size)` 自动沉底，空显「暂无日志」，weight(1f) 吃满剩余）+ 全宽「开始挂机/停止挂机」（enabled=reachable && !busy，按 runnerAlive 切换）+ 原「回到应用/环境启停」行。字符串七键 ZH/EN 同步；DI：prootModule 注册 controller、OverlayModule 注入、MaaFwApp.postCreate `start()`。
- **双头管理决策（roadmap 阶段四遗留）定案**：**不做 Spike D 的 in-proc uvicorn 重构**——gui.py 独立 + wrapper runner 的链路已全绿，重构改动已验证链路风险大于收益。悬浮窗=唯一控制面；WebUI 启停按钮（走 ProcessManager，与本通道并存双跑会抢设备）「不要用」，先写文档警告（AlasRunController 头注，README 待写），阶段五再评硬化（如 WebUI 按钮屏蔽补丁）。
- **真机验证（HONOR PPG-AN00）**：装包重开 → 环境自动起（VD #15、桥通、球出）→ 点球面板渲染全对——调度器「已停止」与 curl /status（runner_alive=false）一致；日志板从「暂无日志」（首版策略=runner 活着才拉）改为**可达即拉**后真实日志上板（gui 日志 `<<< RESTART ALAS >>>`、`Start alas complete`、`[Server] cn` 等，与 /status 的 log_file 相符）；关面板球复活。**「开始挂机」未按**（会真拉起 ALAS 操作游戏，端到端留用户在场演示）。
- **新坑入 debug.md**：wrapper /status 时间戳是 guest 本地时（proot 无 TZ=UTC），比设备 CST 慢 8h——首读 gui_started_at 误判「旧会话逃过重装」，ps 进程树（proot 父=新 app pid）才定案。

### 2026-09-16 · M3-c 收官 ✅：生命周期防护压测全绿（杀 Java 进程 ≤3s 全树自尽）+ 重启引导文案对齐决策 #11

- **划卡归零正赛（DoD 核心项）**：`run-as kill <appPid>` 只杀 Java 进程（模拟最近任务划卡的最坏面——native 子树不随包名被杀），**≤3 秒内 proot/wrapper/gui 全灭**——stdin 管道 EOF → wrapper 监控线程 `_cleanup` → 杀 runner+gui 双进程组 → proot tracee 尽失退出。叠加 M3-b 的 `am force-stop` 零残留（uid 级全杀），两条死亡路径都闭环。
- **重启引导（roadmap 阶段三第 5 条）**：机制沿用 M2-d readiness 弹窗（NotRunning→打开 shizuku-m→NeedAuth→请求授权→自动 bind 建屏，当时 DoD 已实证）；本次把 NotRunning 文案从通用「打开 Shizuku 启动服务」升级为**决策 #11 的每次开机 30 秒手动链**（「每次重启手机后都需要重新激活：打开 shizuku-m 点『启动』（无需连接 WLAN 或电脑），启动成功后返回本应用即可自动继续」，EN 同步）。**真机重启端到端验证待用户授权**（不私自私下重启手机）。
- **结论**：阶段三 DoD 中「划掉 App 无残留 Python/proot/桥进程」✅；「开屏热更新→外部浏览器开 22267」✅（M3-b）；「重启手机经引导恢复可挂机状态」=机制+文案落地，实测待用户。

### 2026-09-16 · M3-b 收官 ✅：FGS 拉 proot + 自愈清锁 + 热更新（快进路径）+ wrapper 监管 WebUI 真机全绿

- **链路（roadmap 阶段三第 3 条全落地）**：AppRoot 侦测 Provision Ready → `proot/ProotHost`（新包）→ 自愈清锁（proot-tmp 整目录重来 + .git/*.lock + reloadalas）→ 写死 DNS（`etc/resolv.conf` 烘焙是悬空软链，删链写 AliDNS）→ `AlasOverlay`（资产 `alas/` 按字节幂等铺 /opt/alas）→ seed_config（maaal 桥配置播种 alas.json）→ `AlasUpdater`（proot 内跑 `seeds/maaal_update.sh`）→ ProcessBuilder 拉起 `libproot.so … python3 wrapper.py` 长跑会话。
- **热更新设计定型**：`/opt/alas` 烘焙时 `.git` 被剔除（build-rootfs.sh:277），首次更新=git init + fetch；脚本协议 `UPDATED/UNCHANGED/FAILED` 三态单行，App 降级不阻塞。**ls-remote 快进路径**（先 60s `git ls-remote` 取远端 HEAD，一致则零下载）——真机二启 **5 秒** 到 wrapper 就绪（对比首跑深度 fetch 83KB/s 撞 240s 超时，见 debug.md 新坑）；首次真更新降级为 `--depth 1` 单提交树。UPDATED 后 App 重放 overlay（patches/module + patches/assets + rpc.py）+ 重跑 assets_fix（幂等 + 漂移自检，Button 找不到非零退出→警告"建议重下整包"不阻塞）。
- **wrapper.py 升格为 WebUI 监管者**：spawn gui.py 子进程（独立进程组，输出 → `log/gui.out`），崩溃自动重拉（退避 5s→60s，活过 5 分钟复位），`_cleanup` 先置 `_closing` 再杀 runner+gui 双进程组；`/status` 增 gui_alive/gui_pid。stdin 管道破裂自尽链路不变（M3-c 正赛）。
- **FGS 语义扩展**：RunForegroundService 观察 HostState.snapshot **combine** ProotHost.state——虚拟屏在**或** proot 会话活跃（PREPARING/UPDATING/STARTING/RUNNING）即钉前台；新增通知文案「内置 ALAS 环境运行中（未建虚拟屏）」。
- **真机验证（HONOR PPG-AN00）**：首跑热更新超时降级→会话照常起；二启 5s 快进（`.maaal_alas_commit`=92c07aa 与远端一致）；wrapper `/status` gui_alive=true；WebUI 22267 HTTP 200（PyWebIO 页）；config/alas.json 桥配置五键正确；FGS id=1001 在岗；**`am force-stop` 后 proot/python/gui 零残留**（DoD 划卡项提前实证）；杀掉 gui 后 wrapper 10s 退避重拉成功（新 pid，WebUI 复 200）；**WebView 开屏自动载入 ALAS 控制台**（截图 `.tmp/m3b-screen2.png`）。
- **工程修正三则（均入 debug.md）**：① RUNNING 语义必须=wrapper+WebUI 双端口可达，否则 WebView 自动重载抢在 uvicorn import 前几秒吃 connection refused 卡死错误页；② jniLibs 被 app/.gitignore 排除（MaaFramework 拉取件规则）→ proot 九件套移 `src/main/prootLibs/` + sourceSets srcDir 入库；③ adb 安装链 `install | tail && …` 的退出码是 tail 的（失败被吞）+ adb 只吃 Windows 路径。
- **jniLibs 九件套入库**（`app/app/src/main/prootLibs/arm64-v8a/`，3.9MB，Spike A 钉版：libproot/libproot-loader/libtalloc/libbusybox(+_app)/libspike_shim/libandroid-selinux/libandroid-shmem/libpcre2-8）。
- **双头管理（WebUI 启停按钮 vs wrapper/悬浮窗）按 Spike D 建议留阶段四决策**，devlog 与 wrapper docstring 均已标注；M1-d harness 后台任务已停（22267 让位生产会话），油数验收改走生产链。

### 2026-09-16 · M3-a 收官 ✅：首启 rootfs 解压流水线（进度条门）真机全绿 + 幻影键修正

- **代码（`f8d8cbe`）**：`provision/RootfsProvisioner`（状态机 Checking/NotBundled/LowDisk/Extracting/Ready/Failed）+ `ui/setup/ProvisionScreen` + AppRoot 门（未 Ready 整屏接管，开发包未内置可跳过）+ `di/ProvisionModule`。真机：~90s 解出 971MB（315MB 压缩包），进度条平滑，二启秒过门。
- **险些出货的大坑（已入 debug.md）**：解压目标最初写 AppPaths.ROOT（getExternalFilesDir=/sdcard）——/sdcard 模拟存储**不支持符号链接**（ubuntu-base 740 个）且 noexec，Spike A 实证 proot 可用的位置是**内部 filesDir**。提交前自查拦下。
- **解压技术选型**：busybox tar 解 ubuntu-base 硬链接前向引用必炸（M1-d 坑②）→ commons-compress + tukaani xz 纯 Java 流式解；符号链接 `Os.symlink`（实测 740 全数落地）、硬链接物化副本（前向引用解完兜底）、可执行位保留（python3→3.12 `-rwx--x--x`）、zip-slip 防护、256KB 节流进度（openFd 读真实长度，noCompress+xz 已配）、≥2GB 磁盘校验。
- **版本闸门**：assets 侧 `rootfs/BUILD_MANIFEST`（入库，678B）vs marker `.provisioned`（实测写出 0.1.0）；升级=换新包重解。rootfs.tar.xz 随包内置（gitignore，APK 392MB）——一键安装符合决策 #3；Gitee Release 100MB 附件上限放不下，分发走 GitHub Release。
- **幻影键修正**：`PermissionGrantHelper.disablePhantomProcessKiller` 原来是 m0 时代两旧键（Spike C 实测**无效**：`settings_config_disable_monitor_phantom_procs`/`phantom_process_killer_enable`）+ 有效副手段；已换成 Spike C 实证对（`settings_enable_monitor_phantom_procs false` 主 + `device_config max_phantom_processes 2147483647` 副），设备侧 `settings get` 双双确认写入。
- **遗留**：部署页期间 HostState 并行起 VD/球（可接受，阶段四再评）；M3-b = FGS 拉 proot（libproot.so 进 jniLibs）+ 自愈清锁 + Gitee 热更新 + wrapper。

### 2026-09-16 · M2-d 收官 ✅：HostState 脱钩 + DoD 真机验证 6/6 + 悬浮球消失之谜定案

- **代码（`8c02157`）**：新建 `service/HostState.kt`（快照=特权连接+桥可达+vdDisplayId；environmentUp=桥通且屏在；4s 裸 socket ping 22300 探测；ensureEnvironmentStarted=bind→setup→startVD→FGS 一键链；stopEnvironment=stopVD）+ `di/HostModule.kt`；OverlayController/OverlayPanel/FloatBall/RunForegroundService 全脱钩 RunnerPort（StubRunnerPort/RunnerContracts 删除）；AlasScreen 错误页改「重试连接」；NotInstalled 档改「我已安装，重新检测」+ shizuku-m 自装引导文案。
- **DoD 真机验证 6/6（HONOR PPG-AN00，竖屏 1264×2800，shizuku-m 在线）**：
  1. ✅ Shizuku 权限链路：NotRunning→点 shizuku-m「启动」→NeedAuth「请求权限」→系统弹窗「始终允许」→全自动 bind→setup→VD→FGS→桥→悬浮球。
  2. ✅ VD 创建：display 动态分配，flags=PRESENTATION|OWN_CONTENT_ONLY|DESTROY_CONTENT_ON_REMOVAL|TRUSTED|OWN_DISPLAY_GROUP|ALWAYS_UNLOCKED|TOUCH_FEEDBACK_DISABLED|OWN_FOCUS|STEAL_TOP_FOCUS_DISABLED（**无** SHOULD_SHOW_SYSTEM_DECORATIONS），owner shell uid2000；**手势三窗口全程 displayId=0**。
  3. ✅ 桥五端点（adb forward + PC python 冻结协议客户端）：PING/SHELL(uid=2000)/SCREENCAP(恰 1280×720×3=2764800B)/UNKNOWN 错误帧全对。
  4. ✅ WebView 渲染**真实 ALAS PyWebIO GUI**（harness WebUI 22267 供）。
  5. ✅ 悬浮球自动出现（绿球呼吸）+ FGS 通知在岗（ONGOING|PROMOTED_ONGOING）。
  6. ✅ 面板全生命周期：点球→面板开（球隐）；「停止环境」→ VD 毁+球隐+面板转「启动环境」；「启动环境」→ VD 重建；关面板（X）→ 球复活。
- **悬浮球消失之谜定案（非 bug，系统机制）**：当 `android.settings.SETTINGS` 开在 **VD** 上时，HONOR ROM 把 `hideOverlayWindows` **全局**应用于所有 display——主屏悬浮窗被策略性强隐（`mPolicyVisibility=false mForceHideNonSystemOverlayWindow=true`，视图仍 VISIBLE）。且 flag **粘性**：Settings 死后不自动复评，需一次前台应用切换（home→回 app）触发重估才恢复。游戏无此属性（游戏前台时球实测存活 ✅），生产无影响。已入 debug.md。
- **顺带修复（`728dff6`）**：面板经「启动环境」重建 VD 后球会压在面板上——observeHost 在 showControl 前查面板在屏则跳过。真机回归：停止→启动→球保持隐 ✅ → 关面板→球复活 ✅。
- **事故披露**：验证"游戏前台球存活"时 monkey 把游戏起到主屏（`--display` 被忽略）→ 主屏转横屏；后续两次按竖屏坐标的 tap 越界被钳到屏幕边缘（未触达有效 UI）；游戏进程随后被发现已退出（登录页，无进度损失；死因未能归属到具体操作，倾向系统回收/游戏自身）。教训入 debug.md（点击前先核旋转与坐标）。
- **空 VD 注入语义（留档）**：空 VD（无窗口消费）上 click/swipe 回 `touch down failed` 非链路坏——WAIT_FOR_FINISH 模式无消费者 natively 返 false（`input -d 2 tap` 同静默 false）；VD 上有窗口（Settings）后 CLICK/SWIPE 均 ok。生产语义正确（游戏常驻 VD）。
- **清场 ✅**：面板停环境 → force-stop → 只剩 display 0、maafw 窗口 0、手势三窗口 displayId=0、无活动通知。
- **遗留**：① M1-d 油数验收仍等用户把游戏点到出击菜单页（游戏现已退出，需重开）；② appId 身份（`com.aliothmoon.maafw`→MaaAL 命名）待用户定夺；③ AppSettings 死 pref、`runner/DisplayResolution.kt` 包名不副实，留阶段三。

### 2026-09-16 · M2-c 收官 ✅：特权进程内 Kotlin 重写 m0 桥（TCP 22300，5 端点）

- **`BridgeServer.kt`（368 行新增）+ JNI 裸帧出口**，commit `05164f8` 已 push。m0 Python Agent 桥（`m0-archive/spike/m0/agent/main.py`）由特权进程内 Kotlin 服务整体替代，协议与冻结客户端 `rootfs/patches/module/device/method/maaal.py` 逐点兼容。
- **协议对照**：行分隔 JSON + screencap 响应行后随裸帧；每回复（含错误帧）echo 请求 id；ping/screencap/click/swipe/shell 五端点（ocr 按 roadmap 剔除，ALAS 改走 in-proc PP-OCR）；shell 剥 `LD_LIBRARY_PATH` + PATH 前缀 + stdout/stderr 各 64KB 上限（超限照读照丢防管道死锁）+ 超时 `destroyForcibly`；请求行 64KB 防呆；per-client daemon 线程。
- **screencap 直通 native**：新 JNI `getFrameBufferBytes()` 走 `GetLockedPixels/UnlockPixels` 读者锁（持锁压到一次 memcpy）；帧缓冲原生 **BGR 3ch** 正是 m0 线上格式（客户端 `[:3][::-1]` 翻 RGB）；尺寸经 `VirtualDisplayManager.getConfig()` 交叉校验，防 VD 重启半途发错尺寸帧。
- **注入**：`InputControlUtils.down/move/up(contact 0, displayId)`，displayId 每请求现取（VD 重建不僵）；click=down→50ms→up；swipe 绝对时间轴线性插值（~16ms/步，步数 max(1,duration/16)），x1==x2 自然退化长按；**move 失败也补 up**——悬着的 ACTION_DOWN 会劫持 VD 触摸直到 VD 重启（直注路径必须自己兜，m0 由 controller 内部兜底）。`setContactSupport(false)` 在 start() 防御性调用（原调用点 MaaRunner.prepare 已删）。
- **生命周期**：`RemoteServiceImpl.init` 启动（ctor 不抛铁律→runCatching）、`cleanup()` 停止；`isRunning()` 预留 M2-d FGS 状态源。
- **评审记录**：DEVICE_LOCK 有意扩到整段（含 2.7MB 发帧，loopback <10ms；m0 只锁 controller 段——soak 见卡顿再议）；半帧 desync 与 m0 同疾（客户端 reconnect-retry 重同步）；畸形请求错误文本与 m0 有出入（冻结客户端永不产生，形状一致）。
- 构建绿（BUILD SUCCESSFUL，CMake 重编过）。真机 ping/screencap/建屏验证属 M2-d DoD。

### 2026-09-16 · M2-b 减法收官 ✅：剔除 MaaCore/PI/定时任务/推送业务管线，宿主外壳收敛，构建绿

- **终验 BUILD SUCCESSFUL**（3s，103 tasks）。APK `app-debug.apk` 80,972,217 → **80,958,388 B**（−14KB；debug dex 未压缩 + fork clone 基线本就不含 jniLibs，包体大头是三方库不是业务码，降幅小属预期）。全 dex 抽查：16 个被删类 0 命中，保留类（StubRunnerPort/RemoteServiceImpl/RunForegroundService 等）在。
- **刀①构建系统**：删 `app/macrobenchmark/`；build-logic 删 PiAssets/AgentRuntime 两 Convention 插件；app 模块去两插件 id + baselineProfile + jna/sentry/markwon/angus.mail/jakarta.activation/reorderable 依赖（okhttp/tracing 按底稿 §七保留）；proguard 删 JNA/markwon/SMTP 段，R8 关键类清单删 maa 两条。
- **刀②业务包整删**：`maa/ project/ schedule/ notification/ telemetry/ session/`；remote 删 MaaRunner/ExecAgentHost/AgentInstaller/AgentRuntimeDescriptor（AgentHost 连锁）；log 删 RunLogArchive/Detail；di 删 Notification/Project/ScheduleModule；`assets/shizuku.apk` + ShizukuInstallHelper + 两个构建脚本（setup_maa_framework/build_agent_bundle）删。
- **刀③留壳改造**：RunnerPort 接口原样保留（RunnerContracts.kt 并入 RunnerEvent.toLogText），DI 改绑 **StubRunnerPort**；**RemoteServiceImpl 空实现**（setup 留 phantom killer 禁用，run/maaVersion 返 false/null，AIDL 四文件全保留）；RunForegroundService 重写为只观察 runnerPort.state，RunProgressSnapshot 迁 `service/` 包；PermissionManager 内化 Shizuku 探测（installShizuku 删，openShizuku 保留）。
- **刀④UI**：删 tasks/schedule/home/notification/options 五页 + 9 个业务组件；**AppRoot 重写为 2 tab（Alas+Settings）**；Routes 只剩 ALAS/SETTINGS/APP_LOG(_DETAIL)；SettingsScreen 重写为 Display/Log/Other/About 四卡（SettingsViewModel 扩三参 + themeMode/language/resolution 意图 + RestartApp 事件）。
- **刀⑤杂项**：Manifest 删 boot/alarm 两权限 + schedule 三组件 + Sentry meta-data；VirtualDisplayManager 删死常量 ROTATES_WITH_CONTENT；ShellDirs/AppPaths/AppFiles 删 AGENT_DIR/JNA_TMPDIR/FOCUS_DIR/PI_DIR。
- **遗留**：① readiness 弹窗 NotInstalled 档 onInstall 无真实安装能力（决策=不内置 APK），现接 openShizuku 语义降级，文案待用户决策；② AppSettings 里 wakeUnlock/telemetryEnabled 等成死 pref（未清 schema）；③ okhttp/tracing 已无引用但保留（M2-c 桥可能用上）；④ toml 未用条目未清；⑤ Koin 图仅编译期核对，真机运行验证留后续里程碑。

### 2026-09-16 · M2-a 基线构建绿 ✅（三跑迭代：Aliyun 镜像 + floatingx-compose 补齐）

- **基线 assembleDebug 第三跑 BUILD SUCCESSFUL**（1m48s，105 tasks；`app/app/build/outputs/apk/debug/app-debug.apk` 81MB）。本机可构建实证，M2-b 减法对照基准就位。APK 缺 MaaFramework jniLibs（拷贝时已排除）属预期，M2-b 连引用一起剔除。
- **跑①红**：`bundletool:1.18.3` 解析挂 TLS 握手中断（dl.google.com 被中间盒 RST；暖缓存只有 1.18.0）。curl 复测 dl.google.com 通=间歇性，仍决定根治：`app/settings.gradle.kts` 两个 repositories 块加 Aliyun google/central 镜像（官方源+jitpack 兜底）。已入 debug.md。
- **跑②红**：`OverlayController.kt:32` `Unresolved reference com.petterp.floatingx.compose.enableComposeSupport`。三方 hash 比对 + m0 用户 Gradle 缓存考古定位：`floatingx:2.3.7` 在中央仓是**无 compose 包的瘦 aar**；m0 当年靠仓库序 jitpack 优先拿到**聚合空 jar** → 传递依赖 `io.github.petterpx.floatingx:floatingx-compose`（jitpack 构建）才编过；加镜像时 jitpack 被挪到队尾 → 中央瘦 aar 截胡。修法：toml + `app/build.gradle.kts` **显式声明 `floatingx-compose:2.3.7`**（中央/aliyun 直达，CN 友好），不恢复 jitpack 优先序。已入 debug.md。
- **fork 源考古**：`git ls-files -v` 全 H 无 skip-worktree 隐藏改动；compose import 是 b2b0f54 提交自带（fork 作者本地靠 jitpack 序巧合可编，上游 CI 未覆盖该坐标陷阱）。
- **seed_config.py 键兼容 ✅**（未决项关闭）：ALAS master HEAD=`92c07aa28ba8515b7709542ae8c14f6a7f3a08bd` 的 `config/template.json` 五键（Serial/PackageName/ScreenshotMethod/ControlMethod/ScreenshotDedithering）全在。附带发现：rootfs 构建 `ALAS_REF` 默认 master **浮动不钉**（BUILD_MANIFEST 记录解析后 commit），可复现性改进留阶段三评估。
- **游戏仍在登录页**（只读 screencap `.tmp/game-now3.png`）——M1-d 油数 100 帧验收继续等用户把游戏点到出击菜单页。

### 2026-09-15 · M2-a 开工：fork 复活为 `app/`（25MB 干净副本）+ 基线构建在跑

- **v4 artifact 核验 ✅**：`.tmp/rootfs-dist-v4/rootfs.tar.xz` sha256 `b506a62e…745a` 与 CI 日志一致，cached-property 2.0.1 在列、ALL_IMPORTS_OK、OCR_GATE PASS——**交付基准定型**。
- **fork 复活**：`m0-archive/vendor/MaaFwApp`（只读）→ 仓内 `app/`（tar 管道拷贝，排除 `.git/app/build/.cxx/.gradle/.kotlin/.maafw/.maa-cache/build*/jniLibs`），25MB 源码级副本，**6 处 m0 WebView 未提交改动随之固化进仓**（AlasScreen/network_security_config/AppRoot/Routes/strings/manifest）。
- **修构建死路径**：`app/local.properties` 删 `pi.profile`（原指向已归档的 m0 yaml，`BuildProfile.kt:91-92` 硬失败）。
- **构建环境**：JDK17 @ `D:\VSCodeCache\shizku-m\build-env\jdk-17.0.2`；SDK 用 `C:\Users\da270\AppData\Local\Android\Sdk`（cmake 3.22.1 + ndk 28.2 齐）；`GRADLE_USER_HOME` = 本仓 `.tmp/gradle-home`（从 build-env 拷 1.1GB 暖缓存，不污染共享目录）。
- **基线 assembleDebug 在跑**（`.tmp/app-build-baseline.log`）——减法前先证本机可构建，之后减法每刀都有对照。

### 2026-09-15 · 阶段二备战：MaaFwApp fork 减法盘点落地（`docs/stage2-maafwapp-inventory.md`）

- explore 子代理对 fork @ b2b0f54 做全量只读摸底，盘点固化成工作底稿。**三条改变任务理解的发现**：
  1. **桥不在 fork 里**——m0 的 6 端点桥是 Python MaaFramework Agent（`m0-archive/spike/m0/agent/main.py`，TCP 22300 行分隔 JSON+裸帧，非 HTTP）；删 libMaaCore 会连桥一起删 → 阶段二的"保留 5 端点"= **在特权进程内用 Kotlin 重写**（去 ocr 端点）。
  2. **桥底层设施（libbridge.so + InputControlUtils + DriverClass）与业务解耦可原地留用**，唯一缺口是帧数据无 Java 裸字节出口（需加 JNI）。
  3. **fork 工作树带 6 处未提交改动 = m0 WebView 资产**（AlasScreen 等），复活前必须先固化。
- VD flag 现状核查**合规**（`SHOULD_SHOW_SYSTEM_DECORATIONS` 被 `VD_SYSTEM_DECORATIONS=false` 代码级挡住，`ROTATES_WITH_CONTENT` 是死常量）。
- 构建前提：`local.properties` 的 `pi.profile` 是死路径须先删；`libc++_shared.so` 不能删（断 libbridge）；13 个 MaaFramework/PP-OCR so 剔除后包体 200MB+ → <20MB。
- 游戏仍停在登录页（等用户点到出击菜单页）；v4 artifact 仍在下载。

### 2026-09-15 · M1-d（中）：油数探针链路全通，GHA 第四跑绿（cached-property 入正）✅

- **GHA run 34997038262（`e233630`）completed/success**——`cached-property` 正式进构建；artifact 后台下载中（`.tmp/rootfs-dist-v4`），作为交付基准。
- **油数探针机械链路真机验证通过**：宿主 `/system/bin/screencap` 抓帧（2800×1264）→ proot `-b frames:/frames` → `Digit.ocr` → in-proc PP-OCR 出文本。登录页错误区域读出 `'NA'` → `Digit.after_process` `int('NA')` ValueError——**正是"区域无数字"的标准失败形态**，证明 import 链/图像加载/CTC 解码/Digit 调用形状全对。
- 口径说明：m0 的 `OIL_AREA=(632,22,712,52)` 是 **1280×720 VD 原生帧**坐标；物理屏 2800×1264 宽屏 UI 锚定真实边缘，不能等比映射。M1-d 油数测试改用**实帧目测的原生分辨率油区**（游戏到出击页后定），m0 原生 720p 口径留阶段二 VD 上线后回归。
- 100 帧连拍与探针脚本（`.tmp/m1d-oil-probe.py`，已在 rootfs `/opt/alas/` 就位）备好，**只等用户把游戏点到出击菜单页**。
- WebUI 仍保活（bash-r6h84em7），PC 浏览器 127.0.0.1:22267 可看。

### 2026-09-15 · M1-d（上）：rootfs 真机拉起成功，WebUI 200 ✅，踩坑 4 连

- **验收 ③ BUILD_MANIFEST 可读 ✅**（设备上 cat 出完整 JSON：rootfs 0.1.0 / alas@92c07aa / py3.12.3 / ort 1.30.0 / cv2 5.0.0）。
- **验收 ① WebUI ✅**：shell 域 proot 单命令 `gui.py` → uvicorn `0.0.0.0:22267` startup complete，adb forward 后 PC `curl 127.0.0.1:22267` = **200**（PyWebIO Application，6055B）。
- **坑①**：解包目标非空场（Spike A 旧 rootfs）→ `./bin` 软链覆盖失败。修：解包脚本先 `rm -rf files/rootfs`。
- **坑②**：busybox tar 解 ubuntu-base 硬链接前向引用必炸（`uncompress→gunzip`）。修：PC 侧 `.tmp/repack-linkfree.py` 重打包去硬链接（reg 21359/hard 3 全物化/sym 740/dir 2380，977MB 未压缩 tar，WiFi push 43MB/s）。已入 debug.md。
- **坑③**：run-as（runas_app 域）**禁 socket**（`socket()` EPERM，虽有 inet gid）→ 改 shell 域跑 harness：shell 执行 /data/local/tmp 内 proot 可行；guest PATH 要显式 export（宿主 Android PATH 无 /usr/bin）；mksh heredoc 在 run-as 下建临时文件失败（禁用 heredoc）。
- **坑④**：shell 域 SELinux 禁**路径式 AF_UNIX**（shell_data_file 上建 socket 文件 EPERM），但 AF_INET/abstract AF_UNIX 通 → harness 用 sitecustomize 把 `BaseManager` 默认地址换 127.0.0.1:0（同 ALAS Windows 路径），**仅 harness 不进构建**（生产 untrusted_app 域 + app 私有 TMPDIR，m0 已实证无碍）。
- **依赖缺口实锤 1 个**：`cached-property`（`config_updater.py`/`alas.py` 顶层 import；老 uiautomator2 传递依赖，现代 3.x 不再传递；m0 清单同样缺但当时未踩到）。静态全扫其余 10 项均惰性/平台限定可忽略（cnocr/av/lz4/psutil 等）。**构建修复待做**：build-rootfs.sh pip 集 + cached-property 并重跑 GHA。
- 现状：WebUI 进程在后台任务保活（bash-r6h84em7）；shell 侧 rootfs @ `/data/local/tmp/rootfs`；**验收 ② 油数 100 次待跑——需用户把游戏点到出击菜单页**。

### 2026-09-15 · M1-c 收官：GHA 第三跑全绿 ✅

- **run 34989709297（commit `a1c9e96`）completed/success**，全程仅 ~4.5 分钟（ubuntu-24.04-arm 原生 + `XZ_OPT=-T0`）。七个 step 全绿，含 Spike F OCR gate。
- **pip 宽松集 aarch64 解析实录**（`.tmp/gh-run3-full.log`）：numpy 2.5.3 / scipy 1.18.1 / opencv-python-headless 5.0.0.93 / onnxruntime 1.30.0 / pydantic 1.10.26 / pillow 12.3.0 + ALAS 全套（adbutils 2.12.0、uiautomator2 3.7.0、pywebio 1.8.4、fastapi 0.125.0、uvicorn 0.53.0 裸版等 46 包）——**m0 实证集在 ubuntu-base 24.04 + py3.12.3 上一次装全，零失败**。
- **chroot import 硬门禁**：`ALL_IMPORTS_OK`；assets_fix 补丁生效（DAILY_SKIP @ module/daily/assets.py:19）。
- **CI Spike F 门禁**：model_load PASS / synthetic_digits 13/13 PASS / gray2d_stacking 2/2 PASS → **OCR_GATE PASS（3 PASS 0 FAIL 0 SKIP）**——合成数字用默认字体即可渲染，此前"无 CJK 字体会 SKIP"的预判未发生。
- **产物**：`rootfs.tar.xz` sha256 `b27148c6859ecbbaad0fb896876e2d13b36629cd987088a7b72c1c82550546d7` + BUILD_MANIFEST（artifact 14 天）。
- 结论：**M1-c 完成，rootfs 烘焙链定型**。进入 M1-d 真机复验（runbook 见 handoff）。

### 2026-09-15 · M1-c：GHA 首跑 404 秒修，第二跑在飞

- **（当日续②）用户新授权**：**本次长任务期间 git 操作全部预授权**（含 push；发版 release/tag 仍需逐次授权），已记 handoff。
- **（当日续③）M1-d 设备侧预踩点完成**：spikea 在机、nld 四件套齐（proot/loader/shmem/busybox）、/data 余量 91G；发现新坑——`libbusybox.so` 直接调报 `applet not found`（多合一认 basename(argv[0])，须软链成裸名 `busybox`），已记 debug.md；完整 M1-d runbook（推包→run-as 解包→proot 拉起→验收三件套）写进 handoff。
- **（当日续）第二跑 34989211076 又红**：ubuntu-base/apt/pip 基座全过（`libglib2.0-0t64` 改名修复生效、py3.12.3、git 2.43 装好），死在 **ALAS 克隆**：`fatal: could not read Username for 'https://gitee.com'`——gitee 同名镜像对匿名克隆返回 401 索取凭证（本机 `git ls-remote` 复现：挂凭证管理器提示）。修复：`ALAS_REPO` 默认改 **GitHub 原生上游**（`ls-remote` 实测 HEAD=92c07aa 可达；GHA runner 在海外本就应走 GitHub；runtime 的 fullcn 更新镜像由 deploy.yaml 管，与构建源无关），`chroot_run` env 白名单补 `GIT_TERMINAL_PROMPT=0` 让凭证提示 fail-fast。commit `a1c9e96` 已 push。**第三跑 34989709297 在飞**，改 2min 轮询盯梢（`.tmp/gh-run-watch3.log`，`gh run watch` 长连接两次被本机网络 EOF 打断，不可用于盯梢）。
- **push 授权到位**：用户"可以push，手机可用于调试"→ commit `b263dfb`（59 文件 +37100 行，M1 全量 + Spike E 报告 + 手势劫持硬约束）推 `Shinarin/MaaAL` main，触发 rootfs.yml 首跑（run 34988699866）。
- **首跑 12s 失败**：`Build rootfs` step 下载 ubuntu-base 404——脚本写的是 `ubuntu-base-24.04-arm64.tar.gz`，cdimage 实际命名为 `ubuntu-base-<点版本>-base-arm64.tar.gz`（当前 24.04.3/4/5 并存）。
- **修复**：`build-rootfs.sh` 两处 URL 钉 `ubuntu-base-24.04.5-base-arm64.tar.gz`（旧点版本 cdimage 保留，可复现；无 sha256 钉版故无连带改动）；`curl -sI` 200 ✓、`bash -n` ✓、全仓 URL 重扫无其他 404 风险。commit `e85255d` 已 push（构建迭代属本次授权范围，已报备）。
- **第二跑**：run 34989211076（`e85255d`）in_progress，后台任务盯梢（`.tmp/gh-run-watch2.log`）。重点盯：pip 宽松集 aarch64 实际解析、import 硬门禁输出、Spike F 门禁 chroot（中文字体缺省 → 合成图 SKIP 属预期）。
- **游戏侧**：`am start` 拉起成功，截屏确认停在**登录页**（服务器：奥林匹克行动）——M1-d 油数复验需要游戏停在**出击菜单页**，届时请用户手动点过去（我不代点游戏界面）。
- 注：盯梢任务 bash-ash579qm 因 GitHub API 瞬时 EOF 提前退出（`failed to get run: EOF`），与构建本身无关；已改直接 `gh run view` 查状态。

### 2026-09-15 · 阶段一 M1-c 前置：push 前主代理终审（4 文件 7 处修）

- 终审动机：push 触发 GHA 首跑前，主代理对子代理交付物逐行把关（不依赖子代理自查）。
- **rpc.py**（360 行全文审）：**通过零修改**——rec 主路径（3ch 堆叠/动态宽/CTC+tail 自适应）、锁、负路径、接口形状全部正确；整屏 3ch 彩图的通道序约定（BGR/RGB 未显式定义）留 M1-d 真机定案。
- **wrapper.py 修 1 个真 bug**：`_arm_stdin_watchdog` 原逻辑对一切非 tty stdin 挂监控，**stdin=/dev/null（如 Java Redirect.DISCARD）时 read 立即 EOF → wrapper 启动即自尽**；改为仅 `stat.S_ISFIFO`（管道）才挂。其余（killpg 3s 优雅窗、flock 单实例、atexit/signal 幂等）通过。
- **build-rootfs.sh 修 4 处**：① mount 前 `mkdir -p dev/pts proc sys`（ubuntu-base 的 /dev 可能无 pts 子目录，mount --bind 要求挂载点已存在——首跑必炸点）；② `libglib2.0-0` → `libglib2.0-0t64`（Ubuntu 24.04 t64 过渡改名，旧名无安装候选）；③ PYPI_MIRROR 默认 aliyun → **PyPI 官方**（GHA 海外直连最快最稳，与运行时无关——InstallDependencies:false 已锁），env 可覆盖回 aliyun；④ `XZ_OPT=-T0` 多线程压缩（单线程 xz 压 ~600MB 要几分钟）。
- **rootfs.yml 修 1 处**：Spike F 门禁 step 前补 `mount --bind /dev /proc /sys` + EXIT trap 卸载（构建脚本打包前已全卸载；onnxruntime CPU 拓扑探测读 /sys，chroot 裸跑行为不确定）。
- 验证：`bash -n` ✓、`py_compile` ✓、YAML safe_load ✓（`on` 键被 PyYAML 1.1 解析为 True 属预期，GHA 用 YAML 1.2 无此问题）。
- 状态：**仍等用户授权 commit + push**（M1 产物含本终审修改已全部就绪）。

### 2026-09-15 · 阶段一 M1-a：rootfs 资产 curated 与构建链骨架

- **pip 层修正（同日补充指令，覆盖下方"关键决策①"旧方案与"未决项①③"）**：原方案"以 ALAS `deploy/headless/requirements.txt` 钉版清单为底 + 黑名单过滤 + 逐包 best-effort"**作废**——核实该清单钉版在 aarch64 + Python 3.12 下大面积死链（`numpy==1.17.4`/`scipy==1.4.1`/`pillow==9.5.0`/`opencv-python-headless==4.7.0.72`/`lz4==4.3.2`/`av==10.0.0`/`psutil==5.9.3`/`pycryptodome==3.9.9`/`pydantic==1.10.9`/`uvicorn[standard]==0.17.6` 等全无 py3.12 wheel），逐包按钉版装照样失败。新策略 = **m0 `termux/setup_env.sh` 真机实证现代化宽松集**（单条 install：`numpy>=2` scipy pillow lxml opencv-python-headless onnxruntime + 纯 Python 16 包；uvicorn 裸版不带 `[standard]`——standard extra 拉 uvloop/httptools 死链，m0 同款；不装 jellyfish/cnocr/mxnet/zerorpc/pyzmq/av，原因留在脚本注释）；装后 **import 硬门禁**（fail-fast）：m0 第 4 节同款校验 + onnxruntime，chroot 内打印各版本号 + `ALL_IMPORTS_OK`，任一 ImportError → `::error::` 退出码 1 中止构建（校验顺序在 jellyfish shim 安装之后）。`dist/pip-failures.txt` 逻辑随之全删（产物注释、dist 拷贝、瘦身清单三处）；`seed_config.py` 一并装入 `/opt/alas/seeds/seed_config.py`（运行时实例播种由阶段三调用，`MAAAL_ALAS_ROOT=/opt/alas`）。

- **产物（全部新建进仓）**：`rootfs/patches/`（m0 补丁集 module/+assets/ 子树 + assets_fix.py，剔除全部 __pycache__ 与 `module/ocr/rpc.py`——后者被 M1-b 的 in-proc 版取代）、`rootfs/seeds/{deploy.yaml,seed_config.py}`、`rootfs/shims/jellyfish.py`、`rootfs/models/ocr/`（PP-OCR 三件套，字节数与源逐一核对一致：9893172/21146753/74947）、`rootfs/build/build-rootfs.sh`、`.github/workflows/rootfs.yml`。
- **deploy.yaml（新写，非照抄 m0）**：行结构与 ALAS `config/deploy.template-linux-cn.yaml` 完全一致（已 diff 校验键序）；fullcn 同款镜像（`git.lyoko.io` + aliyun pypi——不能写 gitee/tuna，会被 `config_redirect()` 静默改写）；**更新器七键全锁**（AutoUpdate/InstallDependencies/EnableReload/CheckUpdateInterval/AutoRestartTime/ReplaceAdb/AutoConnect），`AutoUpdate:false` 是保住钉版 commit 的唯一闸门；OCR 键保留（`OcrClientAddress: 127.0.0.1:22300`，in-proc rpc.py 读而不连）；`WebuiPort: 22267`（非 AlasApp 的 22367）。
- **build-rootfs.sh（GHA `ubuntu-24.04-arm` 上执行，本机只 `bash -n` 通过）**：ubuntu-base 24.04 arm64 + chroot 内 apt/pip/git 钉版克隆；挂载用 MOUNTED 数组 + EXIT trap 兜底 + 打包前显式卸载并 `mountpoint` 校验 + tar `--one-file-system` 三重防线（防把宿主 /dev /proc /sys 打进包）；DNS 用静态 resolv.conf（223.5.5.5+1.1.1.1）bind 进去——宿主 stub 127.0.0.53 在 chroot 内必挂。
- **关键决策**：① pip 依赖层最终 = m0 实证现代化宽松集 + import 硬门禁（原"黑名单过滤 requirements 钉版清单"方案已作废，详见上方"pip 层修正"）；② jellyfish 用纯 Python shim 顶替模块名，site-packages 路径在 chroot 内 `sysconfig` 实查不猜前缀；③ 模型装 `/opt/alas/models/ocr/`（v3 自定义路径，与 M1-b rpc.py 的默认 `./models/ocr/` 约定对齐，已核实）；④ `assets_fix.py` 确认是改 **ALAS 树内**文件（argv[1]=ALAS 根），宿主侧直跑；⑤ BUILD_MANIFEST（JSON）字段：rootfs_version/build_time_utc/alas_repo/alas_commit/patches_source(m0-archive 路径@构建时仓 commit)/ocr_models 三件套 sha256/python/onnxruntime/opencv 版本，镜像内 `/opt/alas/BUILD_MANIFEST` + `dist/` 双份（决策 #10，App 可读）。
- **workflow `rootfs.yml`**：workflow_dispatch + push(paths: rootfs/** 或自身）触发；concurrency 按 ref 取消在途；checkout→runner 信息→构建→Spike F 门禁→upload-artifact（rootfs.tar.xz+BUILD_MANIFEST，14 天）。门禁脚本实际 CLI 无 `--chroot`（已核实 argparse：--model-dir/--rpc-path/...），故采用任务许可的 chroot 等价写法：门禁随构建装入 `/opt/alas/`，workflow 里 `sudo chroot work/rootfs /usr/bin/python3 /opt/alas/spike-f-ocr-gate.py --model-dir ... --rpc-path ...`。
- **未决项**：① 构建未在本机执行（Windows 无 chroot），也未在 GHA 实际跑过——首次 workflow 运行才是真正的验证，重点盯 pip 宽松集在 aarch64 的实际解析结果与 import 硬门禁输出；② rootfs 内无中文字体，门禁合成图用例将记 SKIP（不影响 PASS 判定），如需 CI 全量断言要另议字体方案；③ ~~`seeds/seed_config.py` 未装入镜像~~ **已关闭**：随 pip 层修正装入 `/opt/alas/seeds/seed_config.py`；④ `.gitignore` 通用规则 `build/`、`config/` 会误伤 `rootfs/build/` 与 `rootfs/patches/module/config/`，已加否定规则解除（check-ignore 验证通过）。

### 2026-09-15 · 阶段一 M1-b：rpc.py in-proc OCR + wrapper/runner + Spike F 门禁

- **产物（全部新建进仓）**：`rootfs/overlays/module/ocr/rpc.py`（in-proc onnxruntime PP-OCR，替换 m0 TCP 桥版，对外接口逐字保留）、`rootfs/overlays/wrapper.py`（薄 HTTP 127.0.0.1:22400 + 进程组管理）、`rootfs/overlays/runner.py`（薄 runner：`from alas import AzurLaneAutoScript` → `loop()`；注意官方类在 `alas.py`，仓内**没有** `AzurLaneAutoScript.py`）、`rootfs/build/spike-f-ocr-gate.py`（Spike F 精度门禁，CI/真机两用）。
- **rpc.py 要点**：模型惰性加载（`MAAAL_OCR_MODEL_DIR` 可覆盖，默认 `./models/ocr/`）；一把 RLock 串行加载与 session.run（m0 并发教训）；2D 灰度堆叠 3ch（m0 硬坑）；CTC blank 映射按输出维数反推（实测 rec 输出 18710 = keys 18708 + blank + 尾部 ' '）；cand_alphabet 不接（Digit 系 after_process 自清洗，同 m0）；import 失败 → alive() False、OCR raise RequestHumanTakeover；det 后处理对应 PaddleOCR DBPostProcess（pyclipper unclip 用 minAreaRect 等比外扩近似，注释标明）。
- **本机真测**（`.tmp/venv-ocr/`，onnxruntime 1.30.0 + numpy 2.5.3 + cv2 5.0.0 + pillow 12.3.0，输出存 `.tmp/venv-ocr/test-output.txt`）：
  - 模型加载 PASS（det 动态 H/W、rec [B,3,48,动态W]，均 CPUExecutionProvider）。
  - **合成数字行图 rec：13/13 完全正确**（10 组白底黑字含 `/`、`:`，另 3 组反相浅字深底全对）；2D 灰度单通道 2/2（堆叠分支工作）。
  - 真实截图 `m0_game_login.png`（1280×720）det+rec：23 框，'屏幕执行权限认证'、'CADPA'、审批号行等真实 UI 文本命中；游戏美术字/logo 部分空或误读（'auy Jozy' 等），符合该模型一贯表现——**生产主路径是 rec-only**（ALAS extract_letters 行图），整屏 det+rec 非生产路径。
  - 生产调用形状直测：`atomic_ocr_for_single_lines(img_list, alphabet)` → `list[list[str]]`，`''.join` 消费精确匹配；`close()` 可重入且关后能惰性重载；8 线程 × 20 次并发 rec 零错误；模型目录缺失 → alive() False + RequestHumanTakeover，`close()` 后恢复。
  - 门禁阈值逻辑自验：4/4=100% → exit 0 PASS；3/4=75% <98% → exit 1 FAIL。
- **未覆盖**：wrapper/runner 无法本机真测（需 ALAS + rootfs 环境），仅 `py_compile` 通过（四文件全过）；油数真机图集（m0 DoD ≥98% 口径）待补进 `rootfs/tests/ocr/` 后在 rootfs 内跑 `--real-dir`。
- **留阶段三决策**：WebUI 启停按钮与悬浮窗并存（wrapper 不碰 ProcessManager，双头管理风险；候选：wrapper 同进程 uvicorn 直调 `ProcessManager.get_manager()`）。

### 2026-09-15 · Spike E 收口 + 主屏手势劫持事件彻查（硬约束落地，不能再有第二次）

- **事件**：Spike E 实验窗口（22:15–22:33）内，scrcpy-server `--new-display` 建的虚拟屏带 `FLAG_SHOULD_SHOW_SYSTEM_DECORATIONS` → SystemUI 把 `GestureNavAnim`/`GestureSildeOut`/`NavigationBar0` 建到 VD 上（物证 `spike/e-adb-virtual-display/logs/e3c-power-reset.txt:19-32`）→ **用户主屏手势导航失效**。22:41 停掉实验子代理并杀掉 scrcpy-server（PID 32244/32246），VD 销毁、手势窗口回主屏恢复；22:44 设备侧临时物全清场（`get-displays` 只剩 0、无 app_process 残留），证据图 6 张已留本地 `spike/e-adb-virtual-display/logs/`。
- **根因**：AOSP 原文"virtual displays without this flag shouldn't show home, navigation bar or wallpaper"——scrcpy 默认设该 flag；m0 代码显式不设（`VirtualDisplayManager.kt:39,187-189`），这是 m0 不踩坑的代码级原因。**如实修正**：m0 项目此后长期暂停未用，"数月无事故"不成立，以代码证据为准。
- **硬约束落地（不能再有第二次）**：① REPORT 修正两处"flag 集等价"错误表述并补记事件节（§12）；② `debug.md` 新增 4 条坑（手势劫持生死线、screencap/input 双命名空间、VD 熄灭 shell 点不亮、scrcpy 生命周期两陷阱）；③ `AGENTS.md` 新增「虚拟屏实验纪律」（禁 SYSTEM_DECORATIONS / 实验前后查手势窗口归属 / 清场到 get-displays 只剩 0）；④ `docs/roadmap-v3.md` 阶段二新增「VD flag 硬约束」护栏、Spike E 行补结果。
- **通道状态**：USB 传输在事件中消失（用户拔线），WiFi `192.168.50.190:5555` 已重连恢复调试闭环。
- Spike E 实验本身的结论见下一条（子代理入账）。

### 2026-09-15 · 阶段〇 Spike E：adb 直控虚拟显示屏（B′ + E，PASS 但推翻"甩掉 m0 桥"的预期）

- 结论：**shell 域（uid 2000，无 root）能建虚拟屏、能截屏、能注入输入、能取视频流——能力全通**；但 **不能替代 m0 桥**。
  - 建屏：scrcpy-server **v4.1**（sha256 `deacb991…0cae`）+ `new_display=1280x720/160`，owner=`com.android.shell (uid 2000)`，逐字配方见 `spike/e-adb-virtual-display/REPORT.md` §3.2。
  - 截屏：**`screencap -d` 必须用 `dumpsys SurfaceFlinger --display-id` 的 SF physical id**；用 logical id 就是 m0 §41 那句 `Display Id 'N' is not valid`。用对 id 后拿到真实 1280×720 画面（Settings UI / 壁纸 / 自研 App UI 三张证据图）。
  - 注入：**`input -d` 吃 logical id**（给 physical id 直接 `IllegalArgumentException`），实测 BACK 令 App 从 VD 任务栈消失、滑动令设置列表滚动（前后截图 + 任务栈为证）。
  - 视频：scrcpy h264 1280×720 流实测（IDR + ~116B P 帧），保活客户端落盘取证。
- **推翻 m0 §41 两条负面记录**：`screencap -d` 失败是 ID 命名空间错用；`input -d` 在"VD 可见且窗口 resumed"时确实生效（当年更像"VD 处于熄灭/无焦点窗口"态）。
- **真正的硬约束（新发现）**：VD 因 `FLAG_OWN_DISPLAY_GROUP` 自成 display group，其电源请求由 **WindowManager** 提供；被置 OFF 时 **ColorFade 层**盖住整屏 → 截屏纯黑、任务 STOPPED、窗口无 surface。**shell 域无解**（`cmd display power-reset` 无效；`requestDisplayPower(id, ON)` 只恢复窗口 surface，ColorFade 仍在；`am start` 也不点亮）。实测：设备 `mWakefulness=Awake` 时建屏即 ON（正常渲染），Dozing 时建屏即 OFF；且 VD 创建后 1~2 分钟内会被 framework 自己翻成 OFF（设备仍 Awake）。
- 第二个硬约束：**VD 从不独立存活**——`app_process` 由 `adb shell` 启动，三块 VD 的收场分别是 PC 后台任务超时杀 shell / server 运行 138s 后自灭（死因未取证）/ adb 传输掉线；且实验末段设备 adb 掉线（TCP offline / USB 消失 / `connect` 被拒 10061，ping 正常），需用户在 shizuku-m 点"离线自连" → **设备侧清场 BLOCKED**（待删清单见 REPORT §8）。
- 交付：`spike/e-adb-virtual-display/`（REPORT.md + `logs/` 全量证据含 5 张截图 + `tools/` 保活客户端与 VDLab 反射探针源码/jar）；`handoff/2026-09-15-spike-e.md`。
- 新坑入 `debug.md` 5 条：scrcpy `cleanup` 自删 jar、server 必须有人连、`screencap`/`input` 的 `-d` 命名空间分裂、VD 变黑=display-group 电源请求 OFF（ColorFade）、HONOR 显示栈缺 `requestDisplayPower(int,boolean)`/`getPhysicalDisplayIds`。
- 立场：控制面维持"**桥为主**"，本通路登记为**诊断/备用**；若要生产化需另设计"常驻宿主 + 断线自愈 + VD 重建保活"。

### 2026-09-15 · 建仓：公开仓 MaaAL 首次 push（用户指令授权）

- 仓库：**https://github.com/Shinarin/MaaAL**（PUBLIC，默认分支 `main`，首提交 `f89a43f`，194 文件）。描述：ALAS 一体化 Android APK：proot rootfs 运行时 + Shizuku 虚拟屏后台挂机。
- 用户拍板：阶段一构建走**路径 1（GHA ARM64 runner 构建 rootfs）**（零本地负担；WSL 方案作废）；仓名定 **MaaAL**。本次 push 为用户明确指令，属红线六授权范围；后续 push/发版仍需单独授权。
- 入库口径：
  - `m0-archive/`（1.3G，MaaFwApp fork + ALAS 副本）**留本地不入仓**，已加 `.gitignore`。
  - spike 的 APK 二进制（`spike/**/dist/*.apk`，可重建）不入库；`dist/logs/` 全量文本证据**保留入库**（`.gitignore` 否定规则实现）。
  - Gradle 构建产物（`.gradle/`、`build/`、`.kotlin/`、`local.properties`、`*.iml`、`.idea/`）忽略。
  - `.kimi-code/`（项目技能 + mcp.json，无密钥）与 `.vscode/` 入库。
- License：主仓 **AGPL-3.0**（新建根 `LICENSE`，全文取自 m0-archive 同款；v3 合规线决策）。
- 环境事实：gh CLI 已登录 `Shinarin`（repo scope）；git 身份 Elysia \<da2701076760@gmail.com\>；仓库从无提交，分支 `master`→`main`。
- 注意：GitHub 侧 license 识别有索引延迟（push 后 `licenseInfo` 暂为 null，非缺失）；README 按约定发版前再整理。
- 交接：`handoff/2026-09-15-repo.md`。

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
