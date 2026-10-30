# C4 test dependencies only; D3's resolved ROS/Nav2 image stays the base.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install --no-install-recommends -y python3-pip python3-venv git \
    && python3 -m venv --system-site-packages /opt/c4 \
    && /opt/c4/bin/pip install --no-cache-dir numpy==1.26.4 scipy==1.11.4 \
       fastapi==0.115.6 pydantic==2.10.6 uvicorn==0.34.0 httpx==0.28.1 \
    && rm -rf /var/lib/apt/lists/*
