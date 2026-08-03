# ==========================================
# Stage 1: Build & Dependency Gathering
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /workspace

# Install system compilation tools needed for certain Python binary wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements into a isolated local deployment directory
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ==========================================
# Stage 2: Final Production Runtime Environment
# ==========================================
FROM python:3.11-slim AS runner

# Optimize Python runtime engine inside Docker wrappers
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH=/root/.local/bin:$PATH

WORKDIR /workspace

# Install lightweight runtime dependencies (like curl for container health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the compiled Python site-packages from the builder stage
COPY --from=builder /root/.local /root/.local
# Copy the rest of your application code into the working space
COPY . .

# Expose port 8000 matching your cloud docker-compose setup
EXPOSE 8000

# Execute the FastAPI server using Uvicorn bound to all network interfaces
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
