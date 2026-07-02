"""Polls ZTM Poznan for GTFS and GTFS-RT data and archives it to disk.

Runs as a long-lived process: periodically checks for a new GTFS static archive,
downloads GTFS-RT snapshots, and tracks per-file metadata (validity range, record
count) for the archive. Configuration can be overridden via an optional
downloader_config.py module.
"""

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
    """Write a log entry to the console and/or logfile.

    Entries are buffered in memory and flushed to LOGFILE_PATH once LOG_BUFFER_SIZE
    entries have accumulated, or immediately once shutdown has been requested.

    Args:
        message: The text to log.
        level: Severity tag prefixed to the entry (e.g. "INFO", "WARNING", "ERROR").
            Pass "" to omit it.
        timestamp: Whether to prefix the entry with the current local time.
        console: Whether to print the entry to stdout.
        file: Whether to buffer the entry for writing to LOGFILE_PATH.
        verbose: If True, the entry is suppressed unless the module-level VERBOSE
            flag is set.
    """
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
                log_cache.clear()


shutting_down = False
stop_event = threading.Event()
def shutdown(signum, frame):
    """Signal handler that requests a graceful shutdown.

    Sets the shutting_down flag and stop_event so in-progress waits/retries exit
    early and run_polling_loop() stops after its current iteration.

    Args:
        signum: The signal number that triggered the handler (e.g. SIGINT, SIGTERM).
        frame: The current stack frame; unused, required by the signal handler
            signature.
    """
    global shutting_down
    shutting_down = True
    stop_event.set()
    log(f"Received signal {signum}, shutting down")


def load_constants():
    """Reload module constants from downloader_config.py, if present.

    Only keys already defined as module-level constants are considered; each is
    overwritten in place when its value in downloader_config differs from the
    current one.

    Returns:
        Tuple of (success, detail):
            - (True, changes) where changes is the number of constants that were
              updated.
            - (False, exception) if downloader_config.py could not be imported.
    """
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


def get_latest_gtfs_filename(is_retry=False):
    """Fetch the filename of the current GTFS archive without downloading it.

    Issues a HEAD request and reads the filename from the Content-Disposition
    header. On failure, retries once after a 5 second delay.

    Args:
        is_retry: Internal flag marking this call as the single automatic retry;
            callers should not set this themselves.

    Returns:
        Tuple of (success, detail):
            - (True, filename) on success.
            - (False, exception) if the request and its retry both failed.
    """
    try:
        response = requests.head(GTFS_URL, timeout=5)
        content_disposition = response.headers.get('Content-Disposition')
        filename = content_disposition.split()[1][10:-1]

        if is_retry:
            log("Retry successful")
        return True, filename
    except Exception as e:
        if not is_retry:
            log("Failed to get latest GTFS archive filename, retrying in 5 seconds", level="WARNING")
            stop_event.wait(timeout=5)
            return get_latest_gtfs_filename(is_retry=True)
        else:
            return False, e


def download_gtfs_archive(is_retry=False):
    """Download the current GTFS archive and save it under ARCHIVE_PATH.

    Creates an accompanying metadata JSON file for the archive if one doesn't
    already exist. On failure, retries once after a 10 second delay.

    Args:
        is_retry: Internal flag marking this call as the single automatic retry;
            callers should not set this themselves.

    Returns:
        Tuple of (success, detail):
            - (True, filename) on success.
            - (False, exception) if the download and its retry both failed.
    """
    try:
        response = requests.get(GTFS_URL, timeout=15)
        content_disposition = response.headers.get("Content-Disposition")
        filename = content_disposition.split()[1][10:-1]
        with open(ARCHIVE_PATH+"gtfs/"+filename, "wb") as file:
            file.write(response.content)
        metadata_path = ARCHIVE_PATH+"gtfs/"+filename+".json"
        if not pathlib.Path(metadata_path).is_file():
            create_metadata_file(metadata_path, timestamp=True)

        if is_retry:
            log("Retry successful")
        return True, filename
    except Exception as e:
        if not is_retry:
            log("Failed to download GTFS data, retrying in 10 seconds", level="WARNING")
            stop_event.wait(timeout=10)
            return download_gtfs_archive(is_retry=True)
        else:
            return False, e


