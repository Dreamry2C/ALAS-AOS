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
#
# 退避与换源语义（2026-10-01 opus5 修）：
#   - 终态失败（fetch/reset 真失败）写当天退避，次日自动恢复，避免弱网每启动烧超时。
#   - 但「用户刚换源/换分支」是明确意图：检测到配置源/分支与上次尝试不同时，
#     **无视当天退避强制重试一次**（记指纹文件 .alasaos_update_source）。
#   - ls-remote 只是秒级探测，其失败不再写终态退避——改为回落走 fetch（fetch 自带
#     超时与真·终态判定）。否则换源第一次恰逢 gitee 瞬时抖动就被钉死一整天（实测坑）。
#   - 更新成功后把 config/deploy.yaml 的 Repository/Branch 同步成当前源，让 ALAS
#     自带「更新器」界面的本地/上游对比读到正确的源（用户私有 gitee 源不在 ALAS
#     config_redirect 改写名单，不会被改写；留空=默认源则写回 lyoko）。
# =============================================================================
set -uo pipefail
umask 077

ALAS_DIR="${ALASAOS_ALAS_ROOT:-/opt/alas}"
REPO="${1:-}"
if [[ -z "$REPO" ]]; then REPO="${ALASAOS_UPDATE_REPO:-git://git.lyoko.io/AzurLaneAutoScript}"; fi
BRANCH="${2:-}"
if [[ -z "$BRANCH" ]]; then BRANCH="${ALASAOS_UPDATE_BRANCH:-master}"; fi
DEPTH="${ALASAOS_UPDATE_DEPTH:-50}"
TIMEOUT="${ALASAOS_UPDATE_TIMEOUT:-240}"
STATE_FILE="$ALAS_DIR/.alasaos_alas_commit"
FAIL_FILE="$ALAS_DIR/.alasaos_update_fail_date"
SOURCE_FILE="$ALAS_DIR/.alasaos_update_source"
DEPLOY_YAML="$ALAS_DIR/config/deploy.yaml"
DEFAULT_REPO="git://git.lyoko.io/AzurLaneAutoScript"

# 终态失败才记退避：通道内回落不算失败；ls-remote 瞬时失败也不算（回落 fetch）
fail() { date +%F > "$FAIL_FILE" 2>/dev/null; echo "FAILED $1"; exit 1; }

# deploy.yaml 的 Repository/Branch 同步成当前源：仅改这两行，其余键/注释/行尾原样保留。
# ALAS 自带更新器界面读这两键跑 git log 做本地/上游对比；不同步则界面读旧源→全空。
# 用 Python（seeds/sync_deploy.py）而非 sed：跨平台一致、正确保留 CRLF 行尾
# （git-bash 的 sed 会把整文件 CRLF 压成 LF，真机 Linux sed 行为又不同，不可靠）。
sync_deploy_yaml() {
  [[ -f "$DEPLOY_YAML" ]] || return 0
  python3 seeds/sync_deploy.py "$REPO" "$BRANCH" 2>&1 | sed 's/^/  /' || true
}

cd "$ALAS_DIR" || fail "cd $ALAS_DIR"

# GPT-6 Astra 2026-10-01: only a real HEAD proves that checkout happened.
# A manifest/state SHA can exist in a rootfs with no Git objects or refs.
current="$(git rev-parse --verify HEAD 2>/dev/null || true)"
current_branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
git check-ref-format "refs/heads/$BRANCH" >/dev/null 2>&1 || fail "invalid branch"

# 源指纹：检测「换源/换分支」——用户换源是明确意图，要能突破当天退避
want_source="$(printf '%s\n%s' "$REPO" "$BRANCH" | sha256sum | cut -d' ' -f1)"
last_source=""
[[ -f "$SOURCE_FILE" ]] && last_source="$(cat "$SOURCE_FILE" 2>/dev/null)"
source_changed=0
if [[ "$want_source" != "$last_source" ]]; then
  source_changed=1
fi

# 失败退避：今天已败过一次就不再烧超时（次日自动恢复）——但换源时强制突破
today="$(date +%F)"
if [[ "$source_changed" -eq 0 && -f "$FAIL_FILE" && "$(cat "$FAIL_FILE" 2>/dev/null)" == "$today" ]]; then
  echo "UNCHANGED backoff-until-tomorrow current=${current:-unknown}"
  exit 0
fi
if [[ "$source_changed" -eq 1 ]]; then
  echo "  source configuration changed: retry once, clear backoff"
  rm -f "$FAIL_FILE"
fi
# Save the attempted configuration before network I/O, including failed attempts.
# Never persist/log the credential-bearing URL in the retry marker.
printf '%s\n' "$want_source" > "$SOURCE_FILE" || fail "write source marker"

if [[ ! -d .git ]]; then
  git init -q . || fail "git init"
