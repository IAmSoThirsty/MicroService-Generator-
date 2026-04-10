# ============================================================
# Genesis Microservices Generator — Multi-Stage Docker Build
# ============================================================
# Stage 1 : Build the React frontend
# Stage 2 : Package the Python backend with all dependencies
# Final   : Minimal runtime image serving both on port 8001
# ============================================================

# ---- Stage 1: Build React frontend ----
FROM node:18-alpine AS frontend
WORKDIR /frontend
COPY frontend/ .
# Install dependencies and produce an optimised production bundle
RUN yarn install --frozen-lockfile && yarn build

# ---- Stage 2: Python backend ----
FROM python:3.11-slim AS backend
WORKDIR /app

# System build deps (for packages that compile C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY backend/ ./backend/
COPY genesis.py ./
COPY service-spec.yaml ./

# Copy the compiled React bundle from the frontend stage
COPY --from=frontend /frontend/build ./frontend/build

# ---- Final runtime image ----
FROM python:3.11-slim
WORKDIR /app

# Copy everything from the backend stage
COPY --from=backend /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=backend /usr/local/bin /usr/local/bin
COPY --from=backend /app /app

# Runtime environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MONGO_URL=mongodb://localhost:27017 \
    DB_NAME=genesis \
    CORS_ORIGINS=*

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/')" || exit 1

CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8001"]
