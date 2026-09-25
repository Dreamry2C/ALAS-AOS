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
| 2 | `f66d1d7` | 加依赖链诊断（不改产物） | 不变(~304MB) | ✅ GHA 36186161374 SUCCESS | 无害可留 |
| 3 | `b45b36a`→`2ab5dbc` | **手术**：删 LLVM(136)+mesa(46) GL 软栈（gdal 空壳方案作废，保留真 gdal+全套编解码依赖） | 304→**283MB** | ✅ GHA 36188636403 SUCCESS，门禁过 | `git revert 2ab5dbc c20d18e b45b36a`（或 reset 到 1c26093） |

## 汇总
- rootfs.tar.xz：**461MB（基线）→ 304MB（清 apt 缓存）→ 283MB（删 LLVM+mesa）**，共 -178MB（-39%）。
- OCR 链完好：每步 import 硬门禁均过（`import mxnet`+`cnocr`+numpy 垫片）。
- 结论：283MB 为收尾。再往下（gdcm11/openexr/scipy-blas 十几 MB 级）事倍功半，除非用户要求，停。

## 诊断结论（run 36186161374 日志）
- `imgcodecs.so.406` DT_NEEDED **直链 libgdal.so.34** + libjpeg/webp/png/tiff/openjp2 → gdal 必须在场（故换空壳，不能纯删）。
- rdepends：`libgdal34t64 <- libopencv-imgcodecs406t64`；`mesa-libgallium <- libgbm1,libglx-mesa0`；`libllvm20 <- mesa-libgallium`；`libopenblas0-pthread <- (无 apt 包依赖，仅 mxnet DT_NEEDED)`。
- `apt-get remove libgdal ...` 会**连锁 purge 掉 opencv-core/imgproc/imgcodecs** → 不能 apt-remove，只能「换空壳 + 删文件（不动 dpkg db）」。
- 空壳原理：DT_NEEDED 只要求 .so 在场；推理不读图像文件 → 不触发 gdal 符号 → 惰性绑定不崩。若 imgcodecs 初始化真调了 gdal 符号，门禁会挂 → 回滚步 3。

## 步骤 3 手术迭代（踩坑记录）
- `b45b36a`：GHA 36187090572 **失败**——`ld: no input files`（我 `ld -shared` 没给输入）。非概念问题。
- `c20d18e`：修 ld（`echo|as -o empty.o` 再 ld）。GHA 36187460677 **失败**——`OSError: libgdcmMSFF.so.3.0: cannot open`：**gdcm 是 imgcodecs 直接 DT_NEEDED，我误删了**。→ 学到：imgcodecs 的直接依赖一个都不能删，只能 keep 或 stub。
- (本次修)：删除列表去掉 gdcm/spatialite/mysql（保留），只删 **LLVM+mesa+proj ≈205MB**（确认非 imgcodecs 直接依赖）；诊断改为打印 imgcodecs 全部 DT_NEEDED。待 GHA 验。**gdal 空壳本身能否过 import（imgcodecs 初始化不调 gdal 符号）仍待这轮首次验证。**
- `99f5a30`：GHA 36188071266 **失败**——`undefined symbol: GDALRasterBand::RasterIO`：**imgcodecs 真用 gdal 符号，空壳过不了 dlopen**（不是惰性、载入即需）。imgcodecs 全 DT_NEEDED 也确认含 OpenEXR/gdcm 两库。→ **放弃 gdal 空壳方案**。
- (最终)：保留**真 gdal + proj + gdcm + openexr 等全部编解码依赖**，只删 **LLVM(136)+mesa(46)=~182MB**（GL 软栈，仅 gdal 的 GL 驱动惰性 dlopen，mxnet 永不触发；gdal.so 不直链它们）。这是最稳的一刀。待 GHA 验。

## 待做（从诊断数据决策）
- LLVM(136MB)+mesa(46MB)+gdal 全家桶(~60MB)：被 mxnet 硬需的 `libopencv-imgcodecs406t64` 拖入。
  待诊断确认 imgcodecs 是否直链 gdal / 移除是否连带 opencv，再定「stub gdal」还是「apt remove」。
- OpenBLAS 三份（numpy ILP64 26MB / scipy LP64 22MB / apt LP64 18MB）：ABI 不同，wheel 自带难去重；
  仅可能安全的是让 mxnet 复用 scipy 的 LP64（symlink libopenblas.so.0）省 apt 那 18MB，风险中，门禁验。

## 关键事实（回滚时须知）
- mxnet `libmxnet.so` DT_NEEDED：libopenblas.so.0 + libopencv_{imgcodecs,imgproc,core}.so.406 + libgomp.so.1 —— 这些**缺一不可**，砍到它们 import 门禁必挂。
- 每次瘦身务必单独 commit + 本表记一行；GHA 门禁挂 = 该步不安全，revert。
