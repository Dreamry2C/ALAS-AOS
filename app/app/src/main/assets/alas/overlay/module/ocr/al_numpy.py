# -*- coding: utf-8 -*-
"""AlasAos：azur_lane 字体 OCR（上游 cnocr densenet-lite-gru 的纯 numpy 移植）。

背景：上游 ALAS 的 azur_lane 模型（39 字符 AL 字体微调，验证精度 99.43%）是 mxnet
私有格式，mxnet 无 ARM64 wheel 且已退役，手机上装不了。本文件把同一份权重
（PC 端从 cnocr-v1.2.0-densenet-lite-gru-0015.params 转储的 npz）用纯 numpy
重写前向，达到与 mxnet 逐位一致（13 组参考批 max|Δ|≈1e-5、字符串全同，见
.tmp/ocr-azurlane/np_forward.py 对拍）。

逐字复刻的语义（与 cnocr 1.2.2 + ALAS AlOcr 对齐）：
- 预处理：AlOcr._preprocess_img_array（h→32 等比 cv2.resize，/255，无归一化）
- 网络：densenet-lite（channels 32/64/128/256，BN eps=1e-5，valid 池化，
  末段 k(2,3) depthwise + k(2,1) 池化）→ BiGRU(hidden 128，cuDNN 变体：
  gate 序 r/z/n，n=tanh(i2h_n + r*(h2h_n))，h=(1-z)*n+z*h_prev) → FC(39)
- 解码：AlOcr._gen_line_pred_chars（softmax prob → argmax → >0.5 置信门 →
  批内窄图按 width//4 截尾 → CTC 去重去 blank）
- 字符集约束：CnOcr.set_cand_alphabet 的乘法掩码（[blank]+候选类）

输入契约与上游一致：2D 灰度 uint8 行图（ALAS extract_letters 产物）。
"""
import os

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - rootfs 必有 cv2
    cv2 = None

IMG_H = 32
BN_EPS = 1e-5  # gluon nn.BatchNorm 默认 epsilon
COMP_RATIO = 4  # hp.seq_len_cmpr_ratio（densenet 系）


# ---------------------------------------------------------------- 基础算子
def _sliding(x, kh, kw, sh, sw):
    """(N,C,H,W) → (N,C,oh,ow,kh,kw) valid 滑动窗视图（零拷贝）。"""
    n, c, h, w = x.shape
    oh = (h - kh) // sh + 1
    ow = (w - kw) // sw + 1
    sn, sc, sh_, sw_ = x.strides
    shape = (n, c, oh, ow, kh, kw)
    strides = (sn, sc, sh_ * sh, sw_ * sw, sh_, sw_)
    return np.lib.stride_tricks.as_strided(x, shape=shape, strides=strides)


def _conv2d(x, w, stride=(1, 1), pad=(0, 0), groups=1):
    """mxnet Convolution（no_bias=True, dilate 1）的 numpy 等价。
    普通卷积走 im2col+sgemm（BLAS）；depthwise 组卷积走 einsum（每组矩阵极小）。"""
    n, c, _, _ = x.shape
    f, _, kh, kw = w.shape
    ph, pw = pad
    sh, sw = stride
    if ph or pw:
        x = np.pad(x, [(0, 0), (0, 0), (ph, ph), (pw, pw)])
    win = _sliding(x, kh, kw, sh, sw)
    oh, ow = win.shape[2], win.shape[3]
    if groups == 1:
        cols = win.transpose(0, 2, 3, 1, 4, 5).reshape(n * oh * ow, c * kh * kw)
        out = cols @ w.reshape(f, -1).T                      # (n*oh*ow, f)
        return out.reshape(n, oh, ow, f).transpose(0, 3, 1, 2)
    g = groups
    cg, fg = c // g, f // g
    win = win.reshape(n, g, cg, oh, ow, kh, kw)
    wg = w.reshape(g, fg, cg, kh, kw)
    out = np.einsum('ngcijuv,gfcuv->ngfij', win, wg)
    return out.reshape(n, f, oh, ow)


def _bn(x, gamma, beta, mean, var):
    return ((x - mean[None, :, None, None]) / np.sqrt(var[None, :, None, None] + BN_EPS)
            * gamma[None, :, None, None] + beta[None, :, None, None])


def _maxpool(x, kernel, stride):
    kh, kw = kernel
    sh, sw = stride
    win = _sliding(x, kh, kw, sh, sw)
    return win.max(axis=(-2, -1))


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _softmax(x):
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=-1, keepdims=True)


