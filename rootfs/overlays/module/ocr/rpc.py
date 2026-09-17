"""MaaAL v3：in-proc OCR，替换 m0 的 TCP 桥版 rpc.py（原 zerorpc 实现的第二任替身）。

双引擎按 lang 路由：
- `azur_lane`：上游 cnocr densenet-lite-gru 权重的纯 numpy 移植（module/ocr/al_numpy.py +
  models/ocr/azur_lane/weights.npz），与桌面 mxnet 推理逐位一致（max|Δ|≈1e-5）。
  整页 ocr() = PP-OCR det 出框 + numpy 字体模型 rec；单行接口全走 numpy 模型。
  模型缺失时自动回落 PP-OCR。
- 其余 lang（cnocr/jp/tw/azur_lane_jp）：通用 PP-OCR（det.onnx + rec.onnx + keys.txt，
  复用 m0 资产）。

对外接口与 m0 版（m0-archive/termux/patches/module/ocr/rpc.py）逐字一致，
ocr.py / al_ocr.py / resource.py / webui/app.py 零改动：

- 模块级 `process`、`start_ocr_server` / `start_ocr_server_process` / `stop_ocr_server_process`（no-op）、`alive()`
- `ModelProxy`：init/close + ocr/ocr_for_single_line/ocr_for_single_lines/set_cand_alphabet/
  atomic_ocr/atomic_ocr_for_single_line/atomic_ocr_for_single_lines/debug
- `ModelProxyFactory`：五个语言名的惰性 __getattribute__ + close

与 m0 版的差异：
- "TCP 调用"换成"本进程推理"。alive() 语义从"桥已连接"改为"PP-OCR 模型已加载"。
- 模型路径：默认 ./models/ocr/（相对 ALAS 根；module/logger.py import 期已 chdir 到仓库根），
  环境变量 MAAAL_OCR_MODEL_DIR 可覆盖（本机/CI 测试用）。
- cand_alphabet：azur_lane 引擎实现了上游同款候选掩码；PP-OCR 路径无对应物不接，
  ALAS 的 Digit/DigitCounter/Duration.after_process 自己清洗（module/ocr/ocr.py:150-202）。
- onnxruntime/numpy/cv2 import 失败时：alive() 返回 False，OCR 调用 raise RequestHumanTakeover。

并发：调用方有 early_ocr_import 线程与 worker 线程池并发（m0 教训），
session.run 与模型加载均由一把 threading.RLock 串行化。
"""
import os
import threading

from module.exception import RequestHumanTakeover
from module.logger import logger
from module.webui.setting import State

try:
    import numpy as np
except ImportError:  # pragma: no cover - rootfs 必然有 numpy，兜底只为明确报错语义
    np = None

try:
    import onnxruntime as ort
except ImportError:
    ort = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from module.ocr.al_numpy import AlNumpyOcr
except Exception:  # al_numpy 自身依赖缺失/文件未铺时回落 PP-OCR，不拖死 rpc
    AlNumpyOcr = None

process = None  # 兼容原模块级变量（zerorpc 时代的服务进程句柄）

# DB 后处理阈值，与 PaddleOCR DBPostProcess 默认一致
_DET_THRESH = 0.3
_DET_BOX_THRESH = 0.6
_DET_UNCLIP_RATIO = 1.5
_DET_LIMIT_SIDE = 960
# rec 输入高（PP-OCR mobile rec 恒 48）
_REC_HEIGHT = 48


