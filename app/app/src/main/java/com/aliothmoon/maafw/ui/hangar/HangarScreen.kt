package com.aliothmoon.maafw.ui.hangar

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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
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
import com.aliothmoon.maafw.ui.components.maaClickable
import kotlinx.coroutines.launch
import org.koin.compose.koinInject

/**
 * 挂机 tab：虚拟屏实时画面 + 运行配置选择 + ALAS 控制面板
 *
 * 画面走 native bridge_preview 通道（AIDL setMonitorSurface，零拷贝）；
 * 预览面本体是 AppRoot 持有的 movableContent（见 HangarPreview.kt），点卡片进全屏时搬走，
 * 页面不可见即摘面，不给看不到的画面白烧帧。
 * 配置面（改任务参数）仍在 ALAS WebUI tab，本页只选「跑哪个配置」
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HangarScreen(
    active: Boolean,
    previewContent: (@Composable () -> Unit)?,
    onEnterFullscreen: () -> Unit,
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
                envUp = snapshot.environmentUp,
                onStartEnv = { scope.launch { hostState.ensureEnvironmentStarted() } },
                content = previewContent,
                onEnterFullscreen = onEnterFullscreen,
                modifier = Modifier.fillMaxWidth(),
            )
            ConfigCard(alas = alas, onSelect = alasController::selectConfig)
            AlasControlPanel(
                snapshot = snapshot,
                alas = alas,
                onAlasStart = { alasController.startAlas() },
                onAlasStop = { alasController.stopAlas() },
                onToolStart = { alasController.startTool(it) },
                onToolStop = { alasController.stopTool() },
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
            )
        }
    }
}

/**
 * 虚拟屏画面卡：环境在跑显示实时预览，没跑给占位 + 一键拉起
 *
 * 内嵌画面只响应「单击进全屏」，不转发触摸（防误触）；
 * [content] 为 null 表示画面已搬去全屏宿主，显示占位
 */
@Composable
private fun VdPreview(
    envUp: Boolean,
    onStartEnv: () -> Unit,
    content: (@Composable () -> Unit)?,
    onEnterFullscreen: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .aspectRatio(DefaultDisplayConfig.WIDTH.toFloat() / DefaultDisplayConfig.HEIGHT)
            .clip(MaterialTheme.shapes.medium)
            .background(Color.Black),
        contentAlignment = Alignment.Center,
    ) {
        when {
            envUp && content != null -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .maaClickable(onClick = onEnterFullscreen),
                ) {
                    content()
                }
            }

            envUp -> PreviewPlaceholder(
                textRes = R.string.hangar_preview_moved,
            )

            else -> {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm),
                ) {
                    PreviewPlaceholder(textRes = R.string.hangar_env_down)
                    MaaButton(onClick = onStartEnv) {
                        Text(stringResource(R.string.hangar_env_start))
                    }
                }
            }
        }
    }
}

@Composable
private fun PreviewPlaceholder(textRes: Int) {
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
            text = stringResource(textRes),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
                .copy(alpha = MaaDesignTokens.Alpha.disabledContent),
        )
    }
}

/**
 * 运行配置选择：列出 config/ 下的实例名（wrapper /configs）。
 * 一行形制：左标签，右下拉按钮直接显示当前配置名（点击展开切换）。
 * 调度器在跑时锁选择——生效配置以 /status 回报的 runningConfig 为准，选择下次启动生效
 */
@Composable
private fun ConfigCard(
    alas: AlasRunState,
    onSelect: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    MaaCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.hangar_config_label),
                style = MaterialTheme.typography.titleMedium,
            )
            Box {
                MaaOutlinedButton(
                    onClick = { expanded = true },
                    enabled = !alas.runnerAlive && alas.configs.isNotEmpty(),
                ) {
                    Text(
                        text = if (alas.runnerAlive) {
                            alas.runningConfig ?: alas.selectedConfig
                        } else {
                            alas.selectedConfig
                        },
                    )
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