def download_gtfs_rt_file(remote_name: str, local_name: str, static=False, is_retry=False):
    """Download a single GTFS-RT file and save it if its contents changed.

    Compares the downloaded content against the most recently saved file of the
    same kind; if identical, the file is not rewritten. For static files, also
    creates a metadata JSON file alongside the first saved copy. On failure,
    retries once after a 5 second delay.

    Args:
        remote_name: Name of the file as exposed by GTFS_RT_URL (e.g.
            "trip_updates.pb").
        local_name: Filename to save the downloaded content under.
        static: Whether the file is one of GTFS_RT_STATIC_FILES (saved under
            gtfs-rt/static/) rather than GTFS_RT_DYNAMIC_FILES (gtfs-rt/dynamic/).
        is_retry: Internal flag marking this call as the single automatic retry;
            callers should not set this themselves.

    Returns:
        Tuple of (success, detail):
            - (True, changed) where changed indicates whether the content
              differed from the previously saved file.
            - (False, exception) if the download and its retry both failed.
    """
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

        if is_retry:
            log("Retry successful")
        return True, changed
    except Exception as e:
        if not is_retry:
            log(f"Failed to download GTFS-RT file {remote_name}, retrying in 5 seconds", level="WARNING")
            stop_event.wait(timeout=5)
            return download_gtfs_rt_file(remote_name, local_name, static, is_retry=True)
        else:
            return False, e


def create_metadata_file(path: str, timestamp=False):
    """Create a fresh metadata JSON file for an archived GTFS/GTFS-RT file.

    Args:
        path: Path to write the metadata file to.
        timestamp: Whether to record the current time as a "timestamp" field.
            Used for GTFS archives, which have no filename-derived timestamp
            (unlike GTFS-RT files, whose local_name already encodes one).
    """
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
    """Record a newly downloaded GTFS-RT filename in the latest metadata file of each tracked archive.

    Updates the most recent metadata JSON file for the current GTFS archive and
    for each static GTFS-RT file, setting first_valid on first use, last_valid to
    filename, and incrementing record_count.

    Args:
        filename: Local filename (timestamp) of the GTFS-RT snapshot just downloaded.

    Returns:
        Tuple of (success, detail):
            - (True, count) where count is the number of metadata files updated.
            - (False, exception) if updating any metadata file failed.
    """
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
    """Create the archive directory tree, removing any files that occupy expected directory paths.

    Ensures ARCHIVE_PATH and its gtfs/, gtfs-rt/dynamic/, and gtfs-rt/static/
    subdirectories exist, along with a subdirectory for each configured GTFS-RT
    file.

    Returns:
        Tuple of (success, detail):
            - (True, None) on success.
            - (False, exception) if directory creation failed.
    """
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
    """Register shutdown() as the handler for SIGINT and SIGTERM."""
    signal(SIGINT, shutdown)
    signal(SIGTERM, shutdown)


def initialize_logs():
    """Write a blank line and a startup banner to the logfile, marking a new run."""
    log("", level="", timestamp=False, console=False)
    log("#"*20 + " STARTING DOWNLOADER " + "#"*20, level="", console=False)


def load_configuration():
    """Load downloader_config.py if present and log the outcome.

    Applies overrides via load_constants() and logs how many parameters changed,
    or a warning if no config file was found or loading failed.
    """
    if pathlib.Path("downloader_config.py").is_file():
        status = load_constants()
        if status[0]:
            log(f"Successfully loaded config file - {status[1]} parameters modified")
        else:
            log(f"Failed to load config file: {status[1]}", level="WARNING")
    else:
        log("No config file found", level="WARNING")


def initialize_directories():
    """Prepare the archive directory structure and log the outcome."""
    status = prepare_directory_structure()
    if status[0]:
        log("Successfully prepared archive directory structure")
    else:
        log(f"Failed to prepare archive directory structure: {status[1]}", level="ERROR")


def check_and_download_gtfs_data():
    """Download a new GTFS archive if the remote filename differs from the latest local copy.

    Falls back to always attempting a download if the remote filename couldn't
    be determined.
    """
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

        status = download_gtfs_archive()
        if status[0]:
            log(f"Successfully downloaded GTFS data: {status[1]}")
        else:
            log(f"Failed to download GTFS data: {status[1]}", level="WARNING")
    else:
        log("No new GTFS data available", verbose=True)


def download_gtfs_rt_data():
    """Download one GTFS-RT snapshot: all static files, then all dynamic files.

    All files downloaded in this call share the same local_name timestamp. After
    downloading, updates the metadata for the current GTFS archive and each
    static GTFS-RT file via update_metadata().
    """
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
    """Repeatedly check for new GTFS data and download GTFS-RT snapshots until shutdown.

    Each iteration runs check_and_download_gtfs_data() and download_gtfs_rt_data(),
    then sleeps for the remainder of POLLING_INTERVAL (or not at all if the
    iteration took longer than that).
    """
    while not shutting_down:
        start_time = datetime.now()

        log("#"*10 + " RUNNING POLLING LOOP " + "#"*10, verbose=True)
        check_and_download_gtfs_data()
        download_gtfs_rt_data()

        elapsed = (datetime.now() - start_time).total_seconds()
        stop_event.wait(timeout=max(0.0, POLLING_INTERVAL-elapsed))


def main():
    """Entry point: set up signal handling, logging, config and directories, then poll until shutdown."""
    setup_signal_handlers()
    initialize_logs()
    load_configuration()
    initialize_directories()
    run_polling_loop()
    log("Cleanup complete")


# Entry point
if __name__ == "__main__":
    main()
