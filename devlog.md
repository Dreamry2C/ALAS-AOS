# Devlog

> 倒序排列，最新在上；按发版版本号分段。

## 未发版

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
