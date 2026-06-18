"""Pre-download PaddleOCR models during Docker build."""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    model_dir = Path(os.environ.get("PADDLE_OCR_MODEL_DIR", "/app/models/paddleocr"))
    model_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PADDLEOCR_HOME"] = str(model_dir)
    from paddleocr import PaddleOCR, PPStructure

    PaddleOCR(use_angle_cls=True, lang="ch", show_log=False, use_gpu=False)
    PPStructure(show_log=False, use_gpu=False, lang="ch", table=True, ocr=True)
    print(f"PaddleOCR models cached under {model_dir}")


if __name__ == "__main__":
    main()
