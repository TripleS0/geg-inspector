ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PRELOAD_OCR_MODELS=0

WORKDIR /app

# 国内构建时 deb.debian.org 常超时，切换到可配置的 Debian 镜像源
RUN set -eux; \
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
      if [ -f "$f" ]; then sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" "$f"; fi; \
    done; \
    for attempt in 1 2 3 4 5; do \
      apt-get update && \
      apt-get install -y --no-install-recommends \
        libfreetype6 \
        libpng16-16 \
        libgomp1 \
        libglib2.0-0 \
        libgl1 \
        poppler-utils && break; \
      echo "apt install retry ${attempt}..."; sleep 15; \
    done; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i ${PIP_INDEX_URL}

ENV PADDLE_OCR_MODEL_DIR=/app/models/paddleocr \
    PADDLEOCR_HOME=/app/models/paddleocr \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1
RUN mkdir -p /app/models/paddleocr

COPY backend/scripts/download_paddleocr_models.py backend/scripts/download_paddleocr_models.py
# Apple Silicon / arm64 构建时预加载 Paddle 模型可能 SIGSEGV；默认跳过，首次 OCR 联网下载
RUN if [ "$PRELOAD_OCR_MODELS" = "1" ]; then python backend/scripts/download_paddleocr_models.py; else echo "Skip OCR model preload (set PRELOAD_OCR_MODELS=1 to enable)"; fi

COPY backend/ backend/

ENV DATAFUSIONX_HOME=/data \
    DATAFUSIONX_HOST=0.0.0.0 \
    DATAFUSIONX_BACKEND_PORT=8765

EXPOSE 8765

VOLUME ["/data"]

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8765"]
