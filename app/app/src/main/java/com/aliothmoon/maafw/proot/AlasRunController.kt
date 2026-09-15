package com.aliothmoon.maafw.proot

import com.aliothmoon.maafw.MaaDispatchers
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import timber.log.Timber
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean

/**
 * ALAS 调度器运行态：悬浮窗「开始/停止挂机」与日志板的数据源
 *
 * 数据全部来自 wrapper 薄 HTTP（127.0.0.1:22400，rootfs wrapper.py）：
 * - GET /status → runner_alive/pid/gui_alive/log_lines
 * - POST /start、POST /stop → 调度器启停（幂等；/stop 内部 SIGTERM→3s→SIGKILL，响应偏慢）
 * - GET /logs?tail=N → 纯文本日志尾。语义：按 mtime 取 log/ 下最新 *.txt——
 *   调度器在跑时是它的 {date}_alas.txt，没跑时多半是 gui 启动日志，均够悬浮窗一瞥
 *
 * 4s 轮询；wrapper 不可达不视为错误（proot 会话没起/正在起，reachable=false 即可）。
 * 双头管理注意：WebUI 的启停按钮走 ProcessManager，与本通道并存时不要两边都点
 * （roadmap 阶段四决策：悬浮窗是唯一控制面，WebUI 按钮别用，见 docs/spike-d-wrapper-surface.md）
 */
data class AlasRunState(
    val reachable: Boolean = false,
    val runnerAlive: Boolean = false,
    val pid: Int? = null,
    val guiAlive: Boolean = false,
    val logLines: Int = 0,
    val logTail: List<String> = emptyList(),
    val busy: Boolean = false,
)

class AlasRunController(
    private val scope: CoroutineScope,
) {

    private val _state = MutableStateFlow(AlasRunState())
    val state = _state.asStateFlow()

    private val started = AtomicBoolean(false)
    private val refreshMutex = Mutex()

    /** 幂等：挂到 MaaFwApp.postCreate，轮询整个 App 生命周期 */
    fun start() {
        if (!started.compareAndSet(false, true)) return
        scope.launch(MaaDispatchers.IO) {
            while (true) {
                refreshMutex.withLock { refreshLocked() }
                delay(POLL_MS)
            }
        }
    }

    fun startAlas() = postThenRefresh("$BASE/start")

    fun stopAlas() = postThenRefresh("$BASE/stop")

    private fun postThenRefresh(url: String) {
        scope.launch(MaaDispatchers.IO) {
            _state.update { it.copy(busy = true) }
            runCatching {
                val conn = URL(url).openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.connectTimeout = HTTP_TIMEOUT_MS
                // /stop 要等进程组死掉（SIGTERM→3s→SIGKILL），读超时给足
                conn.readTimeout = POST_READ_TIMEOUT_MS
                conn.inputStream.use { it.readBytes() }
            }.onFailure { Timber.w(it, "alas POST %s failed", url) }
            refreshMutex.withLock { refreshLocked() }
            _state.update { it.copy(busy = false) }
        }
    }

    /** 可达即拉日志尾：loopback 读文件尾部开销可忽略，空闲时 gui 启动日志恰是排障现场 */
    private fun refreshLocked() {
        val body = get("$BASE/status", HTTP_TIMEOUT_MS)
        if (body == null) {
            _state.update {
                it.copy(
                    reachable = false, runnerAlive = false, pid = null,
                    guiAlive = false, logLines = 0, logTail = emptyList(),
                )
            }
            return
        }
        val j = runCatching { JSONObject(body) }.getOrNull() ?: return
        val runnerAlive = j.optBoolean("runner_alive")
        val pid = if (j.isNull("pid")) null else j.optInt("pid")
        val guiAlive = j.optBoolean("gui_alive")
        val logLines = j.optInt("log_lines")
        val tail = get("$BASE/logs?tail=$LOG_TAIL", HTTP_TIMEOUT_MS)
            ?.split('\n')
            ?.filter { it.isNotBlank() }
            ?: _state.value.logTail
        _state.update {
            it.copy(
                reachable = true, runnerAlive = runnerAlive, pid = pid,
                guiAlive = guiAlive, logLines = logLines, logTail = tail,
            )
        }
    }

    private fun get(url: String, timeoutMs: Int): String? = runCatching {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        if (conn.responseCode != 200) return null
        conn.inputStream.use { String(it.readBytes(), Charsets.UTF_8) }
    }.onFailure { Timber.d(it, "alas GET %s failed", url) }.getOrNull()

    private companion object {
        const val BASE = "http://127.0.0.1:${ProotHost.WRAPPER_PORT}"
        const val POLL_MS = 4_000L
        const val HTTP_TIMEOUT_MS = 1_500
        const val POST_READ_TIMEOUT_MS = 12_000
        const val LOG_TAIL = 80
    }
}
