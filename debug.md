# Debug · 坑点记录

> 本文件记录新阶段踩过的坑（现象 / 根本原因 / 解决方案）。
> **历史坑点（m0 阶段，全真机实证）见 `m0-archive/docs/debug.md` 与 `m0-archive/docs/devlog/`。** 高频索引：
> WebView `vh` 塌缩（注入 innerHeight 修复）｜幻影进程查杀（`max_phantom_processes` / `settings_enable_monitor_phantom_procs`）｜mDNS `_adb-tls-connect` 端口过期但广播残留｜MaaFW PP-OCR 对 2D 单通道静默返空（堆叠 3ch）｜MaaFW 截图 BGR↔ALAS RGB 翻转｜RUN_COMMAND 权限只授清单声明方｜`am force-stop` 杀不掉 shell uid 残留（须显式 kill）｜桥 30s 无流量判死（10s 心跳）。

## [2026-09-15] jniLibs 里非 `lib*.so` 命名的文件被双重丢弃

- **现象**：`jniLibs/arm64-v8a/libtalloc.so.2`、`libbusybox.so.1.38.0` 放进工程后，构建成功，但 APK 的 `lib/` 里查无此文件；`nativeLibraryDir` 自然也没有。
- **根本原因**：两层过滤。① AGP 打包阶段丢弃不匹配 `lib*.so` 的名字（静默）；② 即使进了 APK，AOSP 安装器（`ApkParsing.cpp::ValidLibraryPathLastSlash`）对 **非 debuggable** 应用也只解包 `lib` 前缀 + `.so` 后缀的文件（debuggable 应用是例外，所以 debug 构建容易"看起来正常"）。
- **解决方案**：把 DT_NEEDED 字符串原地改写成短名并同步改文件名，例：
  - `libproot.so`：`libtalloc.so.2` → `libtalloc.so`
  - `libbusybox.so`（stub）：`libbusybox.so.1.38.0` → `libbusybox_app.so`
  工具：`spike/a-proot-exec/tools/patch-dynstr.py <elf> <old> <new>`（dynstr 原地缩短 + NUL 填充，其他偏移不受影响），改完 `llvm-readelf -d` 复核。新命名不得长于原名。
  另注意：AGP 新默认 `extractNativeLibs=false`，必须显式 `packaging { jniLibs { useLegacyPackaging = true } }` 才会解包到 nativeLibraryDir。

## [2026-09-15] Termux busybox 是 stub + 载荷，applet 由 argv[0] 决定

- **现象**：exec 改名后的 `libbusybox.so uname -m` → `libbusybox.so: applet not found`，退出码 127（看起来像 exec/动态库失败）。
- **根本原因**：Termux 1.38 的 `bin/busybox` 只有 4320 字节，是启动器 stub；applet 代码在 `lib/libbusybox.so.1.38.0`（876KB 共享对象）。stub 用 `argv[0]` 基名选 applet：名为 `libbusybox.so` 时它把整个名字当 applet 名 → not found。
- **解决方案**：从 nativeLibraryDir 执行时用 argv0 覆写 shim：`libspike_shim.so <argv0> <path> [args...]`（源码：静态 C 版 execve 包装，见 `spike/a-proot-exec/REPORT.md` §4.2）；或 symlink 命名（但 symlink 需落在可 exec 的目录，35 上私有目录不可行，nld 只读）。

## [2026-09-15] `proot -r` 报 `execve(...): Permission denied` 的真凶是 rootfs 内解释器缺 +x

- **现象**：`proot -r <filesDir>/rootfs /bin/busybox ...` → `proot error: execve("/bin/busybox"): Permission denied`，与 targetSdk/SELinux 拦截症状一模一样。
- **根本原因**：guest ELF 的 `PT_INTERP=/system/bin/linker64` 在 rootfs 中被解析为我们的副本 `rootfs/system/bin/linker64`；该副本是用"复制文件"方式从 assets/宿主拷来的，未 `chmod +x`（Kotlin `File.copyTo` 不保留权限）→ 内核/loader 对解释器报 EACCES。
- **解决方案**：rootfs 内**所有**需执行文件（解释器、可执行、脚本）显式 `setExecutable(true)`；探测时先 `ls -l` 打印模式（本 spike 的 `P0-rootfs-modes` 探针）。

## [2026-09-15] proot rootfs 客户机动态库闭包不全 → `CANNOT LINK EXECUTABLE ... libc++.so not found`

- **现象**：修好解释器权限后，busybox 在 rootfs 里继续报 `library "libc++.so" not found: needed by /system/lib64/liblog.so in namespace (default)`。
- **根本原因**：合成迷你 rootfs 只借放了 `liblog.so`，漏了它的依赖 `libc++.so`（逐个症状式补库会反复踩）。
- **解决方案**：用 `llvm-readelf -d` 递归求 `DT_NEEDED` 传递闭包再整体拷贝（本 spike 闭包：`libc/libm/libdl/liblog/libc++ + ld-android.so + linker64`）。真实 Ubuntu rootfs 自带 glibc 不需要这套借用，但同样要保证完整性。

