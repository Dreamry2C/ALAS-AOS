# Handoff 2026-09-26 · 把原版 OCR（cnocr+mxnet）设备方案弄成可复现构建

> 用户令（2026-09-26）：①移除 AOS 加的 PP-OCR/自研 OCR，用 AlasToFox 原版 cnocr+mxnet（作者精调）；②更新源=用户在设置里填上游源+分支，AOS 即用它 `git fetch + reset --hard` 更新——**这是有意设计（方便随时切分支免冲突），保留不动**；③把 mimov 在 66 跑通的设备端 OCR/mxnet 方案「弄成一个构建、可复现」。
> 上一篇：`2026-09-25-fullscreen-and-findings.md`（mimov 阶段）。实时流水 `.tmp/2026-09-25-live.md`。

## ★可复现配方（2026-09-26 从 66 工作态实测捕获；py3.12，**不需要 py3.8**）★

- **base**：ubuntu-base 24.04 arm64（不变）；guest Python 3.12。mimov 定案 2「py3.8 重烘」已被 numpy_shim 方案取代作废。
- **ALAS 源**：AlasToFox（自带 azur_lane 模型 `bin/cnocr_models/azur_lane/cnocr-v1.2.0-densenet-lite-gru-{0015.params(3.4MB),symbol.json,label_cn.txt}`，epoch15）。
- **apt（满足 mxnet whl 的 openblas+opencv4.6 DT_NEEDED）**：`libopenblas0-pthread`、`libopencv-core406t64`、`libopencv-imgproc406t64`、`libopencv-imgcodecs406t64`。
- **pip 关键钉版（改自现 base 现代集）**：`numpy==1.26.4`（原为 >=2）、`scipy==1.13.1`、`opencv-python-headless==4.10.0.84`、`pydantic==1.10.26`(v1)、`imageio==2.27.0`（build 用上游钉版；66 因 proot TLS 装成 2.37.4，干净 build 反而能上更稳的 2.27.0）。
- **OCR 链**：`pip install <mxnet whl#2>`（mxnet 1.9.1，aarch64 libmxnet.so，链 openblas+opencv406；whl#1 要 opencv4.5、mxnet_alas 要 ARM PL 专有栈，均弃）→ `pip install cnocr==1.2.2 --no-deps`（推理路径不需 gluoncv/matplotlib/pandas，66 实测 `INFER_OK`）。
- **numpy 垫片**：`rootfs/shims/numpy_shim.py`（补 numpy≥1.24 删掉的别名 PZERO/NZERO/long/ulong/Inf/NaN/asscalar… 供 mxnet1.9.1/cnocr1.2.2）+ `zzz_alas_shim.pth`（内容 `import numpy_shim`，随 site 自启）→ 装进 guest purelib。
- **deploy.yaml**：`UseOcrServer: false`（原版链走 `ocr.py`→直推 `OCR_MODEL`=cnocr；repo 现为 `true` 需改）。`AutoUpdate:false` 保留。
- **退役 PP-OCR**：build 不再 `cp overlays/module/ocr/rpc.py`、不装 `det/rec/keys.onnx`；清理 build 输入 `rootfs/overlays/module/ocr/{rpc.py,al_numpy.py}` + `rootfs/models/ocr/*`（与 d8bcb37 删 app 资产一致；AlasToFox 自带 rpc.py=zerorpc，UseOcrServer:false 时不走它）。
- 完整工作集（66 dist-info 全表，54 包）见 live log/附录；核心即上述。

## 需要你后续拍板（不阻塞，构建已参数化）

1. **AlasToFox 源怎样进构建**：GHA 够不到未发布的 AlasToFox。选项——(a) 你把 AlasToFox 推到 GHA 可达处（公开/私有+token），`ALAS_REPO` 指它（发布后最干净）；(b) 本地/云机 chroot 用本地 AlasToFox 烘（现在可行）；(c) 提交 git bundle。build-rootfs 已参数化 `ALAS_REPO`/`ALAS_SRC_DIR`。**发布前先走 (b)**。
2. **mxnet whl（~107MB）放哪**：不宜直接进 git（每次 clone 膨胀）。选项——GitHub release 资产+构建下载（推荐，GHA 友好）/ Git LFS / 就近路径提供。build-rootfs 用 `MXNET_WHL` 参数消费，**暂不入 git**。

## 产出与验证路径

- 本机 Windows 无 chroot、GHA 暂够不到 AlasToFox → **现在**：在 66 云机 chroot 用新 build-rootfs 逻辑烘 `rootfs.tar.xz`（或快照 66 工作态兜底）→ 塞进 `app/app/src/main/assets/rootfs/` → `assembleDebug` → 装 66 复验原版 OCR 加载+读数。
- **将来**：AlasToFox 发布 + whl 上 release 后，GHA `ubuntu-24.04-arm` 一键干净烘（改动已在脚本里）。

## 红线
- 不 push/发版、不重启云机、不清碧蓝数据；不改 ALAS/AlasToFox 上游逻辑（换源+依赖+overlay/seeds 层做文章）。更新源+分支+reset--hard 保留（用户有意设计）。
