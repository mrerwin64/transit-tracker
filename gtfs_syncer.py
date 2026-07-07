# Modules
from datetime import datetime
import requests
import pathlib
import zipfile
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
def main():
    verify_manifest()

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
        download_gtfs_file(filename, remote_files[filename]["modified"], remote_files[filename]["size"])
    for filename in mismatches:
        update_gtfs_file(filename, remote_files[filename]["modified"], remote_files[filename]["size"])
    for filename in local_only:
        retire_gtfs_file(filename)


def verify_manifest():
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
        raise Exception("ManifestError")


def list_local_files(old=False) -> dict[str, dict[str, str]]:
    files = load_manifest()

    if not old:
        for filename in list(files.keys()):
            if filename[-4:] == ".old":
                del files[filename]

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

    if len(files) == 0:
        raise Exception("NoRemoteFiles")
    return files


def update_gtfs_file(filename: str, modified: str, size: str):
    retire_gtfs_file(filename)
    download_gtfs_file(filename, modified, size)


def retire_gtfs_file(filename: str):
    # Make sure the new filename is unoccupied
    new_name = filename+".old"
    if (pathlib.Path(ARCHIVE_PATH)/new_name).exists():
        retire_gtfs_file(new_name)
    # Rename the file
    file = pathlib.Path(ARCHIVE_PATH)/filename
    file.rename(file.parent/new_name)
    # Update the manifest
    rename_manifest_entry(filename, new_name)


def download_gtfs_file(filename: str, modified: str, size: str):
    # Fetch the file
    response = requests.get(GTFS_DOWNLOAD_URL, params={"file": filename}, timeout=30)
    response.raise_for_status()
    # Test if it's an uncorrupted zip archive
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                raise Exception("CorruptedGtfs")
    except zipfile.BadZipFile:
        raise Exception("CorruptedGtfs")
    # Save it
    file_path = pathlib.Path(ARCHIVE_PATH)/filename
    file_path.write_bytes(response.content)
    # Update the manifest
    add_manifest_entry(filename, modified, size)
    # Request delay
    time.sleep(REQUEST_DELAY)


def rename_manifest_entry(old_filename: str, new_filename: str):
    manifest = load_manifest()
    manifest[new_filename] = manifest.pop(old_filename)
    save_manifest(manifest)


def add_manifest_entry(filename: str, modified: str, size: str):
    manifest = load_manifest()
    manifest[filename] = {"modified": modified, "size": size}
    save_manifest(manifest)


manifest_path = pathlib.Path(ARCHIVE_PATH)/"manifest.json"
def load_manifest() -> dict[str, dict[str, str]]:
    return json.load(manifest_path.open())


def save_manifest(content: dict[str, dict[str, str]]):
    manifest_temp_path = pathlib.Path(ARCHIVE_PATH)/"manifest.temp"
    json.dump(content, manifest_temp_path.open('w'), indent=2, sort_keys=True)
    manifest_temp_path.replace(manifest_path)


# Entry point
if __name__ == "__main__":
    main()
