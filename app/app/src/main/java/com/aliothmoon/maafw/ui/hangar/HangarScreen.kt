package com.aliothmoon.maafw.ui.hangar

import android.graphics.PixelFormat
import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowDropDown
import androidx.compose.material.icons.outlined.OndemandVideo
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aliothmoon.maafw.R
import com.aliothmoon.maafw.constant.DefaultDisplayConfig
import com.aliothmoon.maafw.proot.AlasRunController
import com.aliothmoon.maafw.proot.AlasRunState
import com.aliothmoon.maafw.service.HostState
import com.aliothmoon.maafw.theme.MaaDesignTokens
import com.aliothmoon.maafw.ui.components.AlasControlPanel
import com.aliothmoon.maafw.ui.components.MaaButton
import com.aliothmoon.maafw.ui.components.MaaCard
import com.aliothmoon.maafw.ui.components.MaaOutlinedButton
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.koin.compose.koinInject

/**
 * setFixedSize 必须延后一拍（上游 MaaPreviewSurface 同款处理）：
 * surfaceCreated 里同步调会被 attach 流程吞掉，画面按错误比例贴上来
 */
private const val FIXED_SIZE_DELAY_MS = 50L

/**
 * 挂机 tab：虚拟屏实时画面 + 运行配置选择 + ALAS 控制面板
 *
 * 画面走 native bridge_preview 通道（AIDL setMonitorSurface，零拷贝）；
 * 页面不可见即摘面，不给看不到的画面白烧帧。
 * 配置面（改任务参数）仍在 ALAS WebUI tab，本页只选「跑哪个配置」
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HangarScreen(
    active: Boolean,
    modifier: Modifier = Modifier,
    hostState: HostState = koinInject(),
    alasController: AlasRunController = koinInject(),
) {
    val snapshot by hostState.snapshot.collectAsStateWithLifecycle()
    val alas by alasController.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()

    // 本页可见且特权连接就绪时自动补一次「开始」链路建虚拟屏（HostState 内幂等）
    LaunchedEffect(active, snapshot.privilegedConnected) {
        if (active && snapshot.privilegedConnected) {
            hostState.ensureEnvironmentStarted()
        }
    }

    Column(modifier = modifier.fillMaxSize()) {
        TopAppBar(
            title = {
                Text(
                    text = stringResource(R.string.nav_hangar),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.SemiBold,
                )
            },
            // AppRoot 的 Scaffold 已吃掉状态栏顶部 inset，这里不能再加一次
            windowInsets = WindowInsets(0, 0, 0, 0),
            colors = TopAppBarDefaults.topAppBarColors(
                containerColor = MaterialTheme.colorScheme.background,
                titleContentColor = MaterialTheme.colorScheme.onBackground,
            ),
        )
        Column(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(
                    start = MaaDesignTokens.Spacing.lg,
                    end = MaaDesignTokens.Spacing.lg,
                    bottom = MaaDesignTokens.Spacing.md,
                ),
            verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.md),
        ) {
            VdPreview(
                active = active,
                envUp = snapshot.environmentUp,
                hostState = hostState,
                onStartEnv = { scope.launch { hostState.ensureEnvironmentStarted() } },
                modifier = Modifier.fillMaxWidth(),
            )
            ConfigCard(alas = alas, onSelect = alasController::selectConfig)
            AlasControlPanel(
                snapshot = snapshot,
                alas = alas,
                onAlasStart = { alasController.startAlas() },
                onAlasStop = { alasController.stopAlas() },
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
            )
        }
    }
}

/** 虚拟屏画面卡：环境在跑显示实时预览，没跑给占位 + 一键拉起 */
@Composable
private fun VdPreview(
    active: Boolean,
    envUp: Boolean,
    hostState: HostState,
    onStartEnv: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .aspectRatio(DefaultDisplayConfig.WIDTH.toFloat() / DefaultDisplayConfig.HEIGHT)
            .clip(MaterialTheme.shapes.medium)
            .background(Color.Black),
        contentAlignment = Alignment.Center,
    ) {
        if (envUp) {
            PreviewSurface(
                active = active,
                hostState = hostState,
                modifier = Modifier.fillMaxSize(),
            )
        } else {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm),
            ) {
                Icon(
                    imageVector = Icons.Outlined.OndemandVideo,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                        .copy(alpha = MaaDesignTokens.Alpha.disabledContent),
                    modifier = Modifier.size(MaaDesignTokens.IconSize.lg),
                )
                Text(
                    text = stringResource(R.string.hangar_env_down),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                        .copy(alpha = MaaDesignTokens.Alpha.disabledContent),
                )
                MaaButton(onClick = onStartEnv) {
                    Text(stringResource(R.string.hangar_env_start))
                }
            }
        }
    }
}

