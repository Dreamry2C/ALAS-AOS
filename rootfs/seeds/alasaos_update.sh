#!/bin/bash
# =============================================================================
# ALAS 热更新：拉取 ALAS 源码到 $ALAS_DIR（默认 /opt/alas），不动依赖与运行文件。
# 更新语义与上游 ALAS 一致：git fetch 后 **git reset --hard** 直接打回远端，
# 不做任何保文件/自愈（用户换源后 /opt/alas 就是配置源的完整镜像，避免内置源
# 与用户源内容混杂冲突）。上游跟踪文件被打回原版后，由 App 侧重放 AlasOverlay。
#
# 与 App 的协议：最后一行 `UPDATED <sha> | UNCHANGED <sha> | FAILED <reason>`。
# UPDATED 表示真的 checkout 了新 commit，调用方负责重放 overlay + assets_fix。
# FAILED（断网/超时/镜像不可达）由 App 降级为"跳过更新"，不阻塞启动。
#
# 参数 / 环境变量（参数优先，冒号后为默认值）：
#   $1  更新源 git URL        ALASAOS_UPDATE_REPO    git://git.lyoko.io/AzurLaneAutoScript
#   $2  分支名                ALASAOS_UPDATE_BRANCH  master
#   —   ALASAOS_ALAS_ROOT     /opt/alas
#   —   ALASAOS_UPDATE_DEPTH  50
#   —   ALASAOS_UPDATE_TIMEOUT 240（秒；首次 fetch 需整棵浅树，弱网可调大）
#   —   ALASAOS_UPDATE_NO_CDN 置非空则跳过 CDN 通道（排障用）
#
# 设置项约定：源**留空 = 默认源**；分支默认 master（用户可在设置里自定义）。
# CDN pack 通道是 lyoko 官方源专用协议，仅在源为默认源时启用。
# =============================================================================
set -uo pipefail

ALAS_DIR="${ALASAOS_ALAS_ROOT:-/opt/alas}"
REPO="${1:-}"
if [[ -z "$REPO" ]]; then REPO="${ALASAOS_UPDATE_REPO:-git://git.lyoko.io/AzurLaneAutoScript}"; fi
BRANCH="${2:-}"
if [[ -z "$BRANCH" ]]; then BRANCH="${ALASAOS_UPDATE_BRANCH:-master}"; fi
DEPTH="${ALASAOS_UPDATE_DEPTH:-50}"
TIMEOUT="${ALASAOS_UPDATE_TIMEOUT:-240}"
STATE_FILE="$ALAS_DIR/.alasaos_alas_commit"
FAIL_FILE="$ALAS_DIR/.alasaos_update_fail_date"
DEFAULT_REPO="git://git.lyoko.io/AzurLaneAutoScript"

# 终态失败才记退避：通道内回落不算失败
fail() { date +%F > "$FAIL_FILE" 2>/dev/null; echo "FAILED $1"; exit 1; }

cd "$ALAS_DIR" || fail "cd $ALAS_DIR"

# 当前 commit：优先 state 文件（上次更新写入），否则 BUILD_MANIFEST 的烘焙钉版
current=""
if [[ -f "$STATE_FILE" ]]; then
  current="$(cat "$STATE_FILE")"
elif [[ -f BUILD_MANIFEST ]]; then
  current="$(grep -o '"alas_commit": *"[0-9a-f]\{40\}"' BUILD_MANIFEST | grep -o '[0-9a-f]\{40\}' | head -1)"
fi

# 失败退避：今天已败过一次就不再烧超时（次日自动恢复）
today="$(date +%F)"
if [[ -f "$FAIL_FILE" && "$(cat "$FAIL_FILE" 2>/dev/null)" == "$today" ]]; then
  echo "UNCHANGED backoff-until-tomorrow current=${current:-unknown}"
  exit 0
fi

if [[ ! -d .git ]]; then
  git init -q . || fail "git init"
fi
# origin 每次对齐配置源：用户换源后新源立即生效，绝不会 fetch 到旧源
git remote remove origin 2>/dev/null
git remote add origin "$REPO" || fail "git remote add"

# 上次被杀的 fetch/reset 可能留锁（App 侧启动清理也会扫一遍，这里双保险）
find .git -name '*.lock' -delete 2>/dev/null

# ---------- 通道 1：CDN pack（仅 lyoko 官方源；其协议就是该源的 git_over_cdn） ----------
if [[ -z "${ALASAOS_UPDATE_NO_CDN:-}" && "$REPO" == "$DEFAULT_REPO" ]]; then
  cdn_out="$(python3 seeds/cdn_update.py "$ALAS_DIR" "$current" 2>&1)"; cdn_rc=$?
  echo "$cdn_out" | sed 's/^/  /'
  cdn_last="$(echo "$cdn_out" | tail -1)"
  if [[ $cdn_rc -eq 0 && "$cdn_last" == "UPTODATE" ]]; then
    echo "$current" > "$STATE_FILE"
    echo "UNCHANGED $current (cdn)"
    exit 0
  elif [[ $cdn_rc -eq 0 && "$cdn_last" == PACK_READY\ * ]]; then
    new="${cdn_last#PACK_READY }"
    git reset --hard origin/"$BRANCH" || fail "reset --hard $new (cdn)"
    echo "$new" > "$STATE_FILE"
    rm -f "$FAIL_FILE"
    echo "UPDATED $new (cdn)"
    exit 0
  fi
  echo "  cdn| 通道不可用（$cdn_last），回落 git fetch"
fi

# ---------- 通道 2：git fetch（任意源通用） ----------
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

timeout "$TIMEOUT" git fetch --depth "$DEPTH" origin "$BRANCH" || fail "fetch"
new="$(git rev-parse FETCH_HEAD)" || fail "rev-parse FETCH_HEAD"

if [[ "$new" == "$current" ]]; then
  echo "$new" > "$STATE_FILE"
  echo "UNCHANGED $new"
  exit 0
fi

git reset --hard FETCH_HEAD || fail "reset --hard $new"
echo "$new" > "$STATE_FILE"
rm -f "$FAIL_FILE"
echo "UPDATED $new"
exit 0
