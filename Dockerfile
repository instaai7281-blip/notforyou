# Use a maintained base image
FROM python:3.10-slim-bookworm

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Update system & install dependencies with build tools for native C extensions (tgcrypto/cryptg)
RUN apt update && apt upgrade -y && \
    apt install -y \
        git \
        curl \
        python3-pip \
        ffmpeg \
        wget \
        bash \
        neofetch \
        gcc \
        python3-dev \
        build-essential \
        libffi-dev \
        software-properties-common && \
    apt clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .

RUN pip3 install --no-cache-dir wheel setuptools && \
    pip3 install --no-cache-dir -r requirements.txt

# Set working directory
WORKDIR /app

# Copy your app code
COPY . .

# Expose Flask app port
EXPOSE 5000

# Run Flask + Python module
CMD ["python3", "main.py"]
