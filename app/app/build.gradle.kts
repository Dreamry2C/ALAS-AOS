plugins {
    id("maafw.android.application")
    id("maafw.android.compose")
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.androidx.baselineprofile)
}

android {
    namespace = "com.aliothmoon.maafw"

    defaultConfig {
        externalNativeBuild {
            cmake {
                arguments += "-DANDROID_STL=c++_shared"
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/native/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    buildFeatures {
        buildConfig = true
        aidl = true
    }

    androidResources {
        // rootfs.tar.xz 已压缩且要按字节读进度（assets.openFd 只对未压缩资产生效）
        noCompress += "zip"
        noCompress += "xz"
    }
}

baselineProfile {
    // 落进 src/main 而不是 src/release：测量用的 benchmark 是另一个 build type，
    // 吃不到 src/release 的源集，不合并的话量出来会是「profile 毫无效果」
    mergeIntoMain = true
}

dependencies {
    compileOnly(project(":hidden-api"))

    implementation(project(":annotation-api"))
    ksp(project(":ksp-processor"))
    implementation(project(":semi-icons"))

    // MIUI 上系统权限页的跳转差异大，自己拼 Intent 覆盖不全
    implementation(libs.xx.permissions)

    implementation(libs.shizuku.api)
    implementation(libs.shizuku.provider)
    implementation(libs.libsu)

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.process)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.core)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.datastore)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.window)
    // 解包与项目加载各圈一段，Perfetto / macrobenchmark 里才归得了因
    implementation(libs.androidx.tracing.ktx)
    // Baseline Profile 在 API 33 以下靠它在启动时装入
    implementation(libs.androidx.profileinstaller)

    implementation(libs.koin.android)
    implementation(libs.koin.androidx.compose)

    implementation(libs.timber)
    implementation(libs.kotlinx.serialization.json)

    implementation(libs.okhttp)
    // 首启解压 rootfs.tar.xz（设备端流式解 tar/xz；busybox tar 解 ubuntu 硬链接有前向引用死坑）
    implementation(libs.commons.compress)
    implementation(libs.tukaani.xz)
    // 前台模式控制层：拖拽/吸边/多屏/返回键拦截都在库里，自己写这几样是纯坑区
    implementation(libs.floatingx)
    implementation(libs.floatingx.compose)

    testImplementation(libs.junit)
    testImplementation(libs.mockk)
    testImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.ui.test.junit4)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)
    // Perfetto 里把 slice 命名到 composable；只进 debug，release 不带
    debugImplementation(libs.androidx.compose.runtime.tracing)
    debugImplementation(libs.androidx.tracing.perfetto.binary)
}
