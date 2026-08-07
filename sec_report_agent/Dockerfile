# V2.2 生产镜像 — 多阶段构建 + 非 root + 健康检查
FROM python:3.10-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 依赖层（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 代码层
COPY . .

# 非 root 运行（uid 10001）+ 数据目录
RUN useradd -m -u 10001 appuser \
    && mkdir -p /app/reports /app/vector_data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
