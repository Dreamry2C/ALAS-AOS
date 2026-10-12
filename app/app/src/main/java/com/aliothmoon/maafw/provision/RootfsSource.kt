package com.aliothmoon.maafw.provision

import java.net.URI

/**
 * lite 构建的 rootfs 下载源模型：源类型 + 自定义直链 + 镜像前缀，纯 JVM 无 Android 依赖
 *
 * - GitHub 源 = 本仓 CI（app.yml 的 lite 发布步骤）滚动维护的 `rootfs-latest` pre-release；
 * - 自定义直链 = 用户自己给的 http(s) 文件地址；
 * - 镜像只对 GitHub 源生效（Moontier 同款前缀拼接：最终 URL = 镜像前缀 + 原始 URL），
 *   下载时按序尝试，失败自动换下一个，全部失败回落 GitHub 直链
 */
enum class RootfsSourceKind {
    GITHUB,
    CUSTOM,
}

object RootfsSource {

    /** CI 每次成功构建 lite 都会重建这个 pre-release（删旧建新），tag 恒定 */
    const val RELEASE_TAG = "rootfs-latest"

    /** GitHub 源的 rootfs 包地址 */
    const val GITHUB_ARCHIVE_URL =
        "https://github.com/Dreamry2C/ALAS-AOS/releases/download/$RELEASE_TAG/rootfs.tar.xz"

    /** GitHub 源的构建清单地址（解压版本闸门的 marker 版本来源） */
    const val GITHUB_MANIFEST_URL =
        "https://github.com/Dreamry2C/ALAS-AOS/releases/download/$RELEASE_TAG/BUILD_MANIFEST"

    /** 镜像前缀默认值，与 Moontier 的 DEFAULT_CORE_DOWNLOAD_PROXIES 同款 */
    const val DEFAULT_MIRRORS_JOINED = "https://ghfast.top/,https://gh-proxy.com/,https://mirror.ghproxy.com/"

    const val MIRROR_SEPARATOR = ","

    fun splitMirrors(joined: String): List<String> =
        joined.split(MIRROR_SEPARATOR)
            .map { it.trim() }
            .filter { it.isNotEmpty() }

    /** 镜像前缀拼接：补齐缺失的结尾斜杠（ghfast.top 与 ghfast.top/ 等价） */
    fun composeMirrorUrl(prefix: String, url: String): String {
        val trimmed = prefix.trim()
        return if (trimmed.endsWith("/")) trimmed + url else "$trimmed/$url"
    }

    /** 清单与包同目录：去掉地址最后一段路径接 BUILD_MANIFEST，兼容自定义直链的任意文件名 */
    fun manifestUrl(archiveUrl: String): String = archiveUrl.substringBeforeLast('/') + "/BUILD_MANIFEST"
}

/**
 * URL 合法性校验（纯函数，可单测）
 *
 * 红线：ALAS 官方国内 git 源（git.lyoko.io）与各处 AzurLaneAutoScript git 仓库
 * （github / gitee 的仓库本身及其 raw 域）都是 git 镜像，给不出 rootfs.tar.xz 文件，
 * 必须明确拒绝而不是让下载白转一圈再以 404/HTML 报错
 */
object RootfsSourceValidator {

    sealed interface Result {
        /** 校验通过；url 为 trim 后的原始直链（未拼镜像） */
        data class Valid(val url: String) : Result

        data class Rejected(val reason: Reason) : Result
    }

    enum class Reason {
        /** 空串或不是合法 URL */
        INVALID_URL,

        /** 协议不是 http/https */
        UNSUPPORTED_SCHEME,

        /** ALAS git 源地址：无法提供运行环境包 */
        BLOCKED_ALAS_SOURCE,
    }

    private val BLOCKED_HOSTS = setOf("git.lyoko.io")

    private val GIT_MIRROR_HOSTS = setOf("github.com", "gitee.com", "raw.githubusercontent.com", "codeload.github.com")

    private const val ALAS_REPO_SEGMENT = "azurlaneautoscript"

    fun validate(rawUrl: String): Result {
        val trimmed = rawUrl.trim()
        if (trimmed.isEmpty()) return Result.Rejected(Reason.INVALID_URL)
        val uri = runCatching { URI(trimmed) }.getOrElse { return Result.Rejected(Reason.INVALID_URL) }
        // 无 scheme（"github.com/x" 这类）按无效直链处理；有 scheme 但不是 http(s) 单独提示
        val scheme = uri.scheme?.lowercase() ?: return Result.Rejected(Reason.INVALID_URL)
        if (scheme != "http" && scheme != "https") {
            return Result.Rejected(Reason.UNSUPPORTED_SCHEME)
        }
        val host = uri.host?.lowercase()
        if (host.isNullOrEmpty()) return Result.Rejected(Reason.INVALID_URL)

        if (isAlasGitSource(host, uri.path)) {
            return Result.Rejected(Reason.BLOCKED_ALAS_SOURCE)
        }
        return Result.Valid(trimmed)
    }

    /**
     * 拦截 ALAS Git 源码仓库/克隆地址（无法提供首启运行环境大包）。
     * 若地址为正规的 Release 资产文件直链（如 /releases/download/...），即使仓库名包含 AzurLaneAutoScript 也不拦截。
     */
    private fun isAlasGitSource(host: String, path: String?): Boolean {
        if (host in BLOCKED_HOSTS) return true
        if (path.isNullOrEmpty() || host !in GIT_MIRROR_HOSTS) return false

        // Release 附件文件直链放行（避免用户自己的 fork 仓库名带 AzurLaneAutoScript 被误伤）
        if (path.contains("/releases/download/")) return false

        val segments = path.split('/').filter { it.isNotEmpty() }
        return segments.any { it.removeSuffix(".git").equals(ALAS_REPO_SEGMENT, ignoreCase = true) }
    }
}

/** 用户在首启页配置好的下载源；[candidateUrls] 给出按序尝试的完整候选 */
data class RootfsDownloadSource(
    val kind: RootfsSourceKind,
    val customUrl: String = "",
    val useMirror: Boolean = false,
    val mirrors: List<String> = emptyList(),
) {
    /**
     * 依次尝试的下载地址：
     * - GitHub 源勾了镜像 → 镜像候选在前、GitHub 直链兜底；
     * - 自定义直链 → 只有这一个候选（镜像不生效，直链用户自管加速）
     */
    fun candidateUrls(): List<String> = when (kind) {
        RootfsSourceKind.GITHUB -> {
            val direct = listOf(RootfsSource.GITHUB_ARCHIVE_URL)
            if (useMirror) {
                mirrors.filter { it.isNotBlank() }.map { RootfsSource.composeMirrorUrl(it, RootfsSource.GITHUB_ARCHIVE_URL) } + direct
            } else {
                direct
            }
        }

        RootfsSourceKind.CUSTOM -> listOf(customUrl.trim())
    }
}
