from datetime import datetime
import pathlib


def match_gtfs_archives_with_rt_files(gtfs_dir: str | pathlib.Path, gtfs_rt_dir: str | pathlib.Path) -> dict[str, list[str]]:
    if isinstance(gtfs_dir, str):
        gtfs_dir = pathlib.Path(gtfs_dir)
    if isinstance(gtfs_rt_dir, str):
        gtfs_rt_dir = pathlib.Path(gtfs_rt_dir)

    gtfs_archives = sorted([x.name for x in filter(lambda x: x.suffix == ".zip", gtfs_dir.iterdir())], reverse=True)
    timestamp_thresholds = {}
    for gtfs_rt_name in gtfs_archives:
        date_str = gtfs_rt_name[:8]
        threshold = datetime.strptime(date_str, "%Y%m%d")
        timestamp_thresholds[gtfs_rt_name] = threshold

    matches = {x: [] for x in gtfs_archives}
    for gtfs_rt_name in [x.name for x in filter(lambda x: x.suffix == "", gtfs_rt_dir.iterdir())]:
        timestamp = datetime.strptime(gtfs_rt_name, "%Y-%m-%dT%H-%M-%S")
        for gtfs_name, threshold in timestamp_thresholds.items():
            if timestamp > threshold:
                matches[gtfs_name].append(gtfs_rt_name)
                break

    matches = {key: value for key, value in matches.items() if len(value) > 0}
    return matches
