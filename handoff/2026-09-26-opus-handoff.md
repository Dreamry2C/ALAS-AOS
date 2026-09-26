# Handoff 2026-09-26 · opus 接手 mimov 后的改动与后续（交接下一 AI）

> 写给：接手 ALAS-AOS「原版 OCR 可复现构建 + 上机验证」的下一个 AI。
> 前序：mimov2.6pro 阶段见 `handoff/2026-09-25-fullscreen-and-findings.md`（+ 其审核索引）。
> 我（opus，commit 署名 `opus-4.8`）从 mimov 的 `d8bcb37` 之后接手，`git log --grep 'opus-4.8'` 可全列。

## 一、大方向（用户拍板，与 mimov 阶段的差异）
1. **OCR**：移除 AOS 加的**通用 PP-OCR**（PaddleOCR 预训练通用模型，未针对游戏字体训练=读不准的根因）**和中间那版 numpy 移植（al_numpy）**，全部换回 **ALAS 原版 cnocr 1.2.2 + mxnet 1.9.1 + azur_lane 模型**（作者精调，UseOcrServer:false 走 OcrModel 直推）。mimov 起的头（d8bcb37 设备端跑通），我把它**做成从源码可复现的构建**。
2. **烘哪个 ALAS**：用户最终定=烘**官方上游 `github.com/LmeSzinc/AzurLaneAutoScript`（开箱即用）**，不是 AlasToFox。AlasToFox 由用户**运行时在 AOS 设置里「更新源」换源切换**（mimov 的 `3fdb62a` 功能）。★关键：`git://git.lyoko.io` 只能对官库做增量更新、**完整克隆会被拒**；换 AlasToFox 这类整仓拉取必须用 **GitHub/Gitee** 源或手动导入。★
3. **可复现**：构建走 **GHA `rootfs` workflow**（`ubuntu-24.04-arm`），已多次实跑成功。
4. **瘦身**：用户要求在推送空窗尽量瘦身、**每步留可回滚书面记录**。已做，见 `handoff/2026-09-26-slimming-log.md`。
5. **要精简版**（2026-09-26 最新）：66 上机 + 交付都用**精简版**（283MB rootfs）。

## 二、我的 commits（d8bcb37 之后，全部署名 opus-4.8；新→旧）
- `82a8b57` docs(slim)：瘦身收尾记录。
- `2ab5dbc` **Perf(build)：删 LLVM+mesa GL 软栈 ~182MB**（最终成功的瘦身刀）。
- `99f5a30` Fix：瘦身保留 gdcm（imgcodecs 直依赖）——中间失败迭代。
- `c20d18e` Fix：修 gdal 空壳创建的 ld 命令——中间失败迭代。
- `b45b36a` Perf：gdal 空壳方案（**已作废**，见踩坑）。
- `f66d1d7` Chore：加依赖链瘦身诊断 + 建瘦身记录。
- `1c26093` **Perf(build)：清 apt 缓存 -157MB**。
- `1aaaf84` **Fix：软链 libmxnet.so 进 mxnet 包目录**（修 "Cannot find the MXNet library"）。
- `531e551` Fix：mxnet whl 用合法文件名装。
- `2a4f9c2` **Add：把 mxnet aarch64 whl(28.8MB) 提交进仓**（GHA 复现用；`rootfs/wheels/`）。
- `15b98cb` **Upd(build)：原版 OCR(cnocr+mxnet) 烘进 rootfs 可复现，退役 PP-OCR**（核心改动）。

（另有未入 git 的实时流水 `.tmp/2026-09-25-live.md`，gitignore；两篇 handoff 已入库：`2026-09-26-ocr-reproducible-build.md`=OCR 配方，`2026-09-26-slimming-log.md`=瘦身可回滚记录。）

