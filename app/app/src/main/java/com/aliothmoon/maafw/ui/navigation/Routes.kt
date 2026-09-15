package com.aliothmoon.maafw.ui.navigation

/**
 * 二级页面路由
 *
 * 主 tab（Alas/Settings）由 AppRoot 的 HorizontalPager 承载，
 * 不进 NavHost；NavHost 只承载推入式子页面，主 tab 路由仅作空占位
 */
object Routes {
    const val ALAS = "alas"
    const val SETTINGS = "settings"

    /** 主 tab 路由集合，用来判断当前是否停在主界面 */
    val mainTabs: Set<String> = setOf(ALAS, SETTINGS)

    /** 错误日志（app 自身的警告与错误） */
    const val APP_LOG = "app_log"

    /** 某一份错误日志的正文；file 是 `AppLogFileInfo.name` */
    const val APP_LOG_DETAIL = "app_log_detail/{file}"
    const val APP_LOG_DETAIL_ARG = "file"
    fun appLogDetail(fileName: String) = "app_log_detail/$fileName"
}
