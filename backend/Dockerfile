# syntax=docker/dockerfile:1.7

# JetPack 5.x / L4T R35 image for NVIDIA Jetson (ARM64).
# The host currently runs JetPack 5.1.6; override BASE_IMAGE when an exact
# R35.6.x image is available in your registry.
ARG BASE_IMAGE=nvcr.io/nvidia/l4t-jetpack:r35.4.1
FROM ${BASE_IMAGE}

ARG UV_VERSION=0.12.16

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    NVC_CONFIG_PATH=/app/data/config.json \
    NVC_BASELINES_PATH=/app/data/baselines \
    WALKWAY_CHECKPOINT=/app/weights/depth_anything_v2_vits.pth \
    WALKWAY_HOST=0.0.0.0 \
    WALKWAY_PORT=8000 \
    MEDIAMTX_API_URL=http://mediamtx:9997/v3 \
    MEDIAMTX_RTSP_URL=rtsp://mediamtx:8554

WORKDIR /app

# Native libraries used by OpenCV, Torch, camera decoding and Vietnamese fonts.
RUN test "$(uname -m)" = "aarch64" \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        ffmpeg \
        fonts-dejavu-core \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-tools \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libopenblas0 \
        libsm6 \
        libusb-1.0-0 \
        libxext6 \
        libxrender1 \
        python3 \
        python3-pip \
        python3-venv \
        v4l-utils \
    && rm -rf /var/lib/apt/lists/*

# Keep the dependency layer reusable when only application source changes.
COPY pyproject.toml uv.lock README.md ./
COPY wheels ./wheels

RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install "uv==${UV_VERSION}"

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY weights ./weights

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && mkdir -p /app/data/baselines

# Nạp GLdispatch trước Python/Torch để plugin GStreamer NVIDIA trên Jetson
# không bị lỗi "cannot allocate memory in static TLS block" khi mở camera.
ENV LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0

VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["walkway-server"]
