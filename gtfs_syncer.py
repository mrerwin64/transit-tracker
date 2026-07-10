# Modules
from datetime import datetime
import requests
import pathlib
import zipfile
import shutil
import json
import time
import re
import io


# Constant defaults
GTFS_LIST_URL = "https://www.ztm.poznan.pl/otwarte-dane/gtfsfiles/"
GTFS_DOWNLOAD_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile/"
LOGFILE_PATH = "syncer.log"
ARCHIVE_PATH = "archive/gtfs/"
REQUEST_DELAY = 0.5


# Functions
error_logged = False
def main() -> None:
    """Entry point: verify the manifest, classify files against remote, then sync and log the results."""
    try:
        initialize_logs()
        log("#"*5 + " PREPARATION " + "#"*5, level="")

        initialize_archive()
        log("On-disk archive is ready")
        verify_manifest()
        log("Manifest matches state on disk")

        local_files = list_local_files()
        log(f"Found {len(local_files)} local files")
        remote_files = list_remote_files()
        log(f"Found {len(remote_files)} remote files")

        mismatches = []
        local_only = []
        remote_only = set(remote_files.keys())
        for filename, filedata in local_files.items():
            remote_only.discard(filename)
            if filename in remote_files:
                if filedata != remote_files[filename]:
                    mismatches.append(filename)
            else:
                local_only.append(filename)

        log("#"*5 + " DIFFERENCES TO REMOTE " + "#"*5, level="")
        log(f"{len(local_files)-len(local_only)-len(mismatches)} files are identical locally and remotely")
        log(f"{len(local_only)} files exist only locally ({', '.join(local_only)})")
        log(f"{len(remote_only)} files exist only remotely ({', '.join(sorted(remote_only))})")
        log(f"{len(mismatches)} files differ between local and remote ({', '.join(mismatches)})")

        log("#"*5 + " CHANGES MADE " + "#"*5, level="")
        for filename in remote_only:
            download_gtfs_file(filename, remote_files[filename]["modified"], remote_files[filename]["size"])
            log(f"Downloaded missing {filename} file from remote")
        for filename in mismatches:
            update_gtfs_file(filename, remote_files[filename]["modified"], remote_files[filename]["size"])
            log(f"Updated changed {filename} file to match remote")
        for filename in local_only:
            retire_gtfs_file(filename)
            log(f"Retired {filename} file which went missing from remote")

        log("#"*5 + " SUMMARY " + "#"*5, level="")
        log(f"Sync over successfully with {len(local_only)+len(remote_only)+len(mismatches)} file changes")
    except Exception as e:
        if not error_logged:
            log(f"Unexpected error occurred: {e}", level="ERROR")
        raise e


def initialize_logs() -> None:
    """Write a blank line and a startup banner to the logfile, marking a new run."""
    log("", level="", timestamp=False, console=False)
    log("#"*20 + " STARTING GTFS SYNC " + "#"*20, level="", console=False)


def initialize_archive() -> None:
    """Ensure the archive directory and manifest.json exist, creating them if not.

    If ARCHIVE_PATH is occupied by a file, it's replaced with a directory. If
    manifest.json is occupied by a directory, it's replaced with an empty
    manifest file.

    Raises:
        Exception: Whatever the underlying filesystem failure was, re-raised
            after logging.
    """
    global error_logged

    archive_path = pathlib.Path(ARCHIVE_PATH)
    manifest_path = archive_path/"manifest.json"

    try:
        if archive_path.is_file():
            archive_path.unlink()
        archive_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log(f"Failed to create archive path ({e})", level="ERROR")
        error_logged = True
        raise e

    try:
        if not manifest_path.is_file():
            if manifest_path.is_dir():
                shutil.rmtree(manifest_path)
            with manifest_path.open("w") as f:
                json.dump({}, f)
    except Exception as e:
        log(f"Failed to create manifest file ({e})", level="ERROR")
        error_logged = True
        raise e


