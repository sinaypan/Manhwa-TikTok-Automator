import importlib.util
import subprocess
import sys

import pytest


@pytest.mark.skipif(not (importlib.util.find_spec("paddle") and importlib.util.find_spec("ctranslate2")),
                    reason="Paddle ou CTranslate2 absent")
def test_whisper_still_loads_after_paddle():
    # « Tout faire » : la lecture du texte (Paddle) passe avant la réécoute des voix (Whisper, CTranslate2)
    code = "from manhwa.ocr_engines import paddle_device; paddle_device(); import ctranslate2; print('ok')"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert out.stdout.strip().endswith("ok"), out.stderr[-500:]
