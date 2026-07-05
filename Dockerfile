FROM python:3.13-slim

WORKDIR /app

COPY archive-requirements.txt ./
RUN pip install --no-cache-dir -r archive-requirements.txt

COPY rt_downloader.py ./

RUN mkdir -p /app/archive

CMD ["python", "rt_downloader.py"]