def verify_manifest() -> None:
    """Check that manifest.json and the archive directory agree on which files exist.

    Counts files present on disk but missing from the manifest, and manifest
    entries with no corresponding file on disk. Logs and raises if any
    discrepancy is found.

    Raises:
        Exception: "ManifestError" if disk contents and the manifest disagree.
    """
    errors = -1
    manifest_files = set(load_manifest().keys())
    disk_files = pathlib.Path(ARCHIVE_PATH).iterdir()

    for disk in [x.name for x in disk_files]:
        if disk in manifest_files:
            manifest_files.remove(disk)
        else:
            errors += 1
    errors += len(manifest_files)

    if errors != 0:
        log("Manifest doesn't match state on disk", level="ERROR")
        global error_logged
        error_logged = True
        raise Exception("ManifestError")


def list_local_files(old: bool=False) -> dict[str, dict[str, str]]:
    """Return the manifest's known files, keyed by filename.

    Args:
        old: If False (default), entries whose filename ends in ".old" (retired
            archives) are excluded, leaving only the live/current files.

    Returns:
        Dict mapping each filename to its {"size": str, "modified": str} entry.
    """
    files = load_manifest()

    if not old:
        for filename in list(files.keys()):
            if filename[-4:] == ".old":
                del files[filename]

    return files


