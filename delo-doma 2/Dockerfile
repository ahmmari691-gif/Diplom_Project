FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install --no-audit --no-fund
COPY frontend ./frontend
COPY core/help_topics.json ./core/help_topics.json
RUN cd frontend && npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 10000
CMD ["sh", "scripts/start-render.sh"]
