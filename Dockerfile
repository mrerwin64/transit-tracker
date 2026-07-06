FROM python:3.13-slim

ENV TZ=Europe/Warsaw
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/

WORKDIR /app

COPY archive-requirements.txt ./
RUN pip install --no-cache-dir -r archive-requirements.txt

COPY rt_downloader.py ./
COPY downloader_docker_config.py ./downloader_config.py

RUN mkdir -p /app/archive

CMD ["python", "rt_downloader.py"]
