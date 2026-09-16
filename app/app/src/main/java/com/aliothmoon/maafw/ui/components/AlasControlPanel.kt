package com.aliothmoon.maafw.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp
import com.aliothmoon.maafw.R
import com.aliothmoon.maafw.constant.DefaultDisplayConfig
import com.aliothmoon.maafw.proot.AlasRunState
import com.aliothmoon.maafw.service.HostSnapshot
import com.aliothmoon.maafw.theme.MaaDesignTokens

/**
 * ALAS 控制面板（共享组合件）：环境/调度器状态行 + 日志板 + 调度器启停
 *
 * 悬浮窗（OverlayPanel）与挂机页（HangarScreen）共用同一份。
 * 调度器控制面只此一处（wrapper 薄 HTTP）；WebUI 里的启停按钮已被锁定补丁封死，
 * 双头同用会抢设备——别用（见 AlasRunController 头注）
 */
@Composable
fun AlasControlPanel(
    snapshot: HostSnapshot,
    alas: AlasRunState,
    onAlasStart: () -> Unit,
    onAlasStop: () -> Unit,
    onToolStart: (String) -> Unit,
    onToolStop: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.md),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm)) {
            AlasStatusRow(
                labelRes = R.string.overlay_host_privileged,
                value = stringResource(
                    if (snapshot.privilegedConnected) {
                        R.string.host_state_connected
                    } else {
                        R.string.host_state_disconnected
                    }
                ),
            )
            AlasStatusRow(
                labelRes = R.string.overlay_host_bridge,
                value = stringResource(
                    if (snapshot.bridgeReachable) {
                        R.string.host_state_ok
                    } else {
                        R.string.host_state_unreachable
                    }
                ),
            )
            AlasStatusRow(
                labelRes = R.string.overlay_host_display,
                value = if (snapshot.vdDisplayId != DefaultDisplayConfig.DISPLAY_NONE) {
                    "#${snapshot.vdDisplayId}"
                } else {
                    stringResource(R.string.host_state_display_none)
                },
            )
            AlasStatusRow(
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
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
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
        AlasToolSection(
            alas = alas,
            onToolStart = onToolStart,
            onToolStop = onToolStop,
        )
        Text(
            text = stringResource(R.string.overlay_alas_hint),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
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
private fun AlasStatusRow(labelRes: Int, value: String) {
    Text(
        text = stringResource(labelRes, value),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/**
 * 工具区：半自动点击 / 活动剧情
 *
 * 与调度器的互斥（启工具自动停 runner、启 runner 自动停工具）由 wrapper 集中执行，
 * 可用性只沿用面板既有的 wrapper 可达/忙碌判断，不拿 runnerAlive/toolAlive 互相禁用
 */
@Composable
private fun AlasToolSection(
    alas: AlasRunState,
    onToolStart: (String) -> Unit,
    onToolStop: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.xs)) {
        Text(
            text = stringResource(R.string.hangar_tool_label),
            style = MaterialTheme.typography.titleSmall,
            color = MaterialTheme.colorScheme.onSurface,
        )
        if (alas.toolAlive) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm),
            ) {
                Text(
                    text = stringResource(R.string.hangar_tool_running, toolDisplayName(alas.toolName)),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f),
                )
                MaaButton(
                    onClick = onToolStop,
                    enabled = alas.reachable && !alas.busy,
                ) {
                    Text(stringResource(R.string.hangar_tool_stop))
                }
            }
        } else {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm),
            ) {
                MaaOutlinedButton(
                    onClick = { onToolStart(AlasRunState.TOOL_SEMI_AUTO) },
                    enabled = alas.reachable && !alas.busy,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.hangar_tool_semi_auto))
                }
                MaaOutlinedButton(
                    onClick = { onToolStart(AlasRunState.TOOL_EVENT_STORY) },
                    enabled = alas.reachable && !alas.busy,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.hangar_tool_event_story))
                }
            }
        }
    }
}

/** /status 回报的工具名 → 展示名；未知名原样显示，null 兜底为「工具」 */
@Composable
private fun toolDisplayName(name: String?): String = when (name) {
    AlasRunState.TOOL_SEMI_AUTO -> stringResource(R.string.hangar_tool_semi_auto)
    AlasRunState.TOOL_EVENT_STORY -> stringResource(R.string.hangar_tool_event_story)
    null -> stringResource(R.string.hangar_tool_label)
    else -> name
}
