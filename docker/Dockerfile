FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY context_layer /app/context_layer
COPY context_manager /app/context_manager
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TIKTOKEN_CACHE_DIR=/token-cache CONTEXT_EXTENSION_DIR=/extensions CONTEXT_MANAGER_HOME=/data CONTEXT_MANAGER_BRIDGE=/bridge HF_HUB_OFFLINE=1
USER 1000:1000
ENTRYPOINT ["python", "-m", "context_manager"]
