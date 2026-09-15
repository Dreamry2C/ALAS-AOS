package com.aliothmoon.maafw.runner

/**
 * PI 作者在 pipeline 节点上声明的消息模板
 * （MaaFramework `docs/zh_cn/3.3-ProjectInterfaceV2协议.md`「消息模板机制」）
 *
 * 与 [RunnerEvent] 其余成员的分工：那些是 MaaFramework 的原始转储，给排障看；
 * 这条是 PI 作者写给终端用户的话，外壳负责补完再按 [channels] 投递
 */
data class FocusMessage(
    /** 回调事件名，也是 focus 字典里的键 */
    val message: String,
    /** 空 = 只配了 trace 的条目，没有要展示的东西 */
    val content: String,
    val channels: Set<FocusChannel>,
    /** v2.9.1 `trace`：这条节点结果要不要上报遥测 */
    val trace: Boolean,
    /** 同一条回调 details 里的标量字段；非标量取不出可比的文本，不收 */
    val placeholders: Map<String, String> = emptyMap(),
) {
    val displayable: Boolean get() = content.isNotBlank()
}

/**
 * 协议的 `display` 有五档，Android 外壳只落地三档
 *
 * `dialog` / `modal` 一并归到 [Log]：modal 的语义是「弹出后任务暂停等待用户确认」，
 * 而回调是 oneway 单向通知，没有让外壳把 pipeline 卡住再放行的通道
 */
enum class FocusChannel { Log, Toast, Notification }
