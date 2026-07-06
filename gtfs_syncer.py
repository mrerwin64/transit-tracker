# Modules
import pathlib
import json


# Constant defaults
GTFS_LIST_URL = "https://www.ztm.poznan.pl/otwarte-dane/gtfsfiles/"
GTFS_DOWNLOAD_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile/"
LOGFILE_PATH = "syncer.log"
ARCHIVE_PATH = "archive/gtfs/"
REQUEST_DELAY = 0.5


# Functions
def main():
    verify_manifest()
    list_local_files()
    list_remote_files()


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


def list_local_files() -> dict[str, dict]:
    pass


def list_remote_files() -> dict[str, dict]:
    pass


# Entry point
if __name__ == "__main__":
    main()
