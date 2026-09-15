package com.aliothmoon.maafw.ui.alas

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.os.Build
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aliothmoon.maafw.BuildConfig
import com.aliothmoon.maafw.R
import com.aliothmoon.maafw.service.HostState
import com.aliothmoon.maafw.theme.MaaDesignTokens
import org.koin.compose.koinInject

/** ALAS WebUI：App 内置环境监听的本机回环地址 */
private const val ALAS_WEBUI_URL = "http://127.0.0.1:22267"

/**
 * 本机（HONOR PPG-AN00, WebView 151）实测 `vh` 单位恒为 0：页面的 layout viewport
 * 错位成 0 高，所有 `100vh`（pywebio 脚手架 `#pywebio-scope-ROOT` 的高度）塌成 0，
 * 整页只画顶部一条标题带。`innerHeight` 正常，所以注入同值像素覆盖即可恢复。
 * 规则挂在 head 上对 JS 后续创建的 scope 元素同样生效；vh 正常的设备上本规则
 * 与 `100vh` 等值，无副作用。
 */
private const val SCOPE_HEIGHT_FIX_JS =
    """
    (() => {
      const h = Math.max(1, window.innerHeight);
      let s = document.getElementById('alas-scope-height-fix');
      if (!s) {
        s = document.createElement('style');
        s.id = 'alas-scope-height-fix';
        document.head.appendChild(s);
      }
      s.textContent = '#pywebio-scope-ROOT{height:' + h + 'px !important;min-height:' + h + 'px !important;}';
    })();
    """

/**
 * ALAS tab：全屏 WebView 容器，承载 App 内置环境里的 ALAS WebUI
 *
 * [active] 标记当前是否为 pager 可见页：ALAS 页不在前台时（pager 仍预组合着它）
 * 不该抢返回键。WebUI 历史能后退就 goBack，否则把返回键让回原有导航逻辑
 *
 * 本页可见且特权连接就绪时自动补一次「开始」链路建虚拟屏（HostState 内幂等，
 * 断线重连后随 privilegedConnected 翻转会再触发）
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun AlasScreen(
    active: Boolean,
    modifier: Modifier = Modifier,
    hostState: HostState = koinInject(),
) {
    var loadFailed by remember { mutableStateOf(false) }
    var canGoBack by remember { mutableStateOf(false) }
    var webView by remember { mutableStateOf<WebView?>(null) }
    val hostSnapshot by hostState.snapshot.collectAsStateWithLifecycle()

    LaunchedEffect(active, hostSnapshot.privilegedConnected) {
        if (active && hostSnapshot.privilegedConnected) {
            hostState.ensureEnvironmentStarted()
        }
    }

    BackHandler(enabled = active && canGoBack) {
        webView?.let {
            it.goBack()
            canGoBack = it.canGoBack()
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        AndroidView(
            factory = { ctx ->
                WebView(ctx).apply {
                    // debug 包开 WebView 调试口：本地排查页面渲染用
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT && BuildConfig.DEBUG) {
                        WebView.setWebContentsDebuggingEnabled(true)
                    }
                    // pywebio 是 SPA，JS 与 localStorage 都要开
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    webViewClient = object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(
                            view: WebView,
                            request: WebResourceRequest,
                        ): Boolean = when (request.url?.scheme) {
                            // http/https 一律留在 WebView 内打开，不放给外部浏览器
                            "http", "https" -> false
                            // 其余协议（intent:/tel:/mailto:...）不交给外部处理
                            else -> true
                        }

                        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                            loadFailed = false
                        }

                        override fun onPageFinished(view: WebView, url: String?) {
                            canGoBack = view.canGoBack()
                            // 见 SCOPE_HEIGHT_FIX_JS：本机 vh=0，补像素高度
                            view.evaluateJavascript(SCOPE_HEIGHT_FIX_JS, null)
                        }

                        override fun onReceivedError(
                            view: WebView,
                            request: WebResourceRequest,
                            error: WebResourceError,
                        ) {
                            // 只对主文档报错；子资源（图片/脚本）失败不算整页失败
                            if (request.isForMainFrame) {
                                canGoBack = view.canGoBack()
                                loadFailed = true
                            }
                        }
                    }
                    webView = this
                    loadUrl(ALAS_WEBUI_URL)
                }
            },
            onRelease = { it.destroy() },
            modifier = Modifier.fillMaxSize(),
        )

        if (loadFailed) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.background)
                    .pointerInput(Unit) {
                        // 挡住穿透到 WebView 自带的错误页上的漏点，只留重试按钮可点
                        awaitPointerEventScope {
                            while (true) {
                                awaitPointerEvent().changes.forEach { it.consume() }
                            }
                        }
                    }
                    .padding(MaaDesignTokens.Spacing.lg),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Text(
                    text = stringResource(R.string.alas_webui_not_running),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onBackground,
                )
                Spacer(Modifier.height(MaaDesignTokens.Spacing.lg))
                Button(
                    onClick = {
                        loadFailed = false
                        webView?.loadUrl(ALAS_WEBUI_URL)
                    },
                ) {
                    Text(stringResource(R.string.alas_webui_retry))
                }
            }
        }
    }
}
