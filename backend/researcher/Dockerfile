FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

# Install Node.js
# RUN apt-get update && apt-get install -y \
#     curl \
#     && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
#     && apt-get install -y nodejs \
#     && rm -rf /var/lib/apt/lists/*

# Install Playwright dependencies (system-level dependencies for Chromium)
# RUN npx -y playwright install --with-deps chromium

# ---------- SYSTEM + NODE ----------
    RUN apt-get update && apt-get install -y \
    curl \
    wget \
    ca-certificates \
    gnupg \
    unzip \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxrandr2 \
    libgbm1 \
    libgtk-3-0 \
    libasound2 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxdamage1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    fonts-liberation \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# ---------- NODE ----------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest

# ---------- PLAYWRIGHT MCP (INSTALL AT BUILD TIME) ----------
RUN npm install -g @playwright/mcp@0.0.48

# RUN npx playwright install chromium

ENV PLAYWRIGHT_BROWSERS_PATH=0
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV CHROME_PATH=/usr/bin/chromium

# Install Python package manager
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock /app/

# Install ALL Python dependencies (system-wide)
# RUN uv pip install --system --no-cache .

# Ensure your App Runner Docker build copies the shared database package:
COPY database /app/database
COPY common /app/common
COPY researcher /app/researcher

# Install Python dependencies during build
# uv will automatically install packages for the container's architecture (linux/amd64)
# RUN uv sync --frozen --no-install-project
RUN uv sync --frozen 

# 🔹 NEW: install dependencies listed in researcher/pyproject.toml
# RUN uv pip install --requirement /app/researcher/pyproject.toml

# Copy application code
# COPY *.py ./

# Ensure your App Runner Docker build copies the shared database package:
# COPY common /app/common
# COPY database /app/database
# COPY researcher /app/researcher

# Expose port
EXPOSE 8000

# Run the application (dependencies already installed)
CMD ["uv", "run", "uvicorn", "researcher.server:app", "--host", "0.0.0.0", "--port", "8000"]