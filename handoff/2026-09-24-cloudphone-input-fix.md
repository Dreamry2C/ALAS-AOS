# 2026-09-24 云机输入串屏修复（安装验证进行中）

- 目标设备：10.126.126.52:5555，Android 10/API 29，adb root。
- 用户授权本地 commit、构建、安装；追加要求先 commit 再编译，若失败撤回本次 commit 后修复重做。禁止 push/release；禁止重启云机、停止 Moontier、动碧蓝航线数据。
- 已确认根因与修复见 debug.md 2026-09-24 两条及 devlog 最新条目。只改自有桥：deviceId=-1、精确显示屏前台解析；补回误忽略的配置存储源码。
- 验证：8 个 Python unittest 通过；云机独立输入探针 -1 的 DOWN/UP 均成功且命中 VD 游戏；提交前 debug 编译通过。完整 APK 安装启动回归尚未完成。
- 此刻设备 AOS 已 force-stop，调度器已停，VD 清到仅 display 0；游戏数据未改，Moontier 网络连接保持。
- 原 APK：`.tmp/cloud-original-v014.apk`；原 AOS 内外部私有数据备份：设备 `/data/local/tmp/alasaos-cloud-backup-20260924/{internal,external}`（1GB）。剩余 /data 4.5GB。签名不一致可按用户授权卸载 AOS、安装后恢复备份，务必恢复新 UID 权限；不修改系统签名校验。
- rootfs 已从原 APK 提取到 gitignored 的 app/app/src/main/assets/rootfs/rootfs.tar.xz。
- JDK：`E:/GitRepository/Moontier/.build-tools/jdk17/jdk-17.0.16+8`；SDK 同项目 `.build-tools/android-sdk`；Gradle：本项目 `.tmp/gradle-dist/gradle-9.4.1`，GRADLE_USER_HOME=`.tmp/gradle-home`。Gradle 命令参数 `'-Pandroid.builder.sdkDownload=false'` 在 PowerShell 要加引号。
- GitHub 下载走用户指定代理 `http://127.0.0.1:7890`。Gradle 9.3.1 不满足 AGP 9.2.1 的最低 9.4.1 要求。
- 实时步骤记录：`.tmp/2026-09-24-cloudphone-debug.md`；构建日志 `.tmp/cloud-build-debug.log`；证据 `.tmp/cloud-input-probe-result.txt` 与 cloud-inputservice-dex.txt。
- 下一步：提交本次文件 → 重建带 commit 版本的 APK → 核签名并安装/恢复 AOS 数据 → 验证内嵌登录、手动全屏触摸与 ALAS 自动登录 → 停调度器清 VD → 更新最终验证账册。
