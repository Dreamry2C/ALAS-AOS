package com.aliothmoon.maafw.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.core.graphics.drawable.IconCompat
import com.aliothmoon.maafw.MainActivity
import com.aliothmoon.maafw.R
import com.aliothmoon.maafw.runner.RunnerPhase
import com.aliothmoon.maafw.runner.RunnerPort
import com.aliothmoon.maafw.runner.RunnerState
import com.aliothmoon.maafw.runner.isBusy
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.koin.android.ext.android.inject
import timber.log.Timber

/**
 * 执行期间把 app 进程钉成前台
 *
 * 不是为了显示进度——是为了活着：app 进程一死，特权进程的看门狗随即自杀并释放虚拟屏，
 * 表现成「任务跑一半自己停了」。实测 MIUI 的 ProcessManager 会对 Adj=905 的空进程
 * 直接 force-stop（`SwipeUpClean: force-stop <pkg> Adj=905`），前台服务是唯一挡得住的一层
 *
 * 同一条通知顺带走 Live Update：进度来自 [RunnerState]
 *
 * 只提供 [start] 不提供外部 stop：`startForegroundService` 之后若 `stopService` 抢在
 * onCreate 之前到达，系统会因 startForeground 未调用直接杀进程。终态退出由本服务自己
 * 观察 [RunnerPort.state] 完成
 */
class RunForegroundService : Service() {

    private val runnerPort: RunnerPort by inject()

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var observeJob: Job? = null

    /** 通知刷新节流的上次落点；进度回调能一秒来好几条 */
    private var lastUpdateAt = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        // 必须先 startForeground 再判终态：慢一步就是 ForegroundServiceDidNotStartInTimeException
        val initial = runnerPort.state.value
        startAsForeground(buildNotification(initial))
        if (!initial.phase.isBusy) {
            stopNow()
            return
        }
        observe()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // 系统可能只走 onStartCommand；FGS 提升要在这里再保一次
        val snapshot = runnerPort.state.value
        startAsForeground(buildNotification(snapshot))
        if (!snapshot.phase.isBusy) {
            stopNow()
        } else {
            observe()
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        observeJob = null
        serviceScope.cancel()
        super.onDestroy()
    }

    private fun observe() {
        if (observeJob?.isActive == true) return
        observeJob = serviceScope.launch { observeProgress() }
    }

    private suspend fun observeProgress() {
        var lastPostedPhase: RunnerPhase? = null
        runnerPort.state.collectLatest { state ->
            if (!state.phase.isBusy) {
                lastPostedPhase = null
                stopNow()
                return@collectLatest
            }
            val now = SystemClock.elapsedRealtime()
            val wait = MIN_UPDATE_INTERVAL_MS - (now - lastUpdateAt)
            if (wait > 0 && state.phase == lastPostedPhase) delay(wait)
            if (!runnerPort.state.value.phase.isBusy) {
                lastPostedPhase = null
                stopNow()
                return@collectLatest
            }
            lastUpdateAt = SystemClock.elapsedRealtime()
            lastPostedPhase = state.phase
            notify(buildNotification(state))
        }
    }

    private fun stopNow() {
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun ensureChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_run),
            // LOW：常驻不该出声。MIN 进不了状态栏，部分 ROM 还当成前台服务不成立；
            // Live Update 也只禁 MIN。重要性建成就改不了，沿用 run_execution
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.notification_channel_run_desc)
            setShowBadge(false)
        }
        notificationManager.createNotificationChannel(channel)
    }

    private fun startAsForeground(notification: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun buildNotification(state: RunnerState): Notification {
        val snapshot = RunProgressSnapshots.from(state.phase, state.activeExecution, null)
        val style = NotificationCompat.ProgressStyle()
            .setStyledByProgress(true)
            .setProgressIndeterminate(snapshot.indeterminate)
            .setProgressTrackerIcon(
                IconCompat.createWithResource(this, R.drawable.ic_progress_tracker),
            )
            .addProgressSegment(
                NotificationCompat.ProgressStyle.Segment(RunProgressSnapshots.PROGRESS_MAX)
                    .setColor(snapshot.barColor),
            )
        if (!snapshot.indeterminate) {
            style.setProgress(snapshot.progress)
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(snapshot.barColor)
            .setContentTitle(getString(snapshot.title.stringRes))
            .setContentText(snapshot.contentText.takeIf { it.isNotBlank() })
            // ProgressStyle 只在 36+ 生效；经典模板仍靠 setProgress，否则 9–15 没有条子
            .setProgress(
                RunProgressSnapshots.PROGRESS_MAX,
                snapshot.progress,
                snapshot.indeterminate,
            )
            .setStyle(style)
            .setContentIntent(contentIntent())
            .setOngoing(true)
            .setRequestPromotedOngoing(notificationManager.canRequestPromotedOngoing())
            .setSilent(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .apply {
                snapshot.shortCriticalText?.let { setShortCriticalText(it) }
            }
            .build()
    }

    /** 通知权限被拒时 notify/cancel 会抛 SecurityException，不能让它掀翻 FGS 主线程 */
    private fun notify(notification: Notification) {
        runCatching { notificationManager.notify(NOTIFICATION_ID, notification) }
            .onFailure { Timber.w(it, "Failed to update run notification") }
    }

    private val notificationManager: NotificationManager
        get() = getSystemService(NOTIFICATION_SERVICE) as NotificationManager

    private fun contentIntent(): PendingIntent {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        return PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
    }

    companion object {
        private const val CHANNEL_ID = "run_execution"
        private const val NOTIFICATION_ID = 1001
        private const val MIN_UPDATE_INTERVAL_MS = 1_000L

        fun start(context: Context) {
            runCatching {
                context.startForegroundService(Intent(context, RunForegroundService::class.java))
            }.onFailure { Timber.w(it, "Failed to start foreground service") }
        }
    }
}
