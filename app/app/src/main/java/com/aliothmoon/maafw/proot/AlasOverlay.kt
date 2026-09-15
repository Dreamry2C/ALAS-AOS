package com.aliothmoon.maafw.proot

import android.content.Context
import timber.log.Timber
import java.io.File

/**
 * App 资产 `alas/` 对 rootfs `/opt/alas` 的运行时覆盖
 *
 * 两份职责：
 * - wrapper/runner/seed/maaal_update.sh 随 App 版本演进，改它们不必重烘焙 rootfs
 *   （rootfs.tar.xz 里那份只是兜底；每次启动都被这里盖成 App 当前版本）
 * - 热更新 `git reset --hard` 会把上游跟踪文件打回原版：patches（module/ 与 assets/）
 *   与 in-proc OCR rpc.py 必须在 UPDATED 后重放
 *
 * 覆盖方式是按字节比对的幂等拷贝；assets_fix.py 只铺到 seeds/（执行要 python，
 * 由 ProotHost 经 proot 另行触发——它幂等且带漂移自检，找不到 Button 会非零退出）
 */
class AlasOverlay(private val context: Context) {

    data class Result(val copied: Int, val skipped: Int, val failed: Int)

    /** 把全部映射铺到 [alasDir]；返回统计，failed>0 由调用方决定是否中止启动 */
    fun apply(alasDir: File): Result {
        var copied = 0
        var skipped = 0
        var failed = 0
        for ((assetRoot, targetRoot) in MAPPINGS) {
            val (c, s, f) = copyTree(assetRoot, File(alasDir, targetRoot))
            copied += c; skipped += s; failed += f
        }
        Timber.i("ALAS overlay applied: copied=%d skipped=%d failed=%d", copied, skipped, failed)
        return Result(copied, skipped, failed)
    }

    /** 递归铺一棵资产子树；AssetManager.list 对文件返回空数组，据此区分文件/目录 */
    private fun copyTree(assetPath: String, target: File): Triple<Int, Int, Int> {
        val children = context.assets.list(assetPath) ?: return Triple(0, 0, 1)
        if (children.isEmpty()) return copyFile(assetPath, target)
        var copied = 0
        var skipped = 0
        var failed = 0
        for (name in children) {
            val (c, s, f) = copyTree("$assetPath/$name", File(target, name))
            copied += c; skipped += s; failed += f
        }
        return Triple(copied, skipped, failed)
    }

    private fun copyFile(assetPath: String, target: File): Triple<Int, Int, Int> {
        return runCatching {
            val bytes = context.assets.open(assetPath).use { it.readBytes() }
            if (target.isFile && target.readBytes().contentEquals(bytes)) {
                return Triple(0, 1, 0)
            }
            target.parentFile?.mkdirs()
            target.writeBytes(bytes)
            if (assetPath.endsWith(".sh")) target.setExecutable(true, false)
            Triple(1, 0, 0)
        }.getOrElse {
            Timber.w(it, "overlay copy failed: %s", assetPath)
            Triple(0, 0, 1)
        }
    }

    private companion object {
        /** (资产子树 → /opt/alas 内目标子树) */
        val MAPPINGS = listOf(
            "alas/overlay" to "",
            "alas/patches/module" to "module",
            "alas/patches/assets" to "assets",
            "alas/patches/assets_fix.py" to "seeds/assets_fix.py",
        )
    }
}