# ---------------------------------------------------------------- 网络片段
def _dense_block(x, w, prefix, layers):
    """BN→relu→conv1x1→BN→relu→conv3x3(p1)→concat 输入（densenet lite 单层）。"""
    bn0, cv0, bn1, cv1 = layers
    y = np.maximum(_bn(x, w['arg:%s%s_gamma' % (prefix, bn0)], w['arg:%s%s_beta' % (prefix, bn0)],
                       w['aux:%s%s_running_mean' % (prefix, bn0)], w['aux:%s%s_running_var' % (prefix, bn0)]), 0)
    y = _conv2d(y, w['arg:%s%s_weight' % (prefix, cv0)])
    y = np.maximum(_bn(y, w['arg:%s%s_gamma' % (prefix, bn1)], w['arg:%s%s_beta' % (prefix, bn1)],
                       w['aux:%s%s_running_mean' % (prefix, bn1)], w['aux:%s%s_running_var' % (prefix, bn1)]), 0)
    y = _conv2d(y, w['arg:%s%s_weight' % (prefix, cv1)], pad=(1, 1))
    return np.concatenate([x, y], axis=1)


def _bn_relu(w, prefix, x):
    return np.maximum(_bn(x, w['arg:%s_gamma' % prefix], w['arg:%s_beta' % prefix],
                          w['aux:%s_running_mean' % prefix], w['aux:%s_running_var' % prefix]), 0)


def _densenet(x, w):
    """(N,1,32,W) → (N,512,1,S)"""
    p = 'densenet0_'
    y = _conv2d(x, w['arg:%sstage0_conv0_weight' % p], pad=(1, 1))
    y = _bn_relu(w, p + 'stage0_batchnorm0', y)
    y = _conv2d(y, w['arg:%sstage0_conv1_weight' % p], pad=(1, 1))
    x = np.concatenate([x, y], axis=1)                       # (N,65,32,W)

    x = _bn_relu(w, p + 'batchnorm0', x)                     # transition0
    x = _conv2d(x, w['arg:%sconv0_weight' % p])
    x = _maxpool(x, (2, 2), (2, 2))

    x = _dense_block(x, w, p + 'stage1_', ['batchnorm0', 'conv0', 'batchnorm1', 'conv1'])
    x = _dense_block(x, w, p + 'stage1_', ['batchnorm2', 'conv2', 'batchnorm3', 'conv3'])

    x = _bn_relu(w, p + 'batchnorm1', x)                     # transition1
    x = _conv2d(x, w['arg:%sconv1_weight' % p])
    x = _maxpool(x, (2, 2), (2, 2))

    x = _dense_block(x, w, p + 'stage2_', ['batchnorm0', 'conv0', 'batchnorm1', 'conv1'])
    x = _dense_block(x, w, p + 'stage2_', ['batchnorm2', 'conv2', 'batchnorm3', 'conv3'])

    x = _bn_relu(w, p + 'last_trans_batchnorm0', x)          # last transition
    x = _conv2d(x, w['arg:%slast_trans_conv0_weight' % p])
    x = np.maximum(x, 0)
    x = _conv2d(x, w['arg:%slast_trans_conv1_weight' % p], stride=(2, 1), pad=(0, 1), groups=256)

    x = _bn_relu(w, p + 'stage3_batchnorm0', x)              # stage3
    x = _maxpool(x, (2, 1), (2, 1))

    n, c, h, s = x.shape
    return x.reshape(n, c * h, s)[:, :, None, :]             # (N,512,1,S)


def _gru_one_dir(x, w, prefix, reverse):
    """(S,N,512) → (S,N,128)。mxnet cuDNN 版 GRU 逐字复刻。"""
    wi = w['arg:%s_i2h_weight' % prefix]
    bi = w['arg:%s_i2h_bias' % prefix]
    wh = w['arg:%s_h2h_weight' % prefix]
    bh = w['arg:%s_h2h_bias' % prefix]
    hs = wh.shape[1]
    if reverse:
        x = x[::-1]
    s_len = x.shape[0]
    i2h = (x.reshape(s_len * x.shape[1], -1) @ wi.T + bi).reshape(s_len, x.shape[1], -1)
    h = np.zeros((x.shape[1], hs), dtype=np.float32)
    outs = []
    for t in range(x.shape[0]):
        h2h = h @ wh.T + bh
        r = _sigmoid(i2h[t, :, :hs] + h2h[:, :hs])
        z = _sigmoid(i2h[t, :, hs:2 * hs] + h2h[:, hs:2 * hs])
        ng = np.tanh(i2h[t, :, 2 * hs:] + r * h2h[:, 2 * hs:])
        h = (1.0 - z) * ng + z * h
        outs.append(h)
    out = np.stack(outs, axis=0)
    return out[::-1] if reverse else out


def _forward(batch, w):
    """(N,1,32,W) → prob (S*N,39)（softmax 后，与上游 reshape 前同序）。"""
    emb = _densenet(batch, w)
    n = emb.shape[0]
    s = emb.shape[3]
    x = emb.squeeze(axis=2).transpose(2, 0, 1)               # (S,N,512)
    fwd = _gru_one_dir(x, w, 'gru0_l0', reverse=False)
    bwd = _gru_one_dir(x, w, 'gru0_r0', reverse=True)
    rnn = np.concatenate([fwd, bwd], axis=2)                 # (S,N,256)
    flat = rnn.reshape(s * n, 256)
    logits = flat @ w['arg:pred_fc_weight'].T + w['arg:pred_fc_bias']
    return _softmax(logits).reshape(s, n, -1)                # (S,N,39)


