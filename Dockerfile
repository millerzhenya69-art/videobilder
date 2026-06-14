FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONIOENCODING=utf-8

# FFmpeg + шрифты с полной поддержкой кириллицы
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
        fonts-dejavu \
        fonts-noto \
        fonts-noto-core \
        fontconfig \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY . .

RUN pip install --upgrade pip \
    && pip install ".[dev]" 2>/dev/null || pip install .

# Создаём нужные директории
RUN mkdir -p cache/videos cache/audio logs assets/downloaded assets/generated

CMD ["atlanta-vpn-bot"]