def list_remote_files() -> dict[str, dict[str, str]]:
    """Fetch and parse the table of available GTFS files from ZTM's open data page.

    Logs and raises if the page can't be fetched, or if it can be fetched but
    no filename rows are found (more likely a scrape/page-structure failure
    than ZTM genuinely listing zero files).

    Returns:
        Dict mapping each filename to its {"size": str, "modified": str} entry.

    Raises:
        requests.exceptions.RequestException: If the page request fails.
        Exception: "NoRemoteFiles" if zero files were parsed from the page.
    """
    global error_logged
    try:
        response = requests.get(GTFS_LIST_URL, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log(f"Failed to fetch remote file list ({e})", level="ERROR")
        error_logged = True
        raise e

    html_text = response.text
    rows = re.findall(r"<td>(\d{8}_\d{8}\.zip)</td><td>([^<]+)</td><td>([^<]+)</td>", html_text)
    files = {}
    for filename, size, modified in rows:
        files[filename] = {
            "size": size.strip(),
            "modified": datetime.strptime(modified.strip(), "%d.%m.%Y, %H:%M:%S").isoformat(),
        }

    if len(files) == 0:
        log("Remote fetch failure - no files listed", level="ERROR")
        error_logged = True
        raise Exception("NoRemoteFiles")
    return files


def update_gtfs_file(filename: str, modified: str, size: str) -> None:
    """Replace a locally-outdated GTFS file with the current remote version.

    Retires the existing file (freeing up its filename) before downloading the
    new content under that same name.

    Args:
        filename: Name of the GTFS archive to update.
        modified: Remote "modified" timestamp to record in the manifest.
        size: Remote size string to record in the manifest.
    """
    retire_gtfs_file(filename)
    download_gtfs_file(filename, modified, size)


def retire_gtfs_file(filename: str) -> None:
    """Rename a file to mark it as no longer current, cascading .old suffixes as needed.

    If the target ".old" name is already occupied, that file is retired first
    (recursively), so existing history is pushed down a level (e.g. "foo.zip.old"
    becomes "foo.zip.old.old") rather than being overwritten. The manifest is
    updated to match.

    Args:
        filename: Name of the file to retire.
    """
    # Make sure the new filename is unoccupied
    new_name = filename+".old"
    if (pathlib.Path(ARCHIVE_PATH)/new_name).exists():
        retire_gtfs_file(new_name)
    # Rename the file
    try:
        file = pathlib.Path(ARCHIVE_PATH)/filename
        file.rename(file.parent/new_name)
    except Exception as e:
        log(f"Filesystem error while renaming {filename} to {new_name} ({e})", level="ERROR")
        global error_logged
        error_logged = True
        raise e
    # Update the manifest
    rename_manifest_entry(filename, new_name)


def download_gtfs_file(filename: str, modified: str, size: str) -> None:
    """Download a GTFS archive, verify it, save it to disk, and record it in the manifest.

    Logs and raises if the download fails, or if the downloaded content is not
    an intact zip archive (checked via zipfile.testzip()).

    Args:
        filename: Name of the GTFS archive to download.
        modified: Remote "modified" timestamp to record in the manifest.
        size: Remote size string to record in the manifest.

    Raises:
        requests.exceptions.RequestException: If the download fails.
        Exception: "CorruptedGtfs" if the downloaded content isn't a valid zip.
    """
    global error_logged
    # Fetch the file
    try:
        response = requests.get(GTFS_DOWNLOAD_URL, params={"file": filename}, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log(f"Failed to download GTFS file {filename} ({e})", level="ERROR")
        error_logged = True
        raise e
    # Test if it's an uncorrupted zip archive
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                log("Downloaded malformed GTFS file - not saved to disk", level="ERROR")
                error_logged = True
                raise Exception("CorruptedGtfs")
    except zipfile.BadZipFile:
        log("Downloaded malformed GTFS file - not saved to disk", level="ERROR")
        error_logged = True
        raise Exception("CorruptedGtfs")
    # Save it
    try:
        file_path = pathlib.Path(ARCHIVE_PATH)/filename
        file_path.write_bytes(response.content)
    except Exception as e:
        log(f"Filesystem error while saving file {filename} ({e})", level="ERROR")
        error_logged = True
        raise e
    # Update the manifest
    add_manifest_entry(filename, modified, size)
    # Request delay
    time.sleep(REQUEST_DELAY)


def rename_manifest_entry(old_filename: str, new_filename: str) -> None:
    """Rename a manifest entry in place, keeping its {size, modified} data.

    Args:
        old_filename: Existing manifest key to rename.
        new_filename: New key to move the entry's data under.
    """
    manifest = load_manifest()
    manifest[new_filename] = manifest.pop(old_filename)
    save_manifest(manifest)


def add_manifest_entry(filename: str, modified: str, size: str) -> None:
    """Add or overwrite a manifest entry with the given metadata.

    Args:
        filename: Manifest key to write.
        modified: Remote "modified" timestamp to record.
        size: Remote size string to record.
    """
    manifest = load_manifest()
    manifest[filename] = {"modified": modified, "size": size}
    save_manifest(manifest)


def load_manifest() -> dict[str, dict[str, str]]:
    """Read and parse manifest.json.

    Returns:
        Dict mapping each filename to its {"size": str, "modified": str} entry.

    Raises:
        Exception: Whatever the underlying read/parse failure was, re-raised
            after logging.
    """
    manifest_path = pathlib.Path(ARCHIVE_PATH)/"manifest.json"
    try:
        with manifest_path.open() as f:
            return json.load(f)
    except Exception as e:
        log(f"Failed to read manifest file ({e})", level="ERROR")
        global error_logged
        error_logged = True
        raise e


def save_manifest(content: dict[str, dict[str, str]]) -> None:
    """Write manifest.json atomically.

    Writes to a temporary file first, then replaces manifest.json with it, so a
    failure partway through never leaves the real manifest truncated or corrupt.

    Args:
        content: Full manifest dict to write, replacing the existing file.

    Raises:
        Exception: Whatever the underlying write/replace failure was, re-raised
            after logging.
    """
    global error_logged
    manifest_path = pathlib.Path(ARCHIVE_PATH)/"manifest.json"
    manifest_temp_path = pathlib.Path(ARCHIVE_PATH)/"manifest.temp"
    try:
        with manifest_temp_path.open('w') as f:
            json.dump(content, f, indent=2, sort_keys=True)
    except Exception as e:
        log(f"Failed to write changes to temporary manifest file ({e})", level="ERROR")
        error_logged = True
        raise e
    try:
        manifest_temp_path.replace(manifest_path)
    except Exception as e:
        log(f"Failed to replace manifest.json with manifest.temp ({e})", level="ERROR")
        error_logged = True
        raise e


def log(message: str, level: str = "INFO", timestamp: bool = True, console: bool = True, file: bool = True) -> None:
    """Write a log entry to the console and/or logfile.

    Args:
        message: The text to log.
        level: Severity tag prefixed to the entry (e.g. "INFO", "WARNING", "ERROR").
            Pass "" to omit it.
        timestamp: Whether to prefix the entry with the current local time.
        console: Whether to print the entry to stdout.
        file: Whether to write the entry to LOGFILE_PATH.
    """
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
        with open(LOGFILE_PATH, "a") as f:
            f.write(entry+"\n")


# Entry point
if __name__ == "__main__":
    main()
