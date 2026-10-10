#!/usr/bin/env python3
"""Run inside an isolated ARM64 rootfs; write only to the supplied work directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


def smoke(alas_root, work):
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.dont_write_bytecode = True
    work.mkdir(parents=True, exist_ok=True)
    os.chdir(work)
    # ALAS's original logger changes cwd to its own module parent on import.
    # Import a byte-identical disposable module copy so that its normal logs
    # stay outside the protected ALAS tree. Models are read from the original.
    import_root = work / 'imports'
    if not (import_root / 'module').exists():
        shutil.copytree(alas_root / 'module', import_root / 'module', symlinks=True)
    sys.path.insert(0, str(import_root))
    import numpy as np
    import scipy
    from scipy import linalg, ndimage, signal
    import cv2
    from PIL import Image
    import imageio
    import mxnet as mx
    import cnocr
    import pywebio, uvicorn, fastapi, pydantic, yaml, requests
    import adbutils, uiautomator2, uiautomator2cache
    import ssl
    from zoneinfo import ZoneInfo

    matrix = np.array([[4., 1., 2.], [1., 3., 0.], [2., 0., 5.]])
    assert np.allclose(matrix @ linalg.inv(matrix), np.eye(3))
    numeric = [float(np.linalg.det(matrix)), float(linalg.det(matrix)),
               float(ndimage.gaussian_filter(matrix, 1).sum()),
               float(signal.convolve2d(matrix, np.ones((2, 2))).sum())]
    pixels = np.arange(32 * 48 * 3, dtype=np.uint8).reshape((32, 48, 3))
    ok, encoded = cv2.imencode('.png', pixels)
    assert ok and np.array_equal(cv2.imdecode(encoded, cv2.IMREAD_COLOR), pixels)
    assert cv2.imdecode(cv2.imencode('.jpg', pixels)[1], cv2.IMREAD_COLOR).shape == pixels.shape
    # Exercise MXNet's separate apt OpenCV chain as well as the Python wheel.
    assert tuple(mx.image.imdecode(encoded.tobytes()).shape) == pixels.shape
    # Compare the actual imgcodecs consumer across a replacement, not just cv2
    # (the Python wheel carries a separate OpenCV implementation).
    codec_pixels = np.arange(96 * 128 * 3, dtype=np.uint8).reshape((96, 128, 3))
    native_codecs = {}
    for extension in ('.png', '.jpg', '.bmp', '.tiff', '.webp', '.jp2', '.ppm'):
        ok, buffer = cv2.imencode(extension, codec_pixels)
        assert ok, f'Cannot encode test input: {extension}'
        frame = mx.image.imdecode(buffer.tobytes()).asnumpy()
        assert frame.shape == codec_pixels.shape, (extension, frame.shape)
        native_codecs[extension] = hashlib.sha256(frame.tobytes()).hexdigest()
    gif = work / 'palette.gif'
    Image.fromarray(pixels).convert('P').save(gif)
    decoded = imageio.v2.imread(gif)
    assert decoded.shape[:2] == pixels.shape[:2]
    assert ssl.create_default_context().cert_store_stats()['x509_ca'] > 0
    assert str(ZoneInfo('Asia/Shanghai')) == 'Asia/Shanghai'

    from module.ocr.al_ocr import AlOcr
    # Synthetic inputs contain no user screenshots/configuration. Compare the
    # original models' exact predictions before and after each trim group.
    # Epochs match the upstream module/ocr/models.py definitions.
    ocr_models = {}
    for name, epoch in (('azur_lane', 15), ('azur_lane_jp', 20), ('cnocr', 39), ('jp', 125), ('tw', 63)):
        model_root = alas_root / 'bin/cnocr_models' / name
        labels = set((model_root / 'label_cn.txt').read_text(encoding='utf-8').splitlines())
        assert set('0123456789') <= labels, f'{name} has no numeric OCR alphabet'
        alphabet = ''.join(char for char in '0123456789/' if char in labels)
        model = AlOcr(model_name='densenet-lite-gru', model_epoch=epoch,
                      root=str(model_root), name='trim_validation_' + name)
        predictions = []
        for text in ('12345', '67890', '2026', '100/200'):
            frame = np.full((40, 200), 255, dtype=np.uint8)
            cv2.putText(frame, text, (2, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2, cv2.LINE_AA)
            prediction = model.atomic_ocr_for_single_line(frame, cand_alphabet=alphabet)
            predictions.append(''.join(prediction))
        assert any(predictions), f'OCR must load the {name} model and recognize text'
        params = model_root / f'cnocr-v1.2.0-densenet-lite-gru-{epoch:04d}.params'
        ocr_models[name] = {'predictions': predictions, 'alphabet': alphabet,
                            'params_sha256': hashlib.sha256(params.read_bytes()).hexdigest()}
    return {'numeric': numeric, 'ocr_predictions': ocr_models['azur_lane']['predictions'],
            'ocr_model_sha256': ocr_models['azur_lane']['params_sha256'], 'ocr_models': ocr_models,
            'versions': {'numpy': np.__version__, 'scipy': scipy.__version__,
                         'cv2': cv2.__version__, 'mxnet': mx.__version__,
                         'imageio': imageio.__version__},
            'png_sha256': hashlib.sha256(encoded.tobytes()).hexdigest(),
            'native_imgcodecs_sha256': native_codecs,
            'gif_shape': list(decoded.shape), 'imports_ok': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--alas-root', type=Path, default=Path('/opt/alas'))
    p.add_argument('--work', type=Path, default=Path('/aos-validation/work'))
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = smoke(args.alas_root.resolve(), args.work.resolve())
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('RUNTIME_SMOKE_OK', json.dumps(report))


if __name__ == '__main__':
    main()
