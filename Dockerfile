FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN addgroup --system flagship && adduser --system --ingroup flagship --home /app flagship
COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY src ./src
ARG FLAGSHIP_EXTRAS="kafka"
RUN python -m pip install --upgrade pip && python -m pip install ".[${FLAGSHIP_EXTRAS}]"
RUN mkdir -p /app/work && chown -R flagship:flagship /app
USER flagship
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"
ENTRYPOINT ["python", "-m", "flagship_lab.cli"]
CMD ["api", "--host", "0.0.0.0", "--port", "8000"]
