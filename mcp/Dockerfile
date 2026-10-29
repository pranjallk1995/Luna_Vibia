FROM python:3.12-slim

WORKDIR /workspace/mcp

# ffprobe and ffmpeg read and decode every audio format Vibia stores.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv installs the requirements; its cache mount reuses downloads across rebuilds.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_LINK_MODE=copy
# requirements.txt adds the PyTorch CUDA 13.0 index for torch; let uv pick the best
# version across both indexes, since that index also carries old copies of
# common packages.
ENV UV_INDEX_STRATEGY=unsafe-best-match

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

# Bake the CLAP model into the image so the first upload does not wait on a
# download and analysis never contacts the Hugging Face hub.
RUN python -c "from transformers import ClapModel, ClapProcessor; \
ClapModel.from_pretrained('laion/clap-htsat-unfused'); ClapProcessor.from_pretrained('laion/clap-htsat-unfused')"
ENV HF_HUB_OFFLINE=1

COPY app ./app
COPY tests ./tests

EXPOSE 8000

CMD ["python", "-m", "app.main"]
