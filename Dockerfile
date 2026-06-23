# Use a slim Python base
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Taipei
WORKDIR /app

# Install apt deps required by some Python packages and optionally Playwright
# Include libxml2-dev/libxslt1-dev for lxml wheel/build support
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    wget \
    git \
    gnupg \
    libxml2-dev \
    libxslt1-dev \
    libssl-dev \
    pkg-config \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libgbm1 \
    libpangocairo-1.0-0 \
    fonts-liberation \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage layer cache
COPY requirements.txt /app/requirements.txt

# Upgrade pip and install wheels first
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

# Copy project files
COPY . /app

# Ensure results dir exists and is writable
RUN mkdir -p /app/results && chmod -R 0777 /app/results

# Optional: install Playwright browsers if your scrapers actually use Playwright.
# This step can be slow and increases image size. Enable only if needed.
ARG INSTALL_PLAYWRIGHT="true"
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ] ; then \
      python -m playwright install --with-deps ; \
    else \
      echo "Skipping playwright browser install" ; \
    fi

# Entrypoint / default command
CMD ["python", "main.py"]
