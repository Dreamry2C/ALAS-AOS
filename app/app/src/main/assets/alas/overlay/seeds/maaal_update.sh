#!/bin/bash
# =============================================================================
# MaaAL · ALAS 热更新（rootfs 内由 App 侧 AlasUpdater 经 proot 拉起）
#
# 只拉 ALAS 源码，不动依赖（InstallDependencies:false 已锁死 pip）。
# 镜像默认 git.lyoko.io（fullcn 同款，大陆可达；deploy.yaml 里 ALAS 内置更新器
# 已被 AutoUpdate:false 锁死，本脚本是设备上唯一的 ALAS 更新通道）。
#
# 补丁重放不在本脚本职责内：git reset 会把上游跟踪文件打回原版，
# App 侧在收到 UPDATED 后重放 assets/alas（patches/module、patches/assets、
# overlays/rpc.py）并重跑 assets_fix.py。
#
# 与 App 的协议：最后一行打印三态之一，UPDATED/UNCHANGED 退出码 0，FAILED 退出码 1。
# FAILED（断网/超时/镜像不可达）由 App 降级为"跳过更新"，不阻塞启动。
#
# 环境变量（均可 export 覆盖，冒号后为默认值）：
#   MAAAL_ALAS_ROOT      /opt/alas
#   MAAAL_UPDATE_REPO    git://git.lyoko.io/AzurLaneAutoScript
#   MAAAL_UPDATE_BRANCH  master
#   MAAAL_UPDATE_DEPTH   50
#   MAAAL_UPDATE_TIMEOUT 240（秒；首次 fetch 需整棵浅树，弱网可调大）
# =============================================================================
set -uo pipefail

ALAS_DIR="${MAAAL_ALAS_ROOT:-/opt/alas}"
REPO="${MAAAL_UPDATE_REPO:-git://git.lyoko.io/AzurLaneAutoScript}"
BRANCH="${MAAAL_UPDATE_BRANCH:-master}"
DEPTH="${MAAAL_UPDATE_DEPTH:-50}"
TIMEOUT="${MAAAL_UPDATE_TIMEOUT:-240}"
STATE_FILE="$ALAS_DIR/.maaal_alas_commit"

fail() { echo "FAILED $1"; exit 1; }

cd "$ALAS_DIR" || fail "cd $ALAS_DIR"

# 当前 commit：优先 state 文件（上次更新写入），否则 BUILD_MANIFEST 的烘焙钉版
current=""
if [[ -f "$STATE_FILE" ]]; then
  current="$(cat "$STATE_FILE")"
elif [[ -f BUILD_MANIFEST ]]; then
  current="$(grep -o '"alas_commit": *"[0-9a-f]\{40\}"' BUILD_MANIFEST | grep -o '[0-9a-f]\{40\}' | head -1)"
fi

if [[ ! -d .git ]]; then
  git init -q . || fail "git init"
  git remote add origin "$REPO" || fail "git remote add"
fi

# 快进路径：ls-remote 直取远端 HEAD（无需本地仓库对象，秒级），
# 与当前一致就连 fetch 都免了——已是最新的常态下热更新必须零下载
remote_head="$(timeout 60 git ls-remote origin "$BRANCH" | head -1 | cut -f1)"
[[ -z "$remote_head" ]] && fail "ls-remote"
if [[ "$remote_head" == "$current" ]]; then
  echo "$remote_head" > "$STATE_FILE"
  echo "UNCHANGED $remote_head"
  exit 0
fi

# 首次更新本地没有对象：只取单提交树先把更新跑完（后续 fetch 会按需加深历史）
if [[ ! -f .git/FETCH_HEAD && ! -f .git/shallow ]]; then
  DEPTH=1
fi

# 上次被杀的 fetch 可能留锁（App 侧启动清理也会扫一遍，这里双保险）
find .git -name '*.lock' -delete 2>/dev/null

timeout "$TIMEOUT" git fetch --depth "$DEPTH" origin "$BRANCH" || fail "fetch"
new="$(git rev-parse FETCH_HEAD)" || fail "rev-parse FETCH_HEAD"

if [[ "$new" == "$current" ]]; then
  echo "$new" > "$STATE_FILE"
  echo "UNCHANGED $new"
  exit 0
fi

git reset --hard FETCH_HEAD || fail "reset --hard $new"
echo "$new" > "$STATE_FILE"
echo "UPDATED $new"
exit 0
