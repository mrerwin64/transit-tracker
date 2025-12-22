# Modules
from signal import signal, SIGINT, SIGTERM
from datetime import datetime
import threading
import requests
import pathlib
import json


# Constant defaults
GTFS_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"
GTFS_RT_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile"
GTFS_RT_DYNAMIC_FILES = ["feeds.pb", "trip_updates.pb", "vehicle_positions.pb"]
GTFS_RT_STATIC_FILES = ["vehicle_dictionary.csv"]
ARCHIVE_PATH = "archive/"
LOGFILE_PATH = "downloader.log"
VERBOSE = True
LOG_BUFFER_SIZE = 10
POLLING_INTERVAL = 60


# Functions
log_cache = []
def log(message: str, level="INFO", timestamp=True, console=True, file=True, verbose=False):
    global log_cache

    if verbose and not VERBOSE:
        return

    entry = ""
    if level != "":
        entry += f"[{level}]"
    if timestamp:
        entry += f"[{datetime.now().replace(microsecond=0).isoformat().replace('T', ' ')}]"
    if len(entry) > 0:
        entry += ": "
    entry += message

    if console:
        print(entry)

    if file:
        log_cache.append(entry+"\n")
        if len(log_cache) >= LOG_BUFFER_SIZE or shutting_down:
            with open(LOGFILE_PATH, "a") as file:
                file.writelines(log_cache)
                log_cache = []


shutting_down = False
stop_event = threading.Event()
def shutdown(signum, frame):
    global shutting_down
    shutting_down = True
    stop_event.set()
    log(f"Received signal {signum}, shutting down")


def load_constants():
    global GTFS_URL, GTFS_RT_URL, GTFS_RT_DYNAMIC_FILES, GTFS_RT_STATIC_FILES, ARCHIVE_PATH, LOGFILE_PATH, VERBOSE, LOG_BUFFER_SIZE, POLLING_INTERVAL

    try:
        import downloader_config as cfg
    except ModuleNotFoundError as e:
        return False, e

    keys = [
        "GTFS_URL",
        "GTFS_RT_URL",
        "GTFS_RT_DYNAMIC_FILES",
        "GTFS_RT_STATIC_FILES",
        "ARCHIVE_PATH",
        "LOGFILE_PATH",
        "VERBOSE",
        "LOG_BUFFER_SIZE",
        "POLLING_INTERVAL",
    ]

    changes = 0
    for key in keys:
        if hasattr(cfg, key):
            old = globals()[key]
            new = getattr(cfg, key)
            if new != old:
                globals()[key] = new
                changes += 1

    return True, changes


def get_latest_gtfs_filename():
    try:
        response = requests.head(GTFS_URL, timeout=5)
        content_disposition = response.headers.get('Content-Disposition')
        filename = content_disposition.split()[1][10:-1]
        return True, filename
    except Exception as e:
        return False, e


def download_gtfs_data():
    try:
        response = requests.get(GTFS_URL, timeout=15)
        content_disposition = response.headers.get("Content-Disposition")
        filename = content_disposition.split()[1][10:-1]
        with open(ARCHIVE_PATH+"gtfs/"+filename, "wb") as file:
            file.write(response.content)
        metadata_path = ARCHIVE_PATH+"gtfs/"+filename+".json"
        if not pathlib.Path(metadata_path).is_file():
            create_metadata_file(metadata_path, timestamp=True)
        return True, filename
    except Exception as e:
        return False, e


def download_gtfs_rt_file(remote_name: str, local_name: str, static=False):
    try:
        response = requests.get(GTFS_RT_URL+"?file="+remote_name, timeout=5)
        if static:
            target_path = pathlib.Path(ARCHIVE_PATH+"gtfs-rt/static/"+remote_name+"/")
        else:
            target_path = pathlib.Path(ARCHIVE_PATH+"gtfs-rt/dynamic/"+remote_name+"/")
        previous_files = list(filter(lambda x: x.suffix == "", target_path.iterdir()))
        changed = False
        if len(previous_files) == 0 or max(previous_files, key=str).read_bytes() != response.content:
            changed = True
            if static:
                create_metadata_file(ARCHIVE_PATH+"gtfs-rt/static/"+remote_name+"/"+local_name+".json")
            with (target_path/local_name).open("wb") as new_file:
                new_file.write(response.content)
        return True, changed
    except Exception as e:
        return False, e


def create_metadata_file(path: str, timestamp=False):
    dictionary = {
        "first_valid": None,
        "last_valid": None,
        "record_count": 0
    }
    if timestamp:
        dictionary["timestamp"] = int(datetime.now().timestamp())
    with open(path, "w") as file:
        json.dump(dictionary, file, indent=2)


