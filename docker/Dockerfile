FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV WINEPREFIX=/root/.wine
ENV WINEARCH=win64
ENV DISPLAY=:1

# 1. Install prerequisites, WineHQ, Xvfb, x11vnc, noVNC, supervisor, and Python 3.11
RUN dpkg --add-architecture i386 && \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    gnupg2 \
    software-properties-common \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    supervisor \
    git \
    unzip \
    cabextract \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 2. Install WineHQ
RUN mkdir -pm755 /etc/apt/keyrings && \
    wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key && \
    wget -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/ubuntu/dists/jammy/winehq-jammy.sources && \
    apt-get update && \
    apt-get install -y --install-recommends winehq-stable && \
    rm -rf /var/lib/apt/lists/*

# 3. Create app workspace
WORKDIR /app
COPY requirements.txt /app/
RUN python3 -m venv /app/.venv && \
    /app/.venv/bin/pip install --upgrade pip && \
    /app/.venv/bin/pip install -r requirements.txt

# 4. Copy project code and EAs
COPY . /app/

# 5. Copy supervisor configuration
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

# Ports: 6080 for noVNC browser GUI, 8501 for Streamlit
EXPOSE 6080 8501

ENTRYPOINT ["/app/docker/entrypoint.sh"]