class _PpOcrEngine:
    """det+rec 两个 onnxruntime session 与 keys 表的载体。全部推理在本类内完成。"""

    def __init__(self, model_dir):
        if np is None or ort is None or cv2 is None:
            missing = [m for m, mod in [('numpy', np), ('onnxruntime', ort), ('cv2', cv2)] if mod is None]
            raise RuntimeError(f'MaaAL OCR: missing dependency: {", ".join(missing)}')

        det_path = os.path.join(model_dir, 'det.onnx')
        rec_path = os.path.join(model_dir, 'rec.onnx')
        keys_path = os.path.join(model_dir, 'keys.txt')
        for p in (det_path, rec_path, keys_path):
            if not os.path.isfile(p):
                raise RuntimeError(f'MaaAL OCR: model file not found: {p}')

        sess_options = ort.SessionOptions()
        sess_options.log_severity_level = 3
        threads = os.environ.get('MAAAL_OCR_THREADS')
        if threads:
            sess_options.intra_op_num_threads = max(1, int(threads))
        providers = ['CPUExecutionProvider']
        self.det = ort.InferenceSession(det_path, sess_options=sess_options, providers=providers)
        self.rec = ort.InferenceSession(rec_path, sess_options=sess_options, providers=providers)
        self.det_in_name = self.det.get_inputs()[0].name
        self.det_out_name = self.det.get_outputs()[0].name
        self.rec_in_name = self.rec.get_inputs()[0].name
        self.rec_out_name = self.rec.get_outputs()[0].name

        # rec 输入 [batch, 3, 48, W]：W 为字符串/'?'/None 即动态宽，否则静态宽（320 需 padding）
        rec_shape = self.rec.get_inputs()[0].shape
        self.rec_height = rec_shape[2] if isinstance(rec_shape[2], int) else _REC_HEIGHT
        self.rec_width = rec_shape[3] if isinstance(rec_shape[3], int) else None

        with open(keys_path, encoding='utf-8') as f:
            self.keys = f.read().splitlines()

        # CTC blank 在 index 0（PaddleOCR 约定 'blank' 占位）。用输出维数对 keys 数反推映射：
        # out == keys+1 → index i>0 映射 keys[i-1]；out == keys+2 → 另有尾部 ' '（PaddleOCR 惯例追加）。
        rec_out_dim = self.rec.get_outputs()[0].shape[-1]
        n_keys = len(self.keys)
        if isinstance(rec_out_dim, int):
            if rec_out_dim == n_keys + 1:
                self._tail_char = None
            elif rec_out_dim == n_keys + 2:
                self._tail_char = ' '
            else:
                logger.warning(f'MaaAL OCR: rec output dim {rec_out_dim} != keys {n_keys} +1/+2, assume +1')
                self._tail_char = None
        else:
            self._tail_char = None

    # ---------------------------------------------------------------- rec（生产主路径）

    def rec_line(self, image):
        """单行图（ALAS extract_letters 产物，2D uint8 灰度或 3ch BGR/RGB）→ 识别字符串。"""
        image = self._to_3ch_uint8(image)
        h, w = image.shape[:2]
        img_h = self.rec_height
        # 高对齐 img_h、宽按比例；静态宽模型再 pad 到固定宽（对应 PaddleOCR resize_norm_img）
        resized_w = max(1, int(round(img_h * w / float(h))))
        if self.rec_width is not None:
            resized_w = min(resized_w, self.rec_width)
        resized = cv2.resize(image, (resized_w, img_h), interpolation=cv2.INTER_LINEAR)
        if self.rec_width is not None and resized_w < self.rec_width:
            pad = np.zeros((img_h, self.rec_width - resized_w, 3), dtype=np.uint8)
            resized = np.concatenate([resized, pad], axis=1)
        x = resized.astype(np.float32) / 255.0
        x = (x - 0.5) / 0.5
        x = x.transpose((2, 0, 1))[np.newaxis, ...]
        out = self.rec.run([self.rec_out_name], {self.rec_in_name: x})[0]
        return self._ctc_greedy(out[0])

    def _ctc_greedy(self, preds):
        """[T, C] logits → greedy decode：argmax + 去连续重复 + 去 blank(0)。"""
        idx = preds.argmax(axis=1)
        n_keys = len(self.keys)
        chars = []
        prev = -1
        for i in idx:
            i = int(i)
            if i != prev and i != 0:
                if 0 < i <= n_keys:
                    chars.append(self.keys[i - 1])
                elif self._tail_char is not None and i == n_keys + 1:
                    chars.append(self._tail_char)
            prev = i
        return ''.join(chars)

    # ---------------------------------------------------------------- det+rec（整屏全管线）

    def det_rec(self, image):
        """整图 → [每框识别串]。标准 PP-OCR 流程，后处理对应 PaddleOCR DBPostProcess。"""
        return [text for _, text in self.det_rec_debug(image)]

    def det_boxes_crops(self, image):
        """整图 → [(box, crop)]：det_rec_debug 的 det 半边，供 azur_lane numpy 引擎
        复用 PP-OCR 的检测、用自己的字体模型做识别（对应上游 cnocr ocr() 的
        line_split + ocr_for_single_lines 角色）。"""
        image = self._to_3ch_uint8(image)
        h, w = image.shape[:2]
        # det 输入：最长边限 960，高宽 32 对齐（对应 DetResizeForTest limit_type=max）
        ratio = min(1.0, _DET_LIMIT_SIDE / float(max(h, w)))
        rs_h = max(32, int(round(h * ratio / 32.0)) * 32)
        rs_w = max(32, int(round(w * ratio / 32.0)) * 32)
        x = cv2.resize(image, (rs_w, rs_h), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0
        x = (x - 0.5) / 0.5
        x = x.transpose((2, 0, 1))[np.newaxis, ...]
        pred = self.det.run([self.det_out_name], {self.det_in_name: x})[0][0, 0]  # [rs_h, rs_w]

        pairs = []
        for box in self._boxes_from_bitmap(pred, rs_h, rs_w, h, w):
            crop = self._get_rotate_crop_image(image, box)
            if crop is not None:
                pairs.append((box, crop))
        return pairs

    def det_rec_debug(self, image):
        """整图 → [(box[4x2], text)]。诊断/门禁脚本（spike-f-ocr-gate.py）用，生产走 det_rec。"""
        image = self._to_3ch_uint8(image)
        h, w = image.shape[:2]
        # det 输入：最长边限 960，高宽 32 对齐（对应 DetResizeForTest limit_type=max）
        ratio = min(1.0, _DET_LIMIT_SIDE / float(max(h, w)))
        rs_h = max(32, int(round(h * ratio / 32.0)) * 32)
        rs_w = max(32, int(round(w * ratio / 32.0)) * 32)
        x = cv2.resize(image, (rs_w, rs_h), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0
        x = (x - 0.5) / 0.5
        x = x.transpose((2, 0, 1))[np.newaxis, ...]
        pred = self.det.run([self.det_out_name], {self.det_in_name: x})[0][0, 0]  # [rs_h, rs_w]

        boxes = self._boxes_from_bitmap(pred, rs_h, rs_w, h, w)
        results = []
        for box in boxes:
            crop = self._get_rotate_crop_image(image, box)
            if crop is None:
                continue
            results.append((box, self.rec_line(crop)))
        return results

    def _boxes_from_bitmap(self, pred, rs_h, rs_w, src_h, src_w):
        """对应 PaddleOCR DBPostProcess.__call__ + boxes_from_bitmap（pyclipper unclip 用
        minAreaRect 等比外扩近似：文本框近矩形，扩距 d = area*unclip_ratio/perimeter 等价于
        每边外移 d，误差在 UI 文本场景可忽略）。"""
        bitmap = (pred > _DET_THRESH).astype(np.uint8)
        contours, _ = cv2.findContours(bitmap * 255, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            # box 分数 = 框内 pred 均值（对应 get_box_score 的 box 裁剪近似，用 contour 掩膜）
            mask = np.zeros_like(bitmap)
            cv2.drawContours(mask, [contour], -1, 1, thickness=-1)
            score = float(pred[mask == 1].mean()) if mask.any() else 0.0
            if score < _DET_BOX_THRESH:
                continue
            # unclip：pyclipper 的多边形偏置，这里对 minAreaRect 的宽高各加 2d 近似
            rect = cv2.minAreaRect(contour)
            (cx, cy), (rw, rh), angle = rect
            area = max(cv2.contourArea(contour), 1.0)
            length = max(cv2.arcLength(contour, True), 1.0)
            distance = area * _DET_UNCLIP_RATIO / length
            rw += 2 * distance
            rh += 2 * distance
            if min(rw, rh) < 3:  # 对应 min_size=3
                continue
            box = cv2.boxPoints(((cx, cy), (rw, rh), angle))
            # 坐标映射回原图并裁剪边界
            box[:, 0] = np.clip(box[:, 0] * src_w / rs_w, 0, src_w - 1)
            box[:, 1] = np.clip(box[:, 1] * src_h / rs_h, 0, src_h - 1)
            boxes.append(box.astype(np.float32))
        # 与 PaddleOCR sorted_boxes 一致：按左上点 (y, x) 排序，阅读顺序自上而下
        boxes.sort(key=lambda b: (min(b[:, 1]), min(b[:, 0])))
        return boxes

    @staticmethod
    def _get_rotate_crop_image(image, points):
        """透视裁剪文本框，逐字对应 PaddleOCR get_rotate_crop_image。"""
        pts = points.astype(np.float32)
        width = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3])))
        height = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
        if width <= 0 or height <= 0:
            return None
        pts_std = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
        matrix = cv2.getPerspectiveTransform(pts, pts_std)
        dst = cv2.warpPerspective(image, matrix, (width, height),
                                  borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_CUBIC)
        if dst.shape[0] / float(dst.shape[1]) >= 1.5:  # 竖排文本转正
            dst = np.rot90(dst)
        return dst

    @staticmethod
    def _to_3ch_uint8(image):
        image = np.asarray(image)
        if image.ndim == 2:
            # m0 硬坑：PP-OCR 对单通道输入静默返回空；ALAS pre_process 的 2D 灰度行图堆叠成 3ch
            image = np.stack([image] * 3, axis=-1)
        elif image.ndim == 3 and image.shape[2] == 4:
            image = image[..., :3]  # RGBA → 去 alpha
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        return np.ascontiguousarray(image)

    def close(self):
        self.det = None
        self.rec = None


