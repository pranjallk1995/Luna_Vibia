# Build the React app; only its static output reaches the runtime image.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /workspace/ui

# uv installs the requirements; its cache mount reuses downloads across rebuilds.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_LINK_MODE=copy

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

COPY config.py gateway.py hidden_pin.py tracks.py sso.py ./
COPY tests ./tests
COPY --from=web /web/dist ./static

EXPOSE 8501

CMD ["uvicorn", "gateway:create_app", "--factory", "--host=0.0.0.0", "--port=8501", "--no-access-log"]
