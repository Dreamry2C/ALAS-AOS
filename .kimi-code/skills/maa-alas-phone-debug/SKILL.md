---
name: maa-alas-phone-debug
description: MaaAL 手机端（HONOR PPG-AN00 / 无 root / Shizuku 后台虚拟屏）调试闭环：pipeline/interface 热推、run-as 直改运行配置、单任务跑测、日志与 on_error 真帧定位。当需要在真机上验证 pipeline 改动、跑单个任务、读取运行日志或定位识别失败时使用。
---

# MaaAL 手机端调试闭环

设备与路径常量：

- 设备序列号：`AVAY025422002864`（USB；无线断连时 mDNS 端口会过期，别信广播，重插 USB）
- App 包名：`com.aliothmoon.maafw.maaal`（debug 包，debuggable=true）
- 外置目录 `$E=/sdcard/Android/data/com.aliothmoon.maafw.maaal/files`（普通 adb shell 可读写，无需 run-as）
- 解包资源：`$E/pi/`（interface.json + resource/base/{pipeline,image}/…）
- 运行日志：`$E/log/run/run_*.jsonl`（`ls -t | head -1` 取最新；grep -vE 'Controller.Action' 后读）
- native 日志：`$E/log/maafw.log`（**不按启动轮转，一份文件跨多次运行**——grep 取证必须按行首时间戳过滤当次运行，否则会吃到上一轮同名节点记录得出假结论；bak 轮转另有触发条件）
- 超时真帧：`$E/log/on_error/<时间>_<节点>.png`（1280×720 虚拟屏内容，定位失败的第一现场）
- 运行配置：`/data/data/com.aliothmoon.maafw.maaal/files/datastore/user_configuration.json`（仅 run-as 可达；该私有目录里**没有** log/ 和 pi/，别去那找）

**所有 adb 命令前 `export MSYS_NO_PATHCONV=1`**，否则 Git Bash 把 `/sdcard/...` 转成 Windows 路径。

## 标准迭代循环（改代码 → 上机验证）

1. 本地改 pipeline/interface → `python dev_tools/validate_resource.py` + `pnpm format && pnpm check` 全绿。
2. 热推（pi.version 不变就不会重解决包，已验证）：

```bash
export MSYS_NO_PATHCONV=1
D=/sdcard/Android/data/com.aliothmoon.maafw.maaal/files/pi
adb -s AVAY025422002864 push resource/base/pipeline/<file>.json "$D/resource/base/pipeline/<file>.json"
adb -s AVAY025422002864 push interface.json "$D/interface.json"   # 改了 interface 才推
# 新模板图片同理 push 到 $D/resource/base/image/<模块>/
```

3. 改写运行配置（见下节），推回，然后重启 App 并开始：

```bash
adb -s AVAY025422002864 shell "run-as com.aliothmoon.maafw.maaal sh -c 'cat > /data/data/com.aliothmoon.maafw.maaal/files/datastore/user_configuration.json'" < .tmp/uc.json
adb -s AVAY025422002864 shell "am force-stop com.aliothmoon.maafw.maaal; sleep 1; monkey -p com.aliothmoon.maafw.maaal -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; sleep 9; input tap 474 2698; sleep 3; input tap 583 2564"
# tap 474,2698 = 底部「任务」tab；583,2564 = 「开始任务」按钮中心（竖屏 1264×2800）
# sleep 6 偶尔不够（App 没加载完 tap 落空、界面停在已停止），用 9+3 稳；tap 后 ps 查 com.bilibili.azurlane 进程确认真拉起了
```

4. 等待后读最新 run jsonl：`任务完成` = 绿；`任务失败` + on_error 新真帧 = 红。
5. 失败定位：pull on_error 真帧 `ReadMediaFile` 看虚拟屏实际内容；再 `grep -a '<节点名>' maafw.log | tail` 看命中链。
6. **节点死循环且 timeout 不触发**（JumpBack 命中会重置 timeout）时，用探针逼帧：热推一份把嫌疑节点 `enabled=false`（或摘掉乒乓对另一半）的同名 pipeline，让扫描无命中 → 45s timeout 落 on_error 真帧 → 看屏幕真相；查完把正式版推回去。
7. **点开即关的导航乒乓**：`Node.Action.Starting` 同一节点 100-200ms 刷屏 = 典型症状（rate_limit 不顶用）。修法=给会打开可点外关闭菜单/页面的导航节点加 `post_delay`（1500ms 实测有效）。

## 运行配置直改（免 UI、免输入法）

读出 → 本地 python 改 → 推回。结构：`config.configurations[0].tasks[]`，每项 `taskName` / `enabled` / `optionValues`。

- **单任务调试必须 Startup 队首**：force-stop App 会拆虚拟屏、游戏进程随之被杀；没有 Startup 拉起，被测任务只会在黑屏上空转 45s 超时。配置形态：`Startup` + 被测任务 `enabled=true`，其余全 false。
- optionValues 形态（已实测）：
    - input 选项：`{"game_package": {"type": "inputs", "values": {"package": "com.bilibili.azurlane"}}}`
    - switch/select 选项：`{"reward_collect_mission": {"type": "single", "case": "No"}}`（写错形态 App 会忽略并回落 default_case，读回校验可发现）
- 推回后必须 force-stop + 重进 App 才会重读。

## 验证选项生效的方法

- **override 三板斧（maafw.log，先按时间戳过滤当次运行！）**：
    1. `grep -a 'MaaTaskerPostTask' maafw.log` → 带 `entry=<任务>` 和 `pipeline_override=[...]` 完整 JSON 原文（App 实际发给 runtime 的 override，最强证据）；
    2. `grep -a 'found in override'` → 节点级 override 被 Context 命中的记录；
    3. `grep -a 'Node.NextList.Starting'` → next 数组实际执行顺序（验 select 预设覆写 next）。
       注意排除 `PipelineParser parse_node` 解析行（每个节点都有，与执行无关）。
- **差分验证**：把选项改成必然产生可观察差异的值（如包名改 `com.android.settings` → StartApp 拉起设置 → 任务超时且 on_error 真帧是设置界面），再改回默认跑绿。
- **时序/日志验证**：开关类选项关掉某阶段后，对比任务耗时（Reward 关任务领取：27.5s → 6.4s）或 grep maafw.log 确认对应节点未执行。
- 配置读回（`run-as cat user_configuration.json`）只证明 JSON 落盘，不证明 App 采纳——要和上面三板斧搭配用。

## 手机侧注意事项

- 锁屏/熄屏不影响后台模式跑任务；但安全锁屏下 `exec-out screencap` 失败（50 字节报错文本），`input keyevent 224` 只能亮屏，解锁要靠用户。
- **调试期间让用户别碰手机**：物理屏的旋转/误触会干扰坐标映射与配置（预设被误应用会重置任务勾选）。
- App UI 输入框会被中文 IME 拦截 `input text`（拼音组合成汉字）；`ime set` 对已打开会话无效。需要填 ASCII 就直改配置 JSON。
- 停止运行：任务页「停止」按钮在竖屏约 (447,2554)；点不动就 force-stop App（核选项，副作用是游戏被杀，下轮靠 Startup 拉起）。
- 游戏前台在物理屏打开过会抢走虚拟屏上的渲染；调试期间不要在物理屏开游戏。
- **`input -d <vid>` 对 MaaFwVirtualDisplay 无效**（返回成功但静默忽略，已实测 tap/keyevent 均无果）；`screencap -d` 也拒绝。外部无法操纵/截取虚拟屏——看内容只能靠 on_error 真帧和识别日志，别浪费时间试 input -d。
