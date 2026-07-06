ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PRELOAD_OCR_MODELS=0

WORKDIR /app

# 国内构建时 deb.debian.org 常超时；按顺序尝试多个 Debian 镜像（清华源在容器内常 403）
RUN set -eux; \
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
      if [ -f "$f" ]; then cp "$f" "$f.orig"; fi; \
    done; \
    installed=0; \
    for mirror in ${APT_MIRROR} mirrors.aliyun.com mirrors.ustc.edu.cn mirrors.huaweicloud.com; do \
      for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
        if [ -f "$f.orig" ]; then \
          cp "$f.orig" "$f"; \
          sed -i "s|deb.debian.org|${mirror}|g; s|security.debian.org|${mirror}|g" "$f"; \
        fi; \
      done; \
      if apt-get update && apt-get install -y --no-install-recommends \
        libfreetype6 libpng16-16 libgomp1 libglib2.0-0 libgl1 poppler-utils; then \
        installed=1; break; \
      fi; \
      echo "apt install failed with mirror ${mirror}, trying next..."; \
    done; \
    test "$installed" = "1"; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN set -eux; \
    python -m pip install --upgrade pip; \
    installed=0; \
    for index in \
      "${PIP_INDEX_URL}" \
      "https://mirrors.aliyun.com/pypi/simple/" \
      "https://mirrors.cloud.tencent.com/pypi/simple/" \
      "https://repo.huaweicloud.com/repository/pypi/simple/" \
      "https://pypi.org/simple"; do \
      if pip install --no-cache-dir -r requirements.txt -i "${index}"; then \
        installed=1; break; \
      fi; \
      echo "pip install failed with index ${index}, trying next..."; \
    done; \
    test "${installed}" = "1"

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
