"""Polls ZTM Poznan for GTFS-RT data and archives it to disk.

Runs as a long-lived process: periodically downloads GTFS-RT snapshots.
Configuration can be overridden via an optional downloader_config.py module.
"""

# Modules
from signal import signal, SIGINT, SIGTERM
from datetime import datetime
from types import FrameType
import threading
import requests
import pathlib


# Constant defaults
GTFS_RT_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile"
GTFS_RT_DYNAMIC_FILES = ["feeds.pb", "trip_updates.pb", "vehicle_positions.pb"]
GTFS_RT_STATIC_FILES = ["vehicle_dictionary.csv"]
ARCHIVE_PATH = "archive/gtfs-rt/"
LOGFILE_PATH = "downloader.log"
VERBOSE = True
LOG_BUFFER_SIZE = 10
POLLING_INTERVAL = 60


# Functions
def main() -> None:
    """Entry point: set up signal handling, logging, config and directories, then poll until shutdown."""
    setup_signal_handlers()
    initialize_logs()
    load_configuration()
    initialize_directories()
    run_polling_loop()
    log("Cleanup complete")


#noinspection DuplicatedCode
def setup_signal_handlers() -> None:
    """Register shutdown() as the handler for SIGINT and SIGTERM."""
    signal(SIGINT, shutdown)
    signal(SIGTERM, shutdown)


shutting_down = False
stop_event = threading.Event()
def shutdown(signum: int, _frame: FrameType | None) -> None:
    """Signal handler that requests a graceful shutdown.

    Sets the shutting_down flag and stop_event so in-progress waits/retries exit
    early and run_polling_loop() stops after its current iteration.

    Args:
        signum: The signal number that triggered the handler (e.g. SIGINT, SIGTERM).
        _frame: The current stack frame; unused, required by the signal handler
            signature.
    """
    global shutting_down
    shutting_down = True
    stop_event.set()
    log(f"Received signal {signum}, shutting down")


def initialize_logs() -> None:
    """Write a blank line and a startup banner to the logfile, marking a new run."""
    log("", level="", timestamp=False, console=False)
    log("#"*20 + " STARTING DOWNLOADER " + "#"*20, level="", console=False)


def load_configuration() -> None:
    """Load downloader_config.py if present and log the outcome.

    Applies overrides via load_constants() and logs how many parameters changed,
    or a warning if no config file was found or loading failed.
    """
    if pathlib.Path("downloader_config.py").is_file():
        status = load_constants()
        if status[0]:
            log(f"Successfully loaded config file - {status[1]} parameters modified")
        else:
            log(f"Failed to load config file: {status[1]}", level="ERROR")
    else:
        log("No config file found", level="WARNING")


def load_constants() -> tuple[bool, int | ModuleNotFoundError]:
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
    global GTFS_RT_URL, GTFS_RT_DYNAMIC_FILES, GTFS_RT_STATIC_FILES, ARCHIVE_PATH, LOGFILE_PATH, VERBOSE, LOG_BUFFER_SIZE, POLLING_INTERVAL

    try:
        # noinspection PyUnresolvedReferences
        import downloader_config as cfg
    except ModuleNotFoundError as e:
        return False, e

    keys = [
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


def initialize_directories() -> None:
    """Prepare the archive directory structure and log the outcome."""
    status = prepare_directory_structure()
    if status[0]:
        log("Successfully prepared archive directory structure")
    else:
        log(f"Failed to prepare archive directory structure: {status[1]}", level="ERROR")


def prepare_directory_structure() -> tuple[bool, Exception | None]:
    """Create the archive directory tree, removing any files that occupy expected directory paths.

    Ensures ARCHIVE_PATH (and any missing parent directories) and its
    dynamic/ and static/ subdirectories exist, along with a subdirectory
    for each configured GTFS-RT file.

    Returns:
        Tuple of (success, detail):
            - (True, None) on success.
            - (False, exception) if directory creation failed.
    """
    archive_path = pathlib.Path(ARCHIVE_PATH)
    gtfs_rt_dynamic_path = archive_path/"dynamic/"
    gtfs_rt_static_path = archive_path/"static/"
    gtfs_rt_dynamic_file_paths = [archive_path/"dynamic"/x for x in GTFS_RT_DYNAMIC_FILES]
    gtfs_rt_static_file_paths = [archive_path/"static"/x for x in GTFS_RT_STATIC_FILES]
    required_paths = [archive_path, gtfs_rt_dynamic_path, gtfs_rt_static_path] + gtfs_rt_dynamic_file_paths + gtfs_rt_static_file_paths

    try:
        for path in required_paths:
            if path.is_file():
                path.unlink()
            path.mkdir(parents=True, exist_ok=True)
        return True, None
    except Exception as e:
        return False, e


def run_polling_loop() -> None:
    """Repeatedly download GTFS-RT snapshots until shutdown.

    Each iteration runs download_gtfs_rt_data(), then sleeps for the remainder
    of POLLING_INTERVAL (or not at all if the iteration took longer than that).
    """
    while not shutting_down:
        start_time = datetime.now()

        log("#"*10 + " RUNNING POLLING LOOP " + "#"*10, verbose=True)
        download_gtfs_rt_data()

        elapsed = (datetime.now() - start_time).total_seconds()
        stop_event.wait(timeout=max(0.0, POLLING_INTERVAL-elapsed))


def download_gtfs_rt_data() -> None:
    """Download one GTFS-RT snapshot: all static files, then all dynamic files.

    All files downloaded in this call share the same local_name timestamp.
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


def download_gtfs_rt_file(remote_name: str, local_name: str, static: bool = False, is_retry: bool = False) -> tuple[bool, bool | Exception]:
    """Download a single GTFS-RT file and save it if its contents changed.

    Compares the downloaded content against the most recently saved file of the
    same kind; if identical, the file is not rewritten. On failure, retries once
    after a 5-second delay.

    Args:
        remote_name: Name of the file as exposed by GTFS_RT_URL (e.g.
            "trip_updates.pb").
        local_name: Filename to save the downloaded content under.
        static: Whether the file is one of GTFS_RT_STATIC_FILES (saved under
            static/) rather than GTFS_RT_DYNAMIC_FILES (dynamic/).
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
            target_path = pathlib.Path(ARCHIVE_PATH)/"static"/remote_name
        else:
            target_path = pathlib.Path(ARCHIVE_PATH)/"dynamic"/remote_name
        previous_files = list(target_path.iterdir())
        changed = False
        if len(previous_files) == 0 or max(previous_files, key=str).read_bytes() != response.content:
            changed = True
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


log_cache = []
def log(message: str, level: str = "INFO", timestamp: bool = True, console: bool = True, file: bool = True, verbose: bool = False) -> None:
    """Write a log entry to the console and/or logfile.

    Entries are buffered in memory and flushed to LOGFILE_PATH once LOG_BUFFER_SIZE
    entries have accumulated, or immediately once shutdown has been requested.

    Args:
        message: The text to log.
        level: Severity tag prefixed to the entry (e.g. "INFO", "WARNING", "ERROR").
            Pass "" to omit it.
        timestamp: Whether to prefix the entry with the current local time.
        console: Whether to print the entry to stdout.
        file: Whether to write the entry to LOGFILE_PATH.
        verbose: If True, the entry is suppressed unless the module-level VERBOSE
            flag is set.
    """
    global log_cache

    if verbose and not VERBOSE:
        return

    #noinspection DuplicatedCode
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
            with open(LOGFILE_PATH, "a") as f:
                f.writelines(log_cache)
                log_cache.clear()


# Entry point
if __name__ == "__main__":
    main()
