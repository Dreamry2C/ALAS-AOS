#!/bin/bash
# =============================================================================
# AlasAos · ALAS 工作区离线还原（rootfs 内由 App 侧 ProotHost 经 proot 拉起，按需执行）
#
# 背景：rootfs 镜像只带浅克隆 .git（瘦身）——git 跟踪的工作区文件在打包前已按
# ls-files 精确剥离，pack（~70MB）里仍含全部内容；untracked 的 AOS 自有资产
# （seeds/、config/deploy.yaml、BUILD_MANIFEST、wrapper*.py 等）不受影响。
# 首次启动（或上次还原中断）时由本脚本 `git reset --hard` 从 pack 离线物化整树，
# 无需网络——官方 Windows 一键包（deploy/git.py git_repository_init）同款方案。
#
# 幂等：成功后落 marker（.alasaos_restored，untracked，reset --hard 不会清掉），
# App 侧见 marker 直接跳过本步；旧版完整工作区的 rootfs 升级上来时同样补 marker。
# 失败：非零退出，ProotHost 按 fatal 处理——树不全 ALAS 必然起不来，早失败早暴露。
# 输出进 runGuest 回收（session.log 可查）。
# =============================================================================
set -u

ALAS_DIR="${ALASAOS_ALAS_ROOT:-/opt/alas}"
MARK=".alasaos_restored"
SENTINEL="alas.py"   # 仓库根主入口，上游 tracked；物化完成的判据

cd "$ALAS_DIR" || { echo "restore: WARN cd $ALAS_DIR failed"; exit 0; }

if [ -f "$MARK" ]; then
  echo "restore: already materialized, skip"
  exit 0
fi

if [ ! -d .git/objects/pack ]; then
  if [ -f "$SENTINEL" ]; then
    # 旧版镜像（无 .git 的完整工作区）：无需还原，补 marker 让 App 侧后续跳过
    touch "$MARK"
    echo "restore: legacy full tree (no .git), marked"
    exit 0
  fi
  echo "restore: FATAL no .git pack and no ALAS tree"
  exit 1
fi

echo "restore: materializing ALAS tree from pack (one-time)..."
git -c safe.directory='*' reset --hard HEAD || { echo "restore: FATAL git reset failed"; exit 1; }
if [ ! -f "$SENTINEL" ]; then
  echo "restore: FATAL sentinel missing after reset"
  exit 1
fi
touch "$MARK"
echo "restore: OK ($(git -c safe.directory='*' ls-files 2>/dev/null | wc -l) tracked files)"
exit 0
