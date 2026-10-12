# 上游同步适配审查 · 2026-10-12（PIN 92c07aa → HEAD 7d6a415e）

## 背景

用户指令：「ALAS 发布了新的 fullcn 版本，查看内部改动，做好本项目的适配工作」。方法 = 双侦察代理交叉：A（本地适配面/漂移监视表）+ B（上游全量 diff），grilling 两轮 7 问收口决策。

## 版本锚点

| 项 | 值 |
|---|---|
| 旧钉版 PIN | `92c07aa28ba8515b7709542ae8c14f6a7f3a08bd`（2026-09-15） |
| 新钉版 HEAD | `7d6a415e3ef5ed049fd7024311c16158fcd2af28`（2026-10-08，GitHub 与 git.lyoko.io 镜像一致） |
| 区间 | 39 commit / 129 文件（M46 A7 D76）/ +781 −375 |

上游为滚动发布，无 tag/release/日期化 fullcn 标记；最新 GitHub tag 停在 2023 年。

## 改动性质判定：低风险滚动更新

- **无 python 依赖变化**（全部 requirements blob sha 与 PIN 相同）、**无配置键增删**（仅新增 1 个枚举值 `PrivateQuarters.TargetShip.implacable`）、**无 WebUI 前端变化**、**无 OCR 模型变化**、**无截图/控制方案变动**（nemu_ipc 通道修正不在我们的路径上）。
- **与 AOS 补丁/overlay 面零碰撞**：我们整替的 18 个上游文件（module/base、module/device 五件、module/webui 两件等 + 8 张 assets PNG）上游一个没动。
- **assets_fix.py 安全**：5 个目标 Button 定义行均未动（module/ui/assets.py 仅 +1 行 TACTICAL_CHECK_2，按名正则不受影响）。
- **regen_args.py 安全**：args.json 改动全为事件下拉选项追加，无键增删；生成链 config_updater 未变。

## 签名变更审计（唯一 breaking 候选，结论：无破坏）

| 变更 | AOS 侧核查 | 结论 |
|---|---|---|
| `dock_select_one(button)` / `dock_selected()` 去掉 `skip_first_screenshot` | 全仓 grep：AOS patch/overlay 零调用点 | 安全 |
| `equipment_code.py` 的 `dump_hierarchy_adb()` → `dump_hierarchy()` | `dump_hierarchy_adb` 定义于 `module/device/method/adb.py:392`，上游本轮未动该文件；且改后调用走进我们 app_control.py patch 的 `dump_hierarchy()` alasaos 桥接分支 | 安全且受益（Android 15 xpath 分支经桥接而非裸 adb） |

## 主要内容性更新（热更新直接覆盖，无需适配）

新增 `module/map/fleet_bar.py`（FleetBarDetector 轮廓检测重构舰队下拉）、7 个复刻活动入口、GET_SHIP 资产全局重录 + offset、private_quarters 少语种资产合并（76 张 PNG 删除无悬空引用）、PR9 活动商店、TACTICAL_CHECK_2 双资产等。

## 决策记录（grilling 两轮）

| # | 决策点 | 结论 |
|---|---|---|
| Q1 | 适配深度 | 兼容适配 + 重烘 rootfs + 发新版 APK（v0.1.7） |
| Q2 | 钉版策略 | `ALAS_REF` 钉 `7d6a415e`；热更新双通道（CN：CDN→git.lyoko；GitHub 档走系统代理）照常拉新——钉版只定烘焙起点 |
| Q3 | 真机验证 | 启动链 + 热更新 + 三件套冒烟（挂机/半自动点击/活动剧情） |
| Q4 | push/发版 | 改完先汇报，逐次授权 |
| Q5 | CDN 回退源 | `cdn_update.py` 补上游新增的第 3 条 myqcloud URL（保持与 deploy/git.py 的 1:1 复刻口径） |
| Q6 | 顺手修 | ① manifest `patches_source` 旧路径更正 ② 烘焙 tar 补装 `cdn_update.py`+`assets_fix.py`（原仅 APK overlay 交付，纯 rootfs 环境缺） ③ `app.yml` 触发路径补 `rootfs/**`（双源门禁原不拦纯 rootfs 改动） |
| Q7 | rootfs_version | 不抬号（保持 0.1.0）：本轮无依赖/系统层变化，热更新通道足以收敛设备；抬号=全员重解 /opt/alas 清用户配置，纯代价。规则写入 development.md |

## 落地改动清单

- `rootfs/build/build-rootfs.sh`：ALAS_REF 默认钉 `7d6a415e`；`require_file` + 安装清单补 `seeds/cdn_update.py` 与 `patches/assets_fix.py`（后者装入 `/opt/alas/seeds/`）；`patches_source` 字段更正为 `rootfs/patches`
- `rootfs/seeds/cdn_update.py` + `app/app/src/main/assets/alas/overlay/seeds/cdn_update.py`（双源同步）：BASE_URLS 第 3 条 myqcloud
- `.github/workflows/app.yml`：push/PR 触发路径补 `rootfs/**`
- `development.md`：rootfs_version 抬号规则 + 现状行刷新
- 本文档归档

## 后续验证（DoD）

- [ ] CI：push 后 rootfs.yml 重烘（新钉版）+ app.yml 双源门禁绿
- [ ] 新 BUILD_MANIFEST 回流入库（alas_commit=7d6a415e）
- [ ] 真机：升级安装（不清数据）→ 热更新至 7d6a415e → assets_fix 无漂移告警 → 三件套冒烟（挂机/半自动点击/活动剧情）
- [ ] 发版 v0.1.7（用户授权后）

侦察原始数据：`.tmp/upstream-check/`（full.diff / stat.txt / commits.txt / sections/，用毕可清）。