## [2026-09-15] targetSdk 35 下 app 不能直接 exec 私有目录文件（error=13）——预期行为

- **现象**：`ProcessBuilder` 执行 `<filesDir>/rootfs/usr/bin/xxx` → `IOException: ... error=13, Permission denied`；同一用户/同一文件在 targetSdk 28 构建下可执行；文件 `canExecute=true`、模式 `-rwx--x--x` 也救不了。
- **根本原因**：Android 10+ 对 targetSdk ≥ 29 的应用禁止执行 app data 目录中的文件（SELinux 域差异：28 → `untrusted_app_27` 有 execute 权限，35 → `untrusted_app` 无）。
- **解决方案**：不要直接 exec 私有目录文件。可执行体放 jniLibs（nativeLibraryDir，命名 `lib*.so`）执行；rootfs 客户机由 proot 走 loader/解释器映射路径运行（本 spike 实测 proot 在 35 上完整可用，含客户机内嵌套 execve）。私有目录仅放数据。28 兜底仅用于无法改造的老场景。

## [2026-09-15] `MSYS_NO_PATHCONV=1` 下 `adb install` 的主机路径必须转 Windows 形式

- **现象**：`MSYS_NO_PATHCONV=1` 后 `adb install -r /d/VSCodeCache/.../x.apk` → `adb.exe: failed to stat ...: No such file or directory`。
- **根本原因**：该环境变量（为 `adb shell` 里 `/data/...` 等设备路径不被 MSYS 改写而必需）同时关掉了 adb.exe 参数路径自动转换；Windows 侧 adb 只认 `D:/...`。
- **解决方案**：脚本里对主机侧路径显式 `cygpath -m "$apk"` 后再传给 adb（`run-device-ladder.sh` 已内置）。

## [2026-09-15] local.properties 指向不存在的 SDK：AGP 仅告警并静默回退 ANDROID_HOME

- **现象**：`local.properties` 里 `sdk.dir` 写错（不存在的目录）时，构建仍成功，只在输出里带一行 `WARNING: ... Directory does not exist`。
- **根本原因**：AGP 找不到 `sdk.dir` 时会回退环境变量 `ANDROID_HOME`（本机指向系统 SDK），于是实际用的是另一套 SDK，排查构建差异时极易误判。
- **解决方案**：构建日志里出现该 WARNING 必须当错误处理；`local.properties` 用 `sdk.dir=D:/VSCodeCache/shizku-m/build-env/android-sdk`（便携工具链，已由 shizuku-m 验证 AGP 8.10 + compileSdk 36 可用）。


## [2026-09-15] 迷你 rootfs 缺 /dev/null：busybox 后台作业全部 `can't open /dev/null` 静默死光

- **现象**：`proot -r rootfs /bin/busybox sh -c '<脚本>'`，脚本里用 `cmd &` 派生后台进程时子进程立刻全死，guest stderr 每行一条 `sh: line 0: can't open /dev/null: no such file`；同一脚本里的前台命令、`$(...)` 替换全部正常——极易误判成"`$!` 拿到的 pid 不对"或"proot 不支多进程"。
- **根本原因**：POSIX 语义：作业控制关闭时异步列表（`&`）的标准输入被指派为 `/dev/null`；busybox ash 在 fork 后以 `O_RDONLY` 打开 `/dev/null`（**不带 `O_CREAT`**），而我们的合成 rootfs 的 `dev/` 是空目录 → ENOENT → 子进程带着这个 errno 退出。
- **二次陷阱**：脚本里任何一次 `2>/dev/null`（ash 的 `file` 重定向是 `O_WRONLY|O_CREAT`）都会在 rootfs 里**创建一个普通文件 `dev/null`**，于是"第二次跑就正常了"。表现为偶发玄学，实际是上一轮把自己的坑填了。
- **解决方案**：proot 启动参数加 `-b /dev:/dev`（最小可用为 `-b /dev/null`），把宿主 /dev 绑进 guest；实测 `-b /dev:/dev` 后同一脚本 8/8、48/48 全存活。生产 rootfs 同理：不能拿普通文件冒充 `/dev/null`（写入不会丢弃，见 Spike C 里那个 3KB 的"null"）。

## [2026-09-15] 设备侧 toybox grep 不认 `\|`（BRE 交替），静默零命中

- **现象**：`run-as <pkg> sh -c 'grep "A\|B" file'` 在真机上没有任何输出也不报错；同一条命令在 PC 的 GNU grep 下正常。
- **根本原因**：`\|` 是 GNU 的 BRE 扩展，Android toybox grep 不支持，模式被当字面量 `A|B` 匹配。
- **解决方案**：设备侧 grep 一律写 `grep -E 'A|B'`（或 `grep -e A -e B`）。

## [2026-09-15] 数「幻影进程」的正确姿势：直读 app cgroup 的 cgroup.procs

