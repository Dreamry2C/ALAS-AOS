package com.aliothmoon.maafw.overlay

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.LockOpen
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.sp
import com.aliothmoon.maafw.R
import com.aliothmoon.maafw.constant.DefaultDisplayConfig
import com.aliothmoon.maafw.proot.AlasRunState
import com.aliothmoon.maafw.service.HostSnapshot
import com.aliothmoon.maafw.theme.MaaDesignTokens
import com.aliothmoon.maafw.theme.MaaTheme
import com.aliothmoon.maafw.ui.components.MaaButton

/**
 * 悬浮控制面板：环境状态的仪表盘 + 环境/调度器两级启停 + ALAS 日志板
 *
 * 调度器控制面只此一处（wrapper 薄 HTTP）；WebUI 里的启停按钮走 ProcessManager，
 * 双头同用会抢设备——别用（见 AlasRunController 头注）
 */
@Composable
fun OverlayPanel(
    snapshot: HostSnapshot,
    alas: AlasRunState,
    isLocked: Boolean,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onAlasStart: () -> Unit,
    onAlasStop: () -> Unit,
    onBackToApp: () -> Unit,
    onLockToggle: (Boolean) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxSize(),
        shape = MaterialTheme.shapes.large,
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = MaaTheme.style.cardElevation,
        shadowElevation = MaaTheme.style.cardElevation,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(MaaTheme.style.cardInnerPadding),
            verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.md),
        ) {
            PanelHeader(isLocked, onLockToggle, onClose)
            Column(verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm)) {
                StatusRow(
                    labelRes = R.string.overlay_host_privileged,
                    value = stringResource(
                        if (snapshot.privilegedConnected) {
                            R.string.host_state_connected
                        } else {
                            R.string.host_state_disconnected
                        }
                    ),
                )
                StatusRow(
                    labelRes = R.string.overlay_host_bridge,
                    value = stringResource(
                        if (snapshot.bridgeReachable) {
                            R.string.host_state_ok
                        } else {
                            R.string.host_state_unreachable
                        }
                    ),
                )
                StatusRow(
                    labelRes = R.string.overlay_host_display,
                    value = if (snapshot.vdDisplayId != DefaultDisplayConfig.DISPLAY_NONE) {
                        "#${snapshot.vdDisplayId}"
                    } else {
                        stringResource(R.string.host_state_display_none)
                    },
                )
                StatusRow(
                    labelRes = R.string.overlay_alas_status,
                    value = when {
                        !alas.reachable -> stringResource(R.string.overlay_alas_unreachable)
                        alas.runnerAlive -> stringResource(R.string.overlay_alas_running, alas.pid ?: 0)
                        else -> stringResource(R.string.overlay_alas_stopped)
                    },
                )
            }
            AlasLogBoard(
                lines = alas.logTail,
                linesCount = alas.logLines,
                modifier = Modifier.weight(1f),
            )
            MaaButton(
                onClick = if (alas.runnerAlive) onAlasStop else onAlasStart,
                enabled = alas.reachable && !alas.busy,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    stringResource(
                        if (alas.runnerAlive) {
                            R.string.overlay_alas_stop
                        } else {
                            R.string.overlay_alas_start
                        }
                    )
                )
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm),
            ) {
                MaaButton(
                    onClick = onBackToApp,
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(
                        Icons.Outlined.Home,
                        contentDescription = null,
                        Modifier.size(MaaDesignTokens.IconSize.sm)
                    )
                    Text(
                        text = stringResource(R.string.overlay_back_to_app),
                        modifier = Modifier.padding(start = MaaDesignTokens.Spacing.xs),
                    )
                }
                MaaButton(
                    onClick = if (snapshot.environmentUp) onStop else onStart,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(
                        stringResource(
                            if (snapshot.environmentUp) {
                                R.string.overlay_host_stop
                            } else {
                                R.string.overlay_host_start
                            }
                        )
                    )
                }
            }
        }
    }
}

/** 半透明黑底日志板：新日志自动沉底；无内容时给占位提示 */
@Composable
private fun AlasLogBoard(lines: List<String>, linesCount: Int, modifier: Modifier = Modifier) {
    val scrollState = rememberScrollState()
    LaunchedEffect(linesCount, lines.size) { scrollState.scrollTo(scrollState.maxValue) }
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.medium,
        color = Color.Black.copy(alpha = 0.55f),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(MaaDesignTokens.Spacing.sm),
        ) {
            if (lines.isEmpty()) {
                Text(
                    text = stringResource(R.string.overlay_alas_log_empty),
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.LightGray,
                )
            } else {
                Text(
                    text = lines.joinToString("\n"),
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontFamily = FontFamily.Monospace,
                        fontSize = 10.sp,
                        lineHeight = 13.sp,
                    ),
                    color = Color(0xFFDDDDDD),
                )
            }
        }
    }
}

@Composable
private fun StatusRow(labelRes: Int, value: String) {
    Text(
        text = stringResource(labelRes, value),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun PanelHeader(
    isLocked: Boolean,
    onLockToggle: (Boolean) -> Unit,
    onClose: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.overlay_panel_title),
            style = MaterialTheme.typography.titleLarge,
            modifier = Modifier.weight(1f),
        )
        // 锁住即禁止拖拽：面板压在目标应用上，误拖会把它拽出可视区
        IconButton(onClick = { onLockToggle(!isLocked) }) {
            Icon(
                imageVector = if (isLocked) Icons.Outlined.Lock else Icons.Outlined.LockOpen,
                contentDescription = stringResource(
                    if (isLocked) R.string.overlay_unlock else R.string.overlay_lock,
                ),
            )
        }
        IconButton(onClick = onClose) {
            Icon(Icons.Outlined.Close, contentDescription = stringResource(R.string.common_close))
        }
    }
}
