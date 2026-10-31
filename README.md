# transit-tracker

Archives public transport data from ZTM Poznań. ZTM publishes timetables as
[GTFS](https://gtfs.org/schedule/) files and live vehicle data as [GTFS-RT](https://gtfs.org/realtime/)
feeds, but keeps no history. transit-tracker downloads both continuously to build a dataset for
analysing delays later.

**Status:** the archiving part is finished and runs in Docker. The analysis part is at an early stage:
there are helpers for reading the data and a first delay calculation, but no real analysis yet.

## Components

| File | What it does |
|---|---|
| [`rt_downloader.py`](rt_downloader.py) | Long-running process that downloads the GTFS-RT feeds (vehicle positions, trip updates and the combined feed) every 60 seconds and stores timestamped snapshots |
| [`gtfs_syncer.py`](gtfs_syncer.py) | Daily job that keeps a local archive of GTFS timetables in sync with ZTM's file listing: downloads new files, updates changed ones and retires removed ones, tracked in a JSON manifest |
| [`reader.py`](reader.py) | *(early)* Helpers that read GTFS archives and GTFS-RT protobuf files into Python structures |
| [`analyzer.py`](analyzer.py) | *(early)* A first attempt at matching snapshots with timetables and pulling out per-stop delays |

Both archivers handle network errors with timeouts and retries, log to a file, can be configured with an
optional `*_config.py` module, and shut down cleanly on `SIGINT`/`SIGTERM`.

## Running with Docker

The archivers run together in one container: `rt_downloader.py` in the background and `gtfs_syncer.py`
every night at 3:00 through [supercronic](https://github.com/aptible/supercronic). The data and logs go to
`/app/mount`.

```bash
docker build -t transit-archiver .
docker run -d --restart unless-stopped -v /path/to/data:/app/mount transit-archiver
```

[`docker_push.ps1`](docker_push.ps1) bumps the version in `docker.version`, builds the image and pushes it
to my home server's registry.

## Running locally

Requires Python 3.10+.

```bash
pip install -r archive-requirements.txt
python rt_downloader.py     # archive GTFS-RT, runs until stopped
python gtfs_syncer.py       # sync GTFS timetables once
```

`reader.py` and `analyzer.py` also need `pip install -r analyze-requirements.txt`.
