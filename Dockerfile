# Nexora (package: datamind) — Streamlit app in a container.
#   docker compose up --build        then open http://localhost:8501
# Secrets never enter the image: .env is passed at run time (see docker-compose.yml) and .dockerignore excludes it.
# stage 1: build the React frontend (web/) into static files
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# stage 2: the Python app (Streamlit UI + REST API serving the built React app)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# dependencies first, so code changes don't reinstall them
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=web /web/dist ./web/dist

# run as an unprivileged user; .cache (Gemma reply cache) and runs (answer log) must be writable
RUN useradd --create-home --uid 1000 nexora && mkdir -p .cache runs && chown -R nexora:nexora /app
USER nexora

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"

ENTRYPOINT ["streamlit", "run", "app/streamlit_app.py", \
            "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
