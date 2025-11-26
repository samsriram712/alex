FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

# Install Node.js
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright dependencies (system-level dependencies for Chromium)
RUN npx -y playwright install --with-deps chromium

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