fi
# origin 每次对齐配置源：用户换源后新源立即生效，绝不会 fetch 到旧源
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO" 2>/dev/null || fail "git remote set-url"
else
  git remote add origin "$REPO" 2>/dev/null || fail "git remote add"
fi

# 上次被杀的 fetch/reset 可能留锁（App 侧启动清理也会扫一遍，这里双保险）
find .git -name '*.lock' -delete 2>/dev/null

# ---------- 通道 1：CDN pack（仅 lyoko 官方源；其协议就是该源的 git_over_cdn） ----------
if [[ -z "${ALASAOS_UPDATE_NO_CDN:-}" && "$REPO" == "$DEFAULT_REPO" && "$BRANCH" == master && -n "$current" && "$source_changed" -eq 0 && "$current_branch" == "$BRANCH" ]]; then
  cdn_out="$(python3 seeds/cdn_update.py "$ALAS_DIR" "$current" 2>&1)"; cdn_rc=$?
  echo "$cdn_out" | sed 's/^/  /'
  cdn_last="$(echo "$cdn_out" | tail -1)"
  if [[ $cdn_rc -eq 0 && "$cdn_last" == "UPTODATE" ]]; then
    git update-ref "refs/remotes/origin/$BRANCH" "$current" || fail "update remote ref"
    echo "$current" > "$STATE_FILE"
    echo "$want_source" > "$SOURCE_FILE"
    rm -f "$FAIL_FILE"
    sync_deploy_yaml
    echo "UNCHANGED $current (cdn)"
    exit 0
  elif [[ $cdn_rc -eq 0 && "$cdn_last" == PACK_READY\ * ]]; then
    new="${cdn_last#PACK_READY }"
    git reset --hard origin/"$BRANCH" >/dev/null 2>&1 || fail "reset --hard $new (cdn)"
    echo "$new" > "$STATE_FILE"
    echo "$want_source" > "$SOURCE_FILE"
    rm -f "$FAIL_FILE"
    sync_deploy_yaml
    echo "UPDATED $new (cdn)"
    exit 0
  fi
  echo "  cdn| 通道不可用（$cdn_last），回落 git fetch"
fi

# ---------- 通道 2：git fetch（任意源通用） ----------
# 快进路径：ls-remote 直取远端 HEAD（无需本地仓库对象，秒级），
# 与当前一致就连 fetch 都免了——已是最新的常态下热更新必须零下载。
# ls-remote 瞬时失败不作终态退避（换源第一次恰逢 gitee 抖动会被钉死一整天）——
# remote_head 取空就跳过快进、直接走 fetch（fetch 有 TIMEOUT 与真·终态判定）。
remote_head="$(timeout 60 git ls-remote --heads origin "refs/heads/$BRANCH" 2>/dev/null | head -1 | cut -f1)"
if [[ -n "$remote_head" && "$remote_head" == "$current" && "$source_changed" -eq 0 && "$current_branch" == "$BRANCH" ]]; then
  git update-ref "refs/remotes/origin/$BRANCH" "$remote_head" || fail "update remote ref"
  echo "$remote_head" > "$STATE_FILE"
  echo "$want_source" > "$SOURCE_FILE"
  rm -f "$FAIL_FILE"
  sync_deploy_yaml
  echo "UNCHANGED $remote_head"
  exit 0
fi
[[ -z "$remote_head" ]] && echo "  ls-remote 无结果（瞬时抖动？），回落 git fetch 重试"

# 首次更新本地没有对象：只取单提交树先把更新跑完（后续 fetch 会按需加深历史）
if [[ ! -f .git/FETCH_HEAD && ! -f .git/shallow ]]; then
  DEPTH=1
fi

# Git may echo the credential-bearing URL even on failure; report only the phase.
timeout "$TIMEOUT" git fetch --depth "$DEPTH" origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" >/dev/null 2>&1 || fail "fetch"
new="$(git rev-parse FETCH_HEAD)" || fail "rev-parse FETCH_HEAD"

if [[ "$new" == "$current" && "$source_changed" -eq 0 && "$current_branch" == "$BRANCH" ]]; then
  echo "$new" > "$STATE_FILE"
  echo "$want_source" > "$SOURCE_FILE"
  rm -f "$FAIL_FILE"
  sync_deploy_yaml
  echo "UNCHANGED $new"
  exit 0
fi

# Forced checkout also aligns the local branch name, even when both refs have
# the same SHA. UPDATED tells ProotHost to reapply the AOS overlay afterwards.
git checkout -f -B "$BRANCH" "$new" -- >/dev/null 2>&1 || fail "checkout branch"
git reset --hard "$new" >/dev/null 2>&1 || fail "reset --hard $new"
echo "$new" > "$STATE_FILE"
echo "$want_source" > "$SOURCE_FILE"
rm -f "$FAIL_FILE"
sync_deploy_yaml
echo "UPDATED $new"
exit 0
