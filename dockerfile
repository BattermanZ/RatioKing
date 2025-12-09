# syntax=docker/dockerfile:1

#################################
# Stage 1: build dependencies
#################################
FROM python:3.11-slim-bookworm AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Vendor dependencies into /opt/ratioking-deps (no pip needed later)
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --no-compile --target /opt/ratioking-deps -r requirements.txt

# Keep zoneinfo for TZ support
COPY ratioking.py .

#################################
# Stage 2: distroless runtime
#################################
FROM gcr.io/distroless/python3-debian12:nonroot

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC \
    PYTHONPATH=/opt/ratioking-deps

WORKDIR /app

COPY --from=build /usr/share/zoneinfo /usr/share/zoneinfo
COPY --from=build /etc/localtime /etc/localtime
COPY --from=build /opt/ratioking-deps /opt/ratioking-deps
COPY ratioking.py .

HEALTHCHECK CMD ["/usr/bin/python3", "-m", "py_compile", "/app/ratioking.py"]

# distroless already sets the entrypoint to python3; pass only the script
CMD ["/app/ratioking.py"]
