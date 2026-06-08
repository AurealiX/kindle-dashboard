FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    tini \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY . /app

ENV KINDLE_CONFIG=/config/config.yaml \
    KINDLE_DATA_DIR=/data \
    CHROME_BIN=/usr/bin/chromium \
    TZ=Asia/Shanghai

EXPOSE 8585

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "server.run"]
