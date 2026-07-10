# Base image and environment
FROM python:3.13-slim
ENV TZ=Europe/Warsaw \
    PYTHONUNBUFFERED=1
WORKDIR /app


# Linux dependencies (time zones and curl for downloading scheduler)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata curl && rm -rf /var/lib/apt/lists/
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.47/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=712d2ece75da6f6e530192a151488578153e4e96 \
    SUPERCRONIC=supercronic-linux-amd64
RUN curl -fsSLO "$SUPERCRONIC_URL" \
 && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
 && chmod +x "$SUPERCRONIC" \
 && mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" \
 && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic


# Python dependencies
COPY archive-requirements.txt ./
RUN pip install --no-cache-dir -r archive-requirements.txt


# Application
COPY rt_downloader.py ./
COPY downloader_docker_config.py ./downloader_config.py
COPY gtfs_syncer.py ./
COPY syncer_docker_config.py ./syncer_config.py


# Scheduling and entrypoint
COPY syncer_crontab ./
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
