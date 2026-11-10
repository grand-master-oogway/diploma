# Image with the firms_ua package; the entry point is the CLI, for example:
#   docker run --rm <image> smoke
#   docker run --rm <image> ingest --source VIIRS_NOAA20_SP --date 2025-07-15
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .

RUN useradd --create-home app
USER app

ENTRYPOINT ["firms-ua"]
