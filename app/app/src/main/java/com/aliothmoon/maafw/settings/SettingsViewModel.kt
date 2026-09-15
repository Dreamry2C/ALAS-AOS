package com.aliothmoon.maafw.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aliothmoon.maafw.config.UserConfigurationStore
import com.aliothmoon.maafw.i18n.AppLocales
import com.aliothmoon.maafw.privileged.PermissionGateway
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * 设置页的 Activity 作用域会话
 *
 * 后端选择是 app 设置而非运行配置；主题/语言/调试都是只改观感与日志详略的外壳设置
 */
class SettingsViewModel(
    private val permissionGateway: PermissionGateway,
    private val appSettings: AppSettingsGateway,
    private val userConfigurationStore: UserConfigurationStore,
) : ViewModel() {

    val uiState: StateFlow<SettingsUiState> = combine(
        permissionGateway.state,
        userConfigurationStore.data,
        appSettings.themeStyle,
        appSettings.resolutionPreference,
        appSettings.debugMode,
    ) { remoteAccess, userConfig, themeStyle, resolution, debugMode ->
        SettingsUiState(
            remoteAccess = remoteAccess,
            themeMode = userConfig.themeMode,
            themeStyle = themeStyle,
            resolutionPreference = resolution,
            debugMode = debugMode,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = SettingsUiState(),
    )

    fun onIntent(intent: SettingsIntent) {
        when (intent) {
            is SettingsIntent.SetBackend -> viewModelScope.launch {
                permissionGateway.setBackend(intent.backend)
            }

            is SettingsIntent.SetThemeMode -> viewModelScope.launch {
                userConfigurationStore.update { it.copy(themeMode = intent.mode) }
            }

            is SettingsIntent.SetThemeStyle -> viewModelScope.launch {
                appSettings.setThemeStyle(intent.style)
            }

            is SettingsIntent.SetLanguage -> AppLocales.apply(intent.tag)

            is SettingsIntent.SetResolutionPreference -> viewModelScope.launch {
                appSettings.setResolutionPreference(intent.preference)
            }

            is SettingsIntent.SetDebugMode -> viewModelScope.launch {
                appSettings.setDebugMode(intent.enabled)
                // 落盘之后再通知重启：杀进程抢在写盘前，开关就白拨了
                if (intent.enabled) _events.emit(SettingsEvent.RestartApp)
            }
        }
    }

    private val _events = MutableSharedFlow<SettingsEvent>()
    val events: SharedFlow<SettingsEvent> = _events.asSharedFlow()
}
