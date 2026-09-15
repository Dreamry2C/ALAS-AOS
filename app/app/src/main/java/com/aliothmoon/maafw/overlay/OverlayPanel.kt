package com.aliothmoon.maafw.overlay

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import com.aliothmoon.maafw.R
import com.aliothmoon.maafw.constant.DefaultDisplayConfig
import com.aliothmoon.maafw.service.HostSnapshot
import com.aliothmoon.maafw.theme.MaaDesignTokens
import com.aliothmoon.maafw.theme.MaaTheme
import com.aliothmoon.maafw.ui.components.MaaButton

/**
 * 悬浮控制面板：环境状态的仪表盘 + 启停开关
 */
@Composable
fun OverlayPanel(
    snapshot: HostSnapshot,
    isLocked: Boolean,
    onStart: () -> Unit,
    onStop: () -> Unit,
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
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(MaaDesignTokens.Spacing.sm),
            ) {
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