/**
 * 预览面：SurfaceView 尺寸对齐虚拟屏后把 Surface 交给特权进程渲染
 *
 * 已挂上的 Surface 记在 [attachedSurface]：tab 切走（active=false）摘除，
 * 切回来时 SurfaceView 还活着（pager 预组合），surfaceChanged 不会再发，靠它重挂
 */
@Composable
private fun PreviewSurface(
    active: Boolean,
    hostState: HostState,
    modifier: Modifier = Modifier,
) {
    var surfaceReady by remember { mutableStateOf(false) }
    var attachedSurface by remember { mutableStateOf<Surface?>(null) }
    val currentActive by rememberUpdatedState(active)
    val scope = rememberCoroutineScope()

    DisposableEffect(active) {
        if (active) {
            attachedSurface?.let { hostState.attachPreviewSurface(it) }
        } else {
            hostState.detachPreviewSurface()
        }
        onDispose { }
    }

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { context ->
                SurfaceView(context).apply {
                    holder.setFormat(PixelFormat.RGBA_8888)
                    holder.addCallback(object : SurfaceHolder.Callback {
                        override fun surfaceCreated(holder: SurfaceHolder) {
                            scope.launch {
                                delay(FIXED_SIZE_DELAY_MS)
                                holder.setFixedSize(
                                    DefaultDisplayConfig.WIDTH,
                                    DefaultDisplayConfig.HEIGHT,
                                )
                            }
                        }

                        override fun surfaceChanged(
                            holder: SurfaceHolder,
                            format: Int,
                            width: Int,
                            height: Int,
                        ) {
                            if (width == DefaultDisplayConfig.WIDTH &&
                                height == DefaultDisplayConfig.HEIGHT
                            ) {
                                attachedSurface = holder.surface
                                surfaceReady = true
                                if (currentActive) {
                                    hostState.attachPreviewSurface(holder.surface)
                                }
                            }
                        }

                        override fun surfaceDestroyed(holder: SurfaceHolder) {
                            attachedSurface = null
                            surfaceReady = false
                            hostState.detachPreviewSurface()
                        }
                    })
                }
            },
        )
        if (!surfaceReady) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm),
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.size(MaaDesignTokens.IconSize.md),
                    strokeWidth = MaaDesignTokens.Border.marker,
                    color = Color.LightGray,
                )
                Text(
                    text = stringResource(R.string.hangar_preview_waiting),
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.LightGray,
                )
            }
        }
    }
}

/**
 * 运行配置选择：列出 config/ 下的实例名（wrapper /configs）。
 * 调度器在跑时锁选择——生效配置以 /status 回报的 runningConfig 为准，选择下次启动生效
 */
@Composable
private fun ConfigCard(
    alas: AlasRunState,
    onSelect: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    MaaCard(title = stringResource(R.string.hangar_config_label)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(
                    text = if (alas.runnerAlive) {
                        alas.runningConfig ?: alas.selectedConfig
                    } else {
                        alas.selectedConfig
                    },
                    style = MaterialTheme.typography.titleMedium,
                )
                if (alas.runnerAlive) {
                    Text(
                        text = stringResource(R.string.hangar_config_running_hint),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Box {
                MaaOutlinedButton(
                    onClick = { expanded = true },
                    enabled = !alas.runnerAlive && alas.configs.isNotEmpty(),
                ) {
                    Text(stringResource(R.string.hangar_config_switch))
                    Icon(
                        imageVector = Icons.Outlined.ArrowDropDown,
                        contentDescription = null,
                        modifier = Modifier.size(MaaDesignTokens.IconSize.sm),
                    )
                }
                DropdownMenu(
                    expanded = expanded,
                    onDismissRequest = { expanded = false },
                ) {
                    alas.configs.forEach { name ->
                        DropdownMenuItem(
                            text = { Text(name) },
                            onClick = {
                                onSelect(name)
                                expanded = false
                            },
                        )
                    }
                }
            }
        }
    }
}