## 三、构建关键机制/事实（改在 `rootfs/build/build-rootfs.sh`）
- 仍烘 `ubuntu-base 24.04 / py3.12`（**不需要 py3.8**——mimov 定案 2 的 py3.8 路线已被 numpy 垫片取代作废）。
- OCR 依赖：pip 钉 `numpy==1.26.4 / scipy==1.13.1 / opencv-python-headless==4.10.0.84`；装 `mxnet 1.9.1`（仓库内置 whl，`rootfs/wheels/`）+ `cnocr==1.2.2 --no-deps`（推理路径不需 gluoncv）。
- **numpy 垫片** `rootfs/shims/{numpy_shim.py,zzz_alas_shim.pth}`：补 numpy≥1.24 删掉的别名（np.long/PZERO…）供 mxnet/cnocr；`.pth` 随 site 自启。
- **libmxnet.so 软链**：whl 把 .so 装进 `/usr/local/mxnet/`，须软链进 `dist-packages/mxnet/` 否则 `import mxnet` 报 "Cannot find the MXNet library"（1aaaf84 修）。
- `deploy.yaml`：`UseOcrServer:false`（原版链直推 OcrModel=cnocr）；`AutoUpdate:false` 保留。
- apt 补 `libopenblas0-pthread` + `libopencv-{core,imgproc,imgcodecs}406t64`（mxnet 的 libmxnet.so 硬链这些 so.406）+ binutils。
- import 硬门禁：构建期 chroot 内 `import mxnet`(dlopen libmxnet)+`import cnocr`+验 numpy 垫片，任一挂则构建失败。
- **GHA 触发**：Dreamry2C/ALAS-AOS 是 fork，push 到 rootfs/** **不自动触发**（fork 首跑）；无 gh.exe → 用 `git credential fill` 取 PAT（scope repo+workflow）走 REST API `workflow_dispatch`（见 moontier-github-release skill 同款手法）。代理 `127.0.0.1:7890`。
- **瘦身手术**（2ab5dbc）：只删 `libLLVM.so*`+mesa(`libgallium/libgbm/libglapi/libGLX_mesa/libEGL_mesa/dri`)——GL 软栈，mxnet 数值链不碰。★保留真 gdal+proj+gdcm+openexr★（imgcodecs 真用 gdal 符号 `GDALRasterBand::RasterIO`，gdal 空壳过不了 dlopen；gdcm/openexr 也是 imgcodecs 直接 DT_NEEDED）。

## 四、产物 / 体积
- rootfs.tar.xz：**461MB → 304MB（清 apt 缓存）→ 283MB（删 LLVM+mesa）**，-39%。
- **精简 rootfs 已下好**：`.tmp/rootfs-slim/rootfs.tar.xz`（283,196,504 B；rootfs_version `0.2.0-ocr`）——**下一步就用它编精简 release APK**。
- 之前那个**非精简** APK（app-debug.apk，rootfs 461MB，vC84，536MB）是给 66 验 OCR 用的中间物，**已被精简版取代，弃用**。
- APK 包名 `io.github.shinarin.alasaos`，debug 签名（`~/.android/debug.keystore`，CN=Android Debug）。

## 五、设备侧 66（`10.126.126.66:5555` 直连 / 中转 `8.148.231.10:15555` 时好时坏）
- 66 = Android10/arm64，`adb shell` 是 root；**无 su/magisk/shizuku**。碧蓝是 **360 渠道服，包名 `com.bilibili.blhx.qihoo`**（≠52 的 com.bilibili.azurlane）。/data 剩 ~47G。
- **激活办法（用户告知，务必照做）**：装好后开 AOS→弹窗**选 root 模式**（不是 shizuku）→打开后**从后台划掉杀死**→**重启 AOS**即获 root。**只要包名不变，容器一直给 root**。
- 66 曾经框架崩溃（/dev/binder 没了、无 zygote），**用户已重启 66** 恢复。
- **推送子代理 a12d7606**（我起的）在推那个非精简 536MB APK；因用户改要精简版，**它已作废**——其最终状态未知（可能已把 536MB 版装上 66，也可能还在推/已停）。下一 AI **先查 66 现状**（`pm list packages|grep alasaos`、`dumpsys package ... versionCode`），有旧包就卸了装精简版。
- mimov 阶段 66 曾跑通 AlasToFox 全栈（Login success、原版 cnocr OCR 加载、PRIMARY 全屏模式）。

## 六、接下来要做（按序）
> 进度（opus 续做）：**步骤 1 完成**——精简 APK vC94（361,962,262 B/~345MB，debug 签名，sha256 `52986d97c7a9565c964598dcfbfd756d4eff01f22fe5c1d4aad6eae9c814f0b6`）；app 内 BUILD_MANIFEST 更到 0.2.0-ocr（cdc0f19）。**seed_config 已改**（1dc514c）：去掉 PackageName/Dedithering 强制→PackageName 用 template 默认 `'auto'`，**ALAS 自动识别包名（含渠道服）→ 步骤 4「设渠道服包名」不再需要**。**步骤 2 进行中**——推送子代理正推 vC94 到 66 卸旧装新。步骤 3/5 待推送完成。
1. **编精简版 release APK**：`cp .tmp/rootfs-slim/rootfs.tar.xz app/app/src/main/assets/rootfs/rootfs.tar.xz` → 用 Moontier JDK17(`E:\GitRepository\Moontier\.build-tools\jdk17\jdk-17.0.16+8`)+`.tmp/gradle-dist/gradle-9.4.1`(`GRADLE_USER_HOME=.tmp/gradle-home`) 跑 `:app:assembleDebug` → `apksigner verify` 核 debug 签名。产物 `app/app/build/outputs/apk/debug/app-debug.apk`（~345MB）。
2. **推 66 装**：先查/卸旧包，`adb push` 到 /data/local/tmp 再 `pm install -r -d`（~30min 慢链；66 连接时好时坏，broken pipe 就重连重试）。
3. **激活**：开 AOS→选 root 模式→杀后台→重启（见 §五）。
4. **设渠道服包名**：把游戏包名设为 `com.bilibili.blhx.qihoo`（66=360 渠道服；seed_config 默认是 com.bilibili.azurlane，需覆盖——查 `rootfs/seeds/seed_config.py` 或 AOS/ALAS 配置页）。
5. **验原版 OCR**：跑起来看 ALAS 日志出现 `Loading OCR model: ./bin/cnocr_models/...` + 页面识别/读数正常（对比 PP-OCR 时代的误读）。
6. **（用户流程，可选）换 AlasToFox**：AOS 设置→更新源填 **GitHub/Gitee** 的 AlasToFox 仓 + 分支（**不能填 lyoko**，整仓克隆会被拒）→ 触发更新（git fetch+reset --hard）。
7. **修小 bug**：BUILD_MANIFEST 里 `cnocr_version` 打成了模块 repr——`cnocr.__version__` 是子模块非字符串；改用 `importlib.metadata.version('cnocr')`（在 build-rootfs.sh 的 manifest 生成段）。
8. **mimov 遗留尾巴**：Commission 滑动 `GameTooManyClickError`；前台模式非游戏前台时预览"套娃"；52 后台模式复验。

## 七、红线 / 勿动
- 不改 ALAS 上游逻辑（修复走 overlay/patches/seeds/构建钉版）；换源后 AlasToFox=用户仓可改，上游 LmeSzinc 不可改。
- **push 需用户授权**（已授权走 GHA/dispatch）；**不 force-push**（我全程只 append commit，历史干净）。
- 不清碧蓝数据；不随意重启云机（66 这次是用户特批重启的）。
- 每步改动单独 commit；GHA import 门禁挂 = 不安全，立即 `git revert`（回滚法见 `2026-09-26-slimming-log.md`）。
- mxnet whl 已进 git（28.8MB，2a4f9c2）；嫌历史膨胀可改 Git LFS / release 资产托管。
- 构建脚本本机（Windows）跑不了（要 chroot/aarch64）；只能 GHA 或云机 chroot。GHA 是当前主路径。


