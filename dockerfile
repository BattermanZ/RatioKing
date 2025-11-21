# syntax=docker/dockerfile:1

#################################
# Stage 1: build pure-Python wheels
#################################
FROM python:3.13.5-alpine3.22 AS build

# No .pyc clutter, unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Amsterdam

WORKDIR /app

# Copy dependency list
COPY requirements.txt .

# Build wheels into /wheels
RUN pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

#################################
# Stage 2: runtime
#################################
FROM python:3.13.5-alpine3.22

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install only prebuilt wheels (no compilers needed)
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels \
        feedparser requests python-dotenv

# Copy application code
COPY ratioking.py .

# Validate syntax on startup
HEALTHCHECK CMD python -m py_compile ratioking.py

# Default command will pick up your host-mounted .env via python-dotenv
CMD ["python", "ratioking.py"]
