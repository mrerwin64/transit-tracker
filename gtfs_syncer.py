# Modules
from datetime import datetime
import requests
import pathlib
import json
import re


# Constant defaults
GTFS_LIST_URL = "https://www.ztm.poznan.pl/otwarte-dane/gtfsfiles/"
GTFS_DOWNLOAD_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile/"
LOGFILE_PATH = "syncer.log"
ARCHIVE_PATH = "archive/gtfs/"
REQUEST_DELAY = 0.5


# Functions
def main():
    manifest_integrity = verify_manifest()
    if not manifest_integrity[0]:
        print(f"{manifest_integrity[1]} errors in manifest.json")
        return

    local_files = list_local_files()
    remote_files = list_remote_files()

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

    for filename in remote_only:
        download_gtfs_file(filename)
    for filename in mismatches:
        update_gtfs_file(filename)
    for filename in local_only:
        retire_gtfs_file(filename)


def verify_manifest() -> tuple[bool, int]:
    errors = -1
    manifest_path = pathlib.Path(ARCHIVE_PATH)/"manifest.json"
    manifest_files = set(json.load(manifest_path.open()).keys())
    disk_files = pathlib.Path(ARCHIVE_PATH).iterdir()

    for disk in [x.name for x in disk_files]:
        if disk in manifest_files:
            manifest_files.remove(disk)
        else:
            errors += 1
    errors += len(manifest_files)

    if errors == 0:
        return True, errors
    else:
        return False, errors


def list_local_files() -> dict[str, dict[str, str]]:
    manifest_path = pathlib.Path(ARCHIVE_PATH)/"manifest.json"
    files = json.load(manifest_path.open())
    return files


def list_remote_files() -> dict[str, dict[str, str]]:
    response = requests.get(GTFS_LIST_URL, timeout=30)
    html_text = response.text
    rows = re.findall(r"<td>(\d{8}_\d{8}\.zip)</td><td>([^<]+)</td><td>([^<]+)</td>", html_text)
    files = {}
    for filename, size, modified in rows:
        files[filename] = {
            "size": size.strip(),
            "modified": datetime.strptime(modified.strip(), "%d.%m.%Y, %H:%M:%S").isoformat(),
        }
    return files


def download_gtfs_file(filename: str):
    pass


def update_gtfs_file(filename: str):
    pass


def retire_gtfs_file(filename: str):
    pass


# Entry point
if __name__ == "__main__":
    main()