class ModelProxy:
    _engine = None
    _load_failed = False
    _al_engine = None
    _al_load_failed = False
    _lock = threading.RLock()  # 模型加载与 session.run 全局串行（m0 并发教训）
    online = True

    @classmethod
    def init(cls, address='127.0.0.1:22300'):
        """address 形参保留但忽略（in-proc 无连接）；内部做模型惰性加载。

        与 m0 版的差异：加载失败后不再每次访问都重试（缺模型文件时重试只会刷屏拖慢），
        close() 后重置失败标记，下一次 init 才会重新加载。
        """
        with cls._lock:
            if cls._engine is not None or cls._load_failed:
                return
            model_dir = os.environ.get('MAAAL_OCR_MODEL_DIR', './models/ocr')
            logger.info(f'MaaAL OCR: loading PP-OCR in-process from {model_dir}')
            try:
                cls._engine = _PpOcrEngine(model_dir)
                cls.online = True
                logger.info('MaaAL OCR: PP-OCR loaded (det+rec)')
            except Exception as e:
                cls._engine = None
                cls._load_failed = True
                cls.online = False
                logger.warning(f'MaaAL OCR: model load failed: {e}')

    @classmethod
    def close(cls):
        with cls._lock:
            if cls._engine is not None:
                logger.info('MaaAL OCR: release PP-OCR sessions')
                cls._engine.close()
            cls._engine = None
            cls._load_failed = False
            if cls._al_engine is not None:
                logger.info('MaaAL OCR: release azur_lane numpy model')
            cls._al_engine = None
            cls._al_load_failed = False

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            cls.init()
        if cls._engine is None:
            logger.critical('MaaAL OCR: model unavailable')
            raise RequestHumanTakeover
        return cls._engine

    @classmethod
    def _get_al_engine(cls):
        """azur_lane 字体模型（上游 cnocr 权重的纯 numpy 移植）惰性加载。

        模型文件缺失/加载失败时返回 None 并回落 PP-OCR（与 m0 桥版同语义：
        宁可用弱模型也不让任务死）。"""
        if AlNumpyOcr is None:
            return None
        with cls._lock:
            if cls._al_engine is not None or cls._al_load_failed:
                return cls._al_engine
            model_dir = os.path.join(os.environ.get('MAAAL_OCR_MODEL_DIR', './models/ocr'), 'azur_lane')
            logger.info(f'MaaAL OCR: loading azur_lane numpy model from {model_dir}')
            try:
                cls._al_engine = AlNumpyOcr(model_dir)
                logger.info('MaaAL OCR: azur_lane numpy model loaded (39 classes)')
            except Exception as e:
                cls._al_engine = None
                cls._al_load_failed = True
                logger.warning(f'MaaAL OCR: azur_lane numpy model load failed: {e}, fallback to PP-OCR')
            return cls._al_engine

    def _best_text(self, image, cand=None) -> str:
        """单行文本块：azur_lane 走 numpy 字体模型，其余走 PP-OCR rec（m0 only_rec 路径）。"""
        if self._al is not None:
            with self._lock:
                return ''.join(self._al.ocr_for_single_line(image, cand))
        engine = self._get_engine()
        with self._lock:
            return engine.rec_line(image)

    def _best_texts(self, images, cand=None) -> list:
        """成批单行：azur_lane 引擎必须整批走（批内宽补齐+截尾语义）。"""
        if self._al is not None:
            with self._lock:
                return [''.join(r) for r in self._al.ocr_for_single_lines(images, cand)]
        engine = self._get_engine()
        with self._lock:
            return [engine.rec_line(img) for img in images]

    def _all_texts(self, image, cand=None) -> list:
        """整图检测+识别：返回每行文本列表。azur_lane = PP-OCR det + numpy 字体模型 rec。"""
        engine = self._get_engine()
        if self._al is not None:
            with self._lock:
                pairs = engine.det_boxes_crops(image)
                if not pairs:
                    return []
                return [''.join(r) for r in self._al.ocr_for_single_lines(
                    [crop for _, crop in pairs], cand)]
        with self._lock:
            return engine.det_rec(image)

    def __init__(self, lang) -> None:
        self.lang = lang
        self._cand = None
        # azur_lane 用字体模型（上游桌面同款权重）；其余语言仍由 PP-OCR 全覆盖
        self._al = self._get_al_engine() if lang == 'azur_lane' else None

    # ---------------------------------------------------------------- 原 zerorpc 方法面（签名与 m0 版逐字一致）

    def ocr(self, img_fp):
        return [list(line) for line in self._all_texts(img_fp, self._cand)]

    def ocr_for_single_line(self, img_fp):
        return list(self._best_text(img_fp, self._cand))

    def ocr_for_single_lines(self, img_list):
        return [list(s) for s in self._best_texts(img_list, self._cand)]

    def set_cand_alphabet(self, cand_alphabet: str):
        # 与上游 CnOcr.set_cand_alphabet 同语义：设置后影响后续调用（状态保留在实例上）。
        # azur_lane numpy 引擎实现候选掩码；PP-OCR 路径无字符集约束能力，不接：
        # ALAS 的 Digit/after_process 会自行清洗非预期字符（module/ocr/ocr.py:150-202）。
        self._cand = cand_alphabet
        return None

    def atomic_ocr(self, img_fp, cand_alphabet=None):
        # 与上游 AlOcr.atomic_* 同语义：先 set_cand_alphabet（状态留置）再调用
        self._cand = cand_alphabet
        return self.ocr(img_fp)

    def atomic_ocr_for_single_line(self, img_fp, cand_alphabet=None):
        self._cand = cand_alphabet
        return self.ocr_for_single_line(img_fp)

    def atomic_ocr_for_single_lines(self, img_list, cand_alphabet=None):
        self._cand = cand_alphabet
        return self.ocr_for_single_lines(img_list)

    def debug(self, img_list):
        return None


class ModelProxyFactory:
    def __getattribute__(self, __name: str) -> ModelProxy:
        if __name in ['azur_lane', 'cnocr', 'jp', 'tw', 'azur_lane_jp']:
            if ModelProxy._engine is None:
                ModelProxy.init(address=State.deploy_config.OcrClientAddress)
            return ModelProxy(lang=__name)
        else:
            return super().__getattribute__(__name)

    def close(self):
        ModelProxy.close()


def start_ocr_server(port=22268):
    """no-op：OCR 在本进程内推理，无需本地服务端。"""
    logger.info('MaaAL: OCR served in-process, local OCR server not started')


def start_ocr_server_process(port=22268):
    return None


def stop_ocr_server_process():
    return None


def alive() -> bool:
    """语义 = "模型已加载"。未加载时尝试一次惰性加载，返回加载是否成功。"""
    ModelProxy.init()
    return ModelProxy._engine is not None
