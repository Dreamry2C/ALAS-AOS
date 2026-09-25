# 瘦身记录（可回滚）· 2026-09-26 · 原版 OCR rootfs

> 目的：记录每一步瘦身的 **commit / 改动 / 体积变化 / 校验结果 / 回滚方法**，出问题按此回滚。
> 回滚通用法：`git revert <hash>`（保留历史）或 `git reset --hard <上一步 hash>`（丢弃）。
> 校验口径：GHA `rootfs` workflow 成功 = build-rootfs 的 import 硬门禁通过（`import mxnet`/`cnocr` + numpy 垫片）；
> 产物 `rootfs.tar.xz` 体积见每步；真机 OCR 验证另记。

## 基线
- **原版 OCR 首个可复现构建**：commit `1aaaf84`，rootfs.tar.xz **482,921,448 B（~461MB）**，APK ~536MB。GHA run 36179642563 SUCCESS。

## 步骤

| # | commit | 改动 | rootfs.tar.xz | 结果 | 回滚 |
|---|---|---|---|---|---|
| 1 | `1c26093` | 清 apt 缓存（apt-get clean + rm /var/cache/apt 的 pkgcache/srcpkgcache/archives） | 461→**304MB**（-157MB） | ✅ GHA 36184673157 SUCCESS，门禁过 | `git revert 1c26093` |
| 2 | (本次) | 仅加依赖链诊断（rdepends/simulate-remove/imgcodecs DT_NEEDED），**不改产物** | 不变 | 待 GHA | 无害，可留 |

## 待做（从诊断数据决策）
- LLVM(136MB)+mesa(46MB)+gdal 全家桶(~60MB)：被 mxnet 硬需的 `libopencv-imgcodecs406t64` 拖入。
  待诊断确认 imgcodecs 是否直链 gdal / 移除是否连带 opencv，再定「stub gdal」还是「apt remove」。
- OpenBLAS 三份（numpy ILP64 26MB / scipy LP64 22MB / apt LP64 18MB）：ABI 不同，wheel 自带难去重；
  仅可能安全的是让 mxnet 复用 scipy 的 LP64（symlink libopenblas.so.0）省 apt 那 18MB，风险中，门禁验。

## 关键事实（回滚时须知）
- mxnet `libmxnet.so` DT_NEEDED：libopenblas.so.0 + libopencv_{imgcodecs,imgproc,core}.so.406 + libgomp.so.1 —— 这些**缺一不可**，砍到它们 import 门禁必挂。
- 每次瘦身务必单独 commit + 本表记一行；GHA 门禁挂 = 该步不安全，revert。
