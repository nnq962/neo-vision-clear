# syntax=docker/dockerfile:1.7

# JetPack 5.x / L4T R35 image for NVIDIA Jetson (ARM64).
# The host currently runs JetPack 5.1.6; override BASE_IMAGE when an exact
# R35.6.x image is available in your registry.
ARG BASE_IMAGE=nvcr.io/nvidia/l4t-jetpack:r35.4.1
FROM ${BASE_IMAGE}

ARG UV_VERSION=0.12.16
ARG ASSET_BASE_URL=https://huggingface.co/quyetnguyen0188/assets/resolve/main
ARG DEPTH_CHECKPOINT_URL=${ASSET_BASE_URL}/weights/pytorch/depth-anything-v2/depth_anything_v2_vits.pth
ARG DEPTH_CHECKPOINT_SHA256=715fade13be8f229f8a70cc02066f656f2423a59effd0579197bbf57860e1378
ARG OPENCV_WHEEL_URL=${ASSET_BASE_URL}/wheels/jp5.1.6/opencv_contrib_python-4.13.0.90-cp38-cp38-linux_aarch64.whl
ARG OPENCV_WHEEL_SHA256=b7dae96844a5591361ac1e610442f12c405c1f7fa1c13272863807fca512a1c7
ARG TORCH_WHEEL_URL=${ASSET_BASE_URL}/wheels/jp5.1.6/torch-2.1.0a0%2B41361538.nv23.06-cp38-cp38-linux_aarch64.whl
ARG TORCH_WHEEL_SHA256=5112e2ef5051f1003ae2ffb545ae596377df66979d62a954d774f18009064dbe
ARG TORCHVISION_WHEEL_URL=${ASSET_BASE_URL}/wheels/jp5.1.6/torchvision-0.16.1-cp38-cp38-linux_aarch64.whl
ARG TORCHVISION_WHEEL_SHA256=fa636d72b33bf7ab0fa7f0141cdd58ac97d685f539f332ba79002507074a49bd

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    NVC_CONFIG_PATH=/app/data/config.json \
    NVC_BASELINES_PATH=/app/data/baselines \
    WALKWAY_CHECKPOINT=/app/weights/pytorch/depth-anything-v2/depth_anything_v2_vits.pth \
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
        curl \
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

# The JetPack wheels and model checkpoint are intentionally not stored in Git.
# Downloading them here makes a clean clone buildable and keeps exact file paths
# expected by pyproject.toml and WALKWAY_CHECKPOINT.
RUN mkdir -p /app/wheels/jp5.1.6 /app/weights/pytorch/depth-anything-v2 \
    && curl --fail --location --retry 5 --retry-connrefused \
        --output /app/wheels/jp5.1.6/opencv_contrib_python-4.13.0.90-cp38-cp38-linux_aarch64.whl \
        "${OPENCV_WHEEL_URL}" \
    && curl --fail --location --retry 5 --retry-connrefused \
        --output /app/wheels/jp5.1.6/torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl \
        "${TORCH_WHEEL_URL}" \
    && curl --fail --location --retry 5 --retry-connrefused \
        --output /app/wheels/jp5.1.6/torchvision-0.16.1-cp38-cp38-linux_aarch64.whl \
        "${TORCHVISION_WHEEL_URL}" \
    && curl --fail --location --retry 5 --retry-connrefused \
        --output /app/weights/pytorch/depth-anything-v2/depth_anything_v2_vits.pth \
        "${DEPTH_CHECKPOINT_URL}" \
    && printf '%s  %s\n' \
        "${OPENCV_WHEEL_SHA256}" /app/wheels/jp5.1.6/opencv_contrib_python-4.13.0.90-cp38-cp38-linux_aarch64.whl \
        "${TORCH_WHEEL_SHA256}" /app/wheels/jp5.1.6/torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl \
        "${TORCHVISION_WHEEL_SHA256}" /app/wheels/jp5.1.6/torchvision-0.16.1-cp38-cp38-linux_aarch64.whl \
        "${DEPTH_CHECKPOINT_SHA256}" /app/weights/pytorch/depth-anything-v2/depth_anything_v2_vits.pth \
        | sha256sum --check --strict

RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install "uv==${UV_VERSION}"

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src

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