- **现象/需求**：需要精确知道 PhantomProcessKiller 眼里的"app 子进程数"：`dumpsys activity processes | grep PhantomProcessRecord` 要等 AMS 周期刷新（CPU tracker 节拍）才准；`ps -A -o USER | grep -c <user>` 会把 adb `run-as` 自己拉起的同 uid 进程算进去，偏高。
- **机制**：`PhantomProcessList.lookForPhantomProcessesLocked()` 读的就是 AOSP `nativeGetCgroupProcsPath(uid, pid)` 指的文件；本机（cgroup v2）布局为 `/sys/fs/cgroup/apps/uid_<uid>/pid_<appPid>/cgroup.procs`，shell 可读，内容 = app 主进程 + cgroup 内全部后代。
- **解决方案**：采样用 `wc -l < /sys/fs/cgroup/apps/uid_<uid>/pid_<appPid>/cgroup.procs` 再减 1（app 自身），与 `ps` 计数互相校验；两者一致即说明读数可靠。

## [2026-09-15] 被 SIGKILL 掉 tracer 的 proot 留下 PPID=1 孤儿，`am force-stop` 收不掉

- **现象**：proot 被幻影杀手 kill 后，guest 的 `sleep`/`sh` 变孤儿（PPID=1），再执行 `am force-stop <pkg>` 也不消失，污染后续实验的进程计数。
- **根本原因**：tracer 死后子进程被 reparent 到 init；实测这些孤儿与 app 主进程不在同一 memory cgroup（`memory:/` vs `memory:/apps/<pkg>`），而 `am force-stop` 的 cgroup 清理只覆盖 app 自己的组，AMS 也没把它们记在 app 名下。
- **解决方案**：同 uid 才能动它们——`adb shell run-as <pkg> sh -c 'M=$$; for p in $(ps -A -o PID,USER | awk "\$2==\"u0_a301\"{print \$1}"); do [ "$p" != "$M" ] && kill -9 $p; done'`。跑任何以"进程计数"为判据的实验前，先跑一遍清理并确认计数归零。

## [2026-09-15] 真机上"app 自己 fork 的进程"才算幻影：Shizuku/shell 域拉起的树不在 app cgroup

- **现象**：用 `run-as`（uid 变成 app 但 SELinux 域仍为 shell）拉起的 proot 树，`am force-stop <pkg>` 杀不掉，`ps` 里也归属 app uid。
- **机制**：AMS 的幻影进程判定 = 读 **app 主进程的 cgroup**（`/sys/fs/cgroup/apps/uid_<uid>/pid_<appPid>/cgroup.procs`）；进程进了哪个 cgroup 取决于 fork 者，而不是 uid。
- **含义**：v3 架构里由 App（untrusted_app）自己 fork 的 proot 整树**必然**计入幻影配额（这正是 Spike C 要缓解的场景）；若将来改由 Shizuku/shell uid 侧拉起，则压根不进 app cgroup，配额问题消失——但 adb 侧无法触达虚拟屏（见 roadmap-v3 决策），该路线不在主线上。

## [2026-09-15] 幻影收割挂在 AMS 的 5 分钟节拍上——存活实验窗口小于一个节拍就会误判

- **现象**：同一份默认配置的对照实验，三轮的"被杀时刻"分别是 spawn 后 **+29s / +43s / +267s**（第三轮一度被当成"没被收割"，因为前 4 分钟一直全存活）。
- **根本原因**：裁触发点不是"超编即杀"，而是 `ActivityManagerService` 的 `CHECK_EXCESSIVE_POWER_USE_MSG`（`POWER_CHECK_INTERVAL` 默认 **5 分钟**）→ `checkExcessivePowerUsage()` → `AppProfiler.updateCpuStatsNow()` → `PhantomProcessList.updateProcessCpuStatesLocked()`（只有此时才扫 app cgroup、建幻影记录并 `scheduleTrimPhantomProcessesLocked()`）。另外 `AppProfiler.updateCpuStatsNow()` 里 phantom 监控 flag 为假时**整个扫描都不做**（不只是跳过 kill）——所以关掉 flag 后 `dumpsys activity processes | grep PhantomProcessRecord` 会恒为 0。
- **解决方案**：任何"子进程是否被收割"的 A/B 观察窗 **≥1 个节拍（≥420s）**；判定"没被杀"必须覆盖至少一次节拍。计数用 `dumpsys activity settings | grep max_phantom_processes` 读生效阈值，用 cgroup.procs 读当前幻影集合。

## [2026-09-15] 别把 `ps -A | grep <user> | wc -l` 当成"幻影进程数"的权威口径

- **现象**：采样里 `ps` 计数偶尔比 cgroup 计数少几十（如 `ps=17` 而 cgroup=50），或把 adb `run-as` 自己拉起的同 uid 进程算进来。
- **根本原因**：`ps` 是快照式遍历 + 文本过滤，进程频繁生死时会漏/多；`run-as` 的 shell 自身也在 app uid 下。
- **解决方案**：以 `/sys/fs/cgroup/apps/uid_<uid>/pid_<appPid>/cgroup.procs` 行数 −1（App 自身）为权威值（与 AMS 同源）；`ps` 仅作交叉校验；App 侧另用 `kill(pid,0)` 做独立心跳复核。
