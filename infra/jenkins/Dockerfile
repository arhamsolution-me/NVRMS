FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install base dependencies and runtime utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    build-essential \
    git \
    make \
    jq \
    tar \
    unzip \
    ffmpeg \
    shellcheck \
    openjdk-17-jdk-headless \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    golang-go \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js LTS (v22.x)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs

# Install Docker CLI and Docker Compose Plugin
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Install tshark noninteractively
RUN echo "wireshark-common wireshark-common/install-setuid boolean true" | debconf-set-selections \
    && apt-get update \
    && apt-get install -y --no-install-recommends tshark \
    && rm -rf /var/lib/apt/lists/*

# Install Pinned Security Scanners
# 1. Gitleaks v8.30.1
RUN curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz | tar -xz -C /usr/local/bin gitleaks \
    && chmod +x /usr/local/bin/gitleaks

# 2. Trivy v0.76.1
RUN curl -sSL https://github.com/aquasecurity/trivy/releases/download/v0.76.1/trivy_0.76.1_Linux-64bit.tar.gz | tar -xz -C /usr/local/bin trivy \
    && chmod +x /usr/local/bin/trivy

# 3. Hadolint v2.12.0
RUN curl -sSL -o /usr/local/bin/hadolint https://github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64 \
    && chmod +x /usr/local/bin/hadolint

# Setup Python virtual environment and install all pinned security & project dependencies
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN python3 -m venv $VIRTUAL_ENV \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir \
        semgrep==1.90.0 \
        bandit==1.7.10 \
        pip-audit==2.7.3 \
        ruff==0.8.0 \
        mypy==1.13.0 \
        black==24.10.0 \
        pytest==8.3.3 \
        pytest-cov==5.0.0 \
        pytest-asyncio==0.24.0 \
        pydantic==2.9.2 \
        pydantic-settings==2.5.2 \
        fastapi==0.115.0 \
        uvicorn==0.30.6 \
        python-multipart==0.0.9 \
        sqlalchemy==2.0.35 \
        asyncpg==0.30.0 \
        alembic==1.13.3 \
        redis==5.0.8 \
        argon2-cffi==23.1.0 \
        pyjwt==2.9.0 \
        pyotp==2.9.0 \
        email-validator==2.2.0 \
        structlog==24.4.0 \
        httpx==0.27.2 \
        anyio==4.6.0 \
        websockets==13.0.1 \
        cryptography==43.0.1 \
        aiosqlite==0.20.0 \
        fakeredis==2.25.0 \
        faker==30.0.0

# Configure git safe directory
RUN git config --system --add safe.directory '*'

# Create jenkins user for non-root execution
RUN groupadd -g 1000 jenkins \
    && useradd -d /home/jenkins -s /bin/bash -m -u 1000 -g jenkins \
    && usermod -aG sudo jenkins || true

WORKDIR /home/jenkins
CMD ["bash"]
