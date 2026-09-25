# rootfs/wheels — 构建输入（whl 不入 git 历史）

ALAS 原版 OCR 用 `cnocr 1.2.2 + mxnet 1.9.1`。PyPI 没有 aarch64 的 mxnet 轮子，
故 `build-rootfs.sh` 从本目录安装一个自备的 aarch64 whl。

## 需要的文件

- `mxnet-1.9.1-py3-none-any.whl`
  - 内含 aarch64 `libmxnet.so`（链 `libopenblas.so.0` + OpenCV 4.6/`so.406`）；tag 标 `py3-none-any`
    以绕过平台校验（pip 会照装）。
  - 构建期 `build-rootfs.sh` 会 `strip --strip-unneeded` 掉其调试符号瘦身（~102MB → 更小）。
  - 默认路径 `rootfs/wheels/mxnet-1.9.1-py3-none-any.whl`，可用 `MXNET_WHL=<path>` 覆盖。

`.gitignore` 忽略了 `rootfs/wheels/*.whl`，避免把 ~28.8MB 二进制永久写进 git 历史。

## 复现构建时怎么提供它

- **本地 / 云机 chroot 烘**：把 whl 放到本目录即可（当前主用路径）。
- **GHA 烘（ubuntu-24.04-arm）**：把 whl 作为 GitHub release 资产或 Git LFS 对象托管，
  在 workflow 里下载到本目录；或直接提交本 whl（体积可接受时再定）。

来源备注：三个候选 aarch64 whl 里选了体积最小、依赖最好补的「第二个版本」
（libopenblas + OpenCV4.6，ubuntu 24.04 apt 直接满足）。其余两个：whl#1 要 OpenCV4.5、
`mxnet_alas-0.0.5` 要 ARM Performance Libraries 专有栈，均弃。
