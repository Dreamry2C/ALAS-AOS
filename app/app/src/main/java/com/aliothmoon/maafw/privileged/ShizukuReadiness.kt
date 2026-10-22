package com.aliothmoon.maafw.privileged

enum class ShizukuReadinessStage {
    /** 未安装 Shizuku，也没检测到 Sui */
    NotInstalled,

    /** 已安装但服务未启动 */
    NotRunning,

    /** 装的是官方版 Shizuku：与 shizuku-m 同包名不同签名，必须先卸载再装 shizuku-m */
    OfficialConflict,

    /** 检测到 Sui（Magisk 模块）提供服务 */
    SuiAvailable,

    /** 服务运行中但未授权 */
    NeedAuth,

    /** 就绪：已授权、当前后端不是 Shizuku，或用户已选跳过 */
    Ready,
}

/** moe.shizuku.privileged.api 这个包名下面装的到底是谁（shizuku-m 与官方版同包名） */
enum class ShizukuFlavor {
    NONE,
    OFFICIAL,
    MOD,
}

/** shizuku-m 下载页：本项目的配套分发，下载引导的首选源 */
const val SHIZUKU_M_RELEASES_URL = "https://github.com/Shinarin/shizuku-m/releases"

/** 官方 Shizuku 下载页：备选（装上会被判 OfficialConflict，再引导卸载换装 shizuku-m） */
const val SHIZUKU_OFFICIAL_RELEASES_URL = "https://github.com/RikkaApps/Shizuku/releases"

data class ShizukuReadiness(
    val stage: ShizukuReadinessStage = ShizukuReadinessStage.Ready,
    val canSwitchToRoot: Boolean = false,
) {
    val needsGuidance: Boolean
        get() = stage != ShizukuReadinessStage.Ready
}
