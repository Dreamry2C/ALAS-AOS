# rootfs/wheels — 构建输入（whl 不入 git 历史）

ALAS 原版 OCR 用 `cnocr 1.2.2 + mxnet 1.9.1`。PyPI 没有 aarch64 的 mxnet 轮子，
故 `build-rootfs.sh` 从本目录安装一个自备的 aarch64 whl。

## 需要的文件

- `mxnet-1.9.1-py3-none-any.whl`
  - 内含 aarch64 `libmxnet.so`（链 `libopenblas.so.0` + OpenCV 4.6/`so.406`）；tag 标 `py3-none-any`
    以绕过平台校验（pip 会照装）。
  - 构建期 `build-rootfs.sh` 会 `strip --strip-unneeded` 掉其调试符号瘦身（~102MB → 更小）。
  - 默认路径 `rootfs/wheels/mxnet-1.9.1-py3-none-any.whl`，可用 `MXNET_WHL=<path>` 覆盖。

`.gitignore` 早前忽略过该 whl；现按方案 A 已提交进仓（~28.8MB），GHA `actions/checkout` 后即得。

## 复现构建时怎么提供它

- **本地 / 云机 chroot 烘**：whl 已随仓，放在本目录直接用（`MXNET_WHL` 可覆盖路径）。
- **GHA 烘（ubuntu-24.04-arm）**：whl 已随仓提交，`actions/checkout` 后 build-rootfs.sh 直接装；
  若日后嫌 git 历史膨胀，可改为 Git LFS 或 release 资产 + workflow 下载。

来源备注：三个候选 aarch64 whl 里选了体积最小、依赖最好补的「第二个版本」
（libopenblas + OpenCV4.6，ubuntu 24.04 apt 直接满足）。其余两个：whl#1 要 OpenCV4.5、
`mxnet_alas-0.0.5` 要 ARM Performance Libraries 专有栈，均弃。