def update_metadata(filename: str):
    try:
        gtfs_dir = pathlib.Path(ARCHIVE_PATH+"gtfs/")
        static_gtfs_rt_dirs = list(pathlib.Path(ARCHIVE_PATH+"gtfs-rt/"+"static/").iterdir())

        paths = []
        for directory in [gtfs_dir] + static_gtfs_rt_dirs:
            json_files = list(filter(lambda x: x.suffix == ".json", directory.iterdir()))
            latest_file = max(json_files)
            paths.append(latest_file)

        for path in paths:
            with open(path, "r+") as file:
                dictionary = json.load(file)
                if dictionary["first_valid"] is None:
                    dictionary["first_valid"] = filename
                dictionary["last_valid"] = filename
                dictionary["record_count"] += 1

                file.seek(0)
                file.truncate()
                json.dump(dictionary, file, indent=2)

        return True, len(paths)
    except Exception as e:
        return False, e


def prepare_directory_structure():
    archive_path = pathlib.Path(ARCHIVE_PATH)
    gtfs_path = archive_path/"gtfs/"
    gtfs_rt_path = archive_path/"gtfs-rt/"
    gtfs_rt_dynamic_path = archive_path/"gtfs-rt"/"dynamic/"
    gtfs_rt_static_path = archive_path/"gtfs-rt"/"static/"
    gtfs_rt_dynamic_file_paths = [archive_path/"gtfs-rt"/"dynamic"/x for x in GTFS_RT_DYNAMIC_FILES]
    gtfs_rt_static_file_paths = [archive_path/"gtfs-rt"/"static"/x for x in GTFS_RT_STATIC_FILES]
    required_paths = [archive_path, gtfs_path, gtfs_rt_path, gtfs_rt_dynamic_path, gtfs_rt_static_path] + gtfs_rt_dynamic_file_paths + gtfs_rt_static_file_paths

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


def setup_signal_handlers():
    signal(SIGINT, shutdown)
    signal(SIGTERM, shutdown)


def initialize_logs():
    log("", level="", timestamp=False, console=False)
    log("#"*20 + " STARTING DOWNLOADER " + "#"*20, level="", console=False)


def load_configuration():
    if pathlib.Path("downloader_config.py").is_file():
        status = load_constants()
        if status[0]:
            log(f"Successfully loaded config file - {status[1]} parameters modified")
        else:
            log(f"Failed to load config file: {status[1]}", level="WARNING")
    else:
        log("No config file found", level="WARNING")


def initialize_directories():
    status = prepare_directory_structure()
    if status[0]:
        log("Successfully prepared archive directory structure")
    else:
        log(f"Failed to prepare archive directory structure: {status[1]}", level="ERROR")


def check_and_download_gtfs_data():
    status = get_latest_gtfs_filename()
    if not status[0]:
        log(f"Failed to get latest GTFS data filename: {status[1]}", level="WARNING")
        remote_latest = ""
    else:
        remote_latest = status[1]

    gtfs_path = pathlib.Path(ARCHIVE_PATH+"gtfs/")
    gtfs_files = list(filter(lambda x: x.suffix == ".zip", gtfs_path.iterdir()))
    if len(gtfs_files) == 0 or max(gtfs_files, key=str).parts[-1] != remote_latest:
        if len(remote_latest) > 0:
            log("Found new GTFS data")

        status = download_gtfs_data()
        if status[0]:
            log(f"Successfully downloaded GTFS data: {status[1]}")
        else:
            log(f"Failed to download GTFS data: {status[1]}", level="WARNING")
    else:
        log("No new GTFS data available", verbose=True)


def download_gtfs_rt_data():
    local_name = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    # Static files
    for remote_name in GTFS_RT_STATIC_FILES:
        status = download_gtfs_rt_file(remote_name, local_name, static=True)
        if status[0]:
            if status[1]:
                log(f"Successfully downloaded updated static GTFS-RT file - {remote_name}")
            else:
                log(f"Successfully downloaded identical static GTFS-RT file - {remote_name}", verbose=True)
        else:
            log(f"Failed to download static GTFS-RT file {remote_name}: {status[1]}", level="WARNING")

    # Dynamic files
    for remote_name in GTFS_RT_DYNAMIC_FILES:
        status = download_gtfs_rt_file(remote_name, local_name)
        if status[0]:
            if status[1]:
                log(f"Successfully downloaded updated dynamic GTFS-RT file - {remote_name}", verbose=True)
            else:
                log(f"Successfully downloaded identical dynamic GTFS-RT file - {remote_name}")
        else:
            log(f"Failed to download dynamic GTFS-RT file {remote_name}: {status[1]}", level="WARNING")

    # Update GTFS and static GTFS-RT file metadata
    status = update_metadata(local_name)
    if status[0]:
        log(f"Successfully updated metadata for {status[1]} files", verbose=True)
    else:
        log(f"Failed to update metadata: {status[1]}", level="ERROR")


def run_polling_loop():
    while not shutting_down:
        start_time = datetime.now()

        log("#"*10 + " RUNNING POLLING LOOP " + "#"*10, verbose=True)
        check_and_download_gtfs_data()
        download_gtfs_rt_data()

        elapsed = (datetime.now() - start_time).total_seconds()
        stop_event.wait(timeout=max(0.0, POLLING_INTERVAL-elapsed))


def main():
    setup_signal_handlers()
    initialize_logs()
    load_configuration()
    initialize_directories()
    run_polling_loop()
    log("Cleanup complete")


# Entry point
if __name__ == "__main__":
    main()
