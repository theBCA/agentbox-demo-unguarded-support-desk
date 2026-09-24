# The unguarded twin of starter-apps/support-desk. Same page, same job, a
# different agent SDK (OpenAI), and nothing wrapping it: no Package Guard
# stage, no CA injection, a writable rootfs, a real key in the environment.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY ui ./ui
COPY concept ./concept

RUN useradd --create-home --home-dir /home/agent --uid 10001 --user-group agent
RUN mkdir -p /tmp/agent-state && chown -R 10001:10001 /tmp/agent-state /home/agent
USER 10001:10001

EXPOSE 8081

HEALTHCHECK --interval=10s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8081), timeout=8).close()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
