# Modules
from datetime import datetime
import requests
import pathlib
import time


# Constants
GTFS_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"
GTFS_RT_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile"
GTFS_RT_FILES = ["feeds.pb", "trip_updates.pb", "vehicle_dictionary.pb", "vehicle_positions.pb"]
ARCHIVE_PATH = "archive/"
LOGFILE_PATH = "downloader.log"
POLLING_INTERVAL = 45


# Functions
log_cache = []
def log(message: str, timestamp=True, console=True, file=True):
    global log_cache

    if timestamp:
        entry = f"[{datetime.now().replace(microsecond=0).isoformat().replace('T', ' ')}]: {message}"
    else:
        entry = message

    if console:
        print(entry)

    if file:
        log_cache.append(entry+"\n")
        if len(log_cache) >= 10:
            with open(LOGFILE_PATH, "a") as file:
                file.writelines(log_cache)
                log_cache = []


def get_latest_gtfs_filename():
    try:
        response = requests.head(GTFS_URL)
        content_disposition = response.headers.get('Content-Disposition')
        filename = content_disposition.split()[1][10:-1]
        return True, filename
    except Exception as e:
        return False, e


def download_gtfs_data():
    try:
        response = requests.get(GTFS_URL)
        content_disposition = response.headers.get("Content-Disposition")
        filename = content_disposition.split()[1][10:-1]
        with open(ARCHIVE_PATH+"gtfs/"+filename, "wb") as file:
            file.write(response.content)
        return True, filename
    except Exception as e:
        return False, e


def download_gtfs_rt_data():
    local_name = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    changed_files = 0
    try:
        for remote_name in GTFS_RT_FILES:
            response = requests.get(GTFS_RT_URL+"?file="+remote_name)
            target_path = pathlib.Path(ARCHIVE_PATH+"gtfs-rt/"+remote_name+"/")
            previous_files = list(target_path.iterdir())
            if len(previous_files) == 0 or max(previous_files, key=str).read_bytes() != response.content:
                with (target_path / local_name).open("wb") as new_file:
                    new_file.write(response.content)
                    changed_files += 1
        return True, changed_files
    except Exception as e:
        return False, e


def prepare_directory_structure():
    archive_path = pathlib.Path(ARCHIVE_PATH)
    gtfs_path = archive_path/"gtfs/"
    gtfs_rt_path = archive_path/"gtfs-rt/"
    gtfs_rt_file_paths = [archive_path/"gtfs-rt"/x for x in GTFS_RT_FILES]
    required_paths = [archive_path, gtfs_path, gtfs_rt_path] + gtfs_rt_file_paths

    try:
        for path in required_paths:
            if not path.exists():
                path.mkdir()
            elif path.is_file():
                path.unlink()
                path.mkdir()
        return True, None
    except Exception as e:
        return False, e


# Main function
def main():
    log("", timestamp=False, console=False)
    log("#"*15 + " STARTING DOWNLOADER " + "#"*15, console=False)

    # Prepare directory structure
    status = prepare_directory_structure()
    if status[0]:
        log("Successfully prepared archive directory structure")
    else:
        log(f"Failed to prepare archive directory structure: {status[1]}")

    # Main loop
    while True:
        # Check for GTFS updates and download data if needed
        status = get_latest_gtfs_filename()
        if not status[0]:
            log(f"Failed to get latest GTFS data filename: {status[1]}")
            remote_latest = ""
        else:
            remote_latest = status[1]

        gtfs_path = pathlib.Path(ARCHIVE_PATH+"gtfs/")
        gtfs_files = list(gtfs_path.iterdir())
        if len(gtfs_files) == 0 or max(gtfs_files, key=str).parts[-1] != remote_latest:
            log("Found new GTFS data")
            status = download_gtfs_data()
            if status[0]:
                log(f"Successfully downloaded GTFS data: {status[1]}")
            else:
                log(f"Failed to download GTFS data: {status[1]}")

        # Download GTFS-RT data
        status = download_gtfs_rt_data()
        if status[0]:
            log(f"Successfully downloaded GTFS-RT data - {status[1]} files changed")
        else:
            log(f"Failed to download GTFS-RT data: {status[1]}")

        # Wait until it's time to poll the agency again
        time.sleep(POLLING_INTERVAL)


# Entry point
if __name__ == "__main__":
    main()
