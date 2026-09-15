package com.aliothmoon.maafw.ui.setup

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import com.aliothmoon.maafw.R
import com.aliothmoon.maafw.provision.ProvisionState
import com.aliothmoon.maafw.theme.MaaDesignTokens
import com.aliothmoon.maafw.theme.MaaTheme
import com.aliothmoon.maafw.ui.components.MaaButton

/**
 * 首启 rootfs 部署页：未完成时整屏接管（AppRoot 的门）
 *
 * 全程唯一动作是「等」；失败/低磁盘/未内置给原因与重试，跳过只留给开发包
 */
@Composable
fun ProvisionScreen(
    state: ProvisionState,
    onRetry: () -> Unit,
    onSkip: (() -> Unit)?,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(MaaTheme.style.cardInnerPadding),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                text = stringResource(R.string.provision_title),
                style = MaterialTheme.typography.headlineMedium,
            )
            Spacer(Modifier.height(MaaDesignTokens.Spacing.md))
            Text(
                text = stringResource(R.string.provision_subtitle),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(MaaDesignTokens.Spacing.xl))

            when (state) {
                ProvisionState.Checking -> {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    StatusLine(stringResource(R.string.provision_checking))
                }

                is ProvisionState.Extracting -> {
                    val progress =
                        if (state.totalBytes > 0) state.doneBytes.toFloat() / state.totalBytes else 0f
                    LinearProgressIndicator(
                        progress = { progress },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    StatusLine(
                        stringResource(
                            R.string.provision_extracting,
                            (progress * 100).toInt(),
                            state.doneBytes / 1_000_000,
                            state.totalBytes / 1_000_000,
                        )
                    )
                }

                is ProvisionState.LowDisk -> {
                    StatusLine(
                        stringResource(
                            R.string.provision_low_disk,
                            state.freeBytes / 1_000_000,
                        ),
                        isError = true,
                    )
                    RetryButton(onRetry)
                }

                ProvisionState.NotBundled -> {
                    StatusLine(
                        stringResource(R.string.provision_not_bundled),
                        isError = true,
                    )
                    RetryButton(onRetry)
                    if (onSkip != null) {
                        Spacer(Modifier.height(MaaDesignTokens.Spacing.sm))
                        MaaButton(onClick = onSkip) {
                            Text(stringResource(R.string.provision_skip))
                        }
                    }
                }

                is ProvisionState.Failed -> {
                    StatusLine(
                        stringResource(R.string.provision_failed, state.reason),
                        isError = true,
                    )
                    RetryButton(onRetry)
                }

                ProvisionState.Ready -> Unit // 门已开，本页不再渲染
            }
        }
    }
}

@Composable
private fun StatusLine(text: String, isError: Boolean = false) {
    Spacer(Modifier.height(MaaDesignTokens.Spacing.md))
    Text(
        text = text,
        style = MaterialTheme.typography.bodyMedium,
        color = if (isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
        textAlign = TextAlign.Center,
    )
}

@Composable
private fun RetryButton(onRetry: () -> Unit) {
    Spacer(Modifier.height(MaaDesignTokens.Spacing.lg))
    MaaButton(onClick = onRetry) {
        Text(stringResource(R.string.provision_retry))
    }
}