# ---------------------------------------------------------------- 对外引擎
class AlNumpyOcr:
    """azur_lane 字体模型引擎。加载 weights.npz + label_cn.txt，提供
    ocr_for_single_line(s)（返回字符列表，与 cnocr 对齐）。"""

    def __init__(self, model_dir):
        if cv2 is None:
            raise RuntimeError('AlasAos AL-OCR: cv2 unavailable')
        npz_path = os.path.join(model_dir, 'weights.npz')
        label_path = os.path.join(model_dir, 'label_cn.txt')
        for p in (npz_path, label_path):
            if not os.path.isfile(p):
                raise RuntimeError(f'AlasAos AL-OCR: model file not found: {p}')
        z = np.load(npz_path)
        self._w = {k: z[k] for k in z.files}
        self._alphabet = self._read_charset(label_path)
        self._inv_alph = {c: i for i, c in enumerate(self._alphabet) if c}

    @staticmethod
    def _read_charset(fp):
        """cnocr.utils.read_charset 逐字复刻（blank=None@0，'<space>'→' '）。"""
        alphabet = [None]
        with open(fp, encoding='utf-8') as f:
            for line in f:
                alphabet.append(line.rstrip('\n'))
        try:
            alphabet[alphabet.index('<space>')] = ' '
        except ValueError:
            pass
        return alphabet

    # ---------------- 预处理（AlOcr._preprocess_img_array）与批补齐（CnOcr._pad_arrays）
    @staticmethod
    def _preprocess(img):
        if img.ndim == 3:
            # 防御路径：上游 AlOcr 假定 2D 灰度输入（生产送图均为 extract_letters 产物）。
            # 真收到彩图时按 ALAS BGR 约定转灰，宁可可用也不 raise。
            if img.shape[2] == 4:
                img = img[..., :3]
            img = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2GRAY)
        new_width = int(round(IMG_H / img.shape[0] * img.shape[1]))
        img = cv2.resize(img, (new_width, IMG_H))
        return np.expand_dims(img, 0).astype('float32') / 255.0

    @staticmethod
    def _pad(img_list):
        img_widths = [img.shape[2] for img in img_list]
        if len(img_list) <= 1:
            return img_list, img_widths
        max_width = max(img_widths)
        padded = []
        for img in img_list:
            if img.shape[2] < max_width:
                img = np.pad(img, [(0, 0), (0, 0), (0, max_width - img.shape[2])],
                             'constant', constant_values=0.0)
            padded.append(img)
        return padded, img_widths

    # ---------------- 解码（AlOcr._gen_line_pred_chars + CtcMetrics.ctc_label）
    def _decode_line(self, line_prob, img_width, max_img_width, cand_idx):
        if cand_idx is not None:
            mask = np.zeros(line_prob.shape[1], dtype=np.float32)
            mask[cand_idx] = 1.0
            line_prob = line_prob * mask[None, :]
        class_ids = np.argmax(line_prob, axis=-1)
        class_ids = class_ids * (np.max(line_prob, axis=-1) > 0.5)
        if img_width < max_img_width:
            end_idx = img_width // COMP_RATIO
            if end_idx < len(class_ids):
                class_ids[end_idx:] = 0
        # ctc_label：去连续重复、去 blank(0)
        ret = []
        prev = 0
        for c in class_ids.tolist():
            if c != 0 and c != prev:
                ret.append(c)
            prev = c
        alphabet = self._alphabet
        return [alphabet[p] if alphabet[p] != '<space>' else ' ' for p in ret]

    def _cand_idx(self, cand_alphabet):
        if cand_alphabet is None:
            return None
        idx = [0] + [self._inv_alph[c] for c in cand_alphabet if c in self._inv_alph]
        idx.sort()
        return idx

    # ---------------- 公共方法面（与 cnocr 对齐：返回 list[list[char]]）
    def ocr_for_single_lines(self, img_list, cand_alphabet=None):
        if len(img_list) == 0:
            return []
        img_list = [self._preprocess(np.asarray(img)) for img in img_list]
        img_list, img_widths = self._pad(img_list)
        batch = np.stack(img_list, axis=0)
        prob = _forward(batch, self._w)                      # (S,N,39)
        max_w = max(img_widths)
        cand_idx = self._cand_idx(cand_alphabet)
        return [self._decode_line(prob[:, i, :], img_widths[i], max_w, cand_idx)
                for i in range(batch.shape[0])]

    def ocr_for_single_line(self, img, cand_alphabet=None):
        return self.ocr_for_single_lines([np.asarray(img)], cand_alphabet)[0]
