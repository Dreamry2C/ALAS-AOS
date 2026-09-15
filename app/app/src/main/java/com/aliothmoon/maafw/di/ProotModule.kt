package com.aliothmoon.maafw.di

import com.aliothmoon.maafw.proot.ProotHost
import org.koin.android.ext.koin.androidApplication
import org.koin.core.qualifier.named
import org.koin.dsl.module

val prootModule = module {
    single { ProotHost(androidApplication(), get(named<AppCoroutineScope>())) }
}
