package com.aliothmoon.maafw.di

import com.aliothmoon.maafw.runner.RunnerPort
import com.aliothmoon.maafw.runner.StubRunnerPort
import org.koin.core.qualifier.named
import org.koin.dsl.module

val runnerModule = module {
    single<RunnerPort> {
        StubRunnerPort(scope = get(named<AppCoroutineScope>()))
    }
}
