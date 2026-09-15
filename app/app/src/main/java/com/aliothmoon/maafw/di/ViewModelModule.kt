package com.aliothmoon.maafw.di

import com.aliothmoon.maafw.log.AppLogDetailViewModel
import com.aliothmoon.maafw.log.AppLogViewModel
import com.aliothmoon.maafw.settings.SettingsViewModel
import org.koin.core.module.dsl.viewModel
import org.koin.core.module.dsl.viewModelOf
import org.koin.dsl.module

val viewModelModule = module {
    viewModelOf(::AppLogViewModel)
    viewModelOf(::AppLogDetailViewModel)

    viewModel {
        SettingsViewModel(get(), get(), get())
    }
}
