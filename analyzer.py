from datetime import datetime, date
import pathlib
import reader


def match_gtfs_archives_with_rt_files(gtfs_dir: str | pathlib.Path, gtfs_rt_dir: str | pathlib.Path) -> dict[pathlib.Path, dict[date, list[pathlib.Path]]]:
    # Convert path string to pathlib.Path
    if isinstance(gtfs_dir, str):
        gtfs_dir = pathlib.Path(gtfs_dir)
    if isinstance(gtfs_rt_dir, str):
        gtfs_rt_dir = pathlib.Path(gtfs_rt_dir)

    # Get thresholds after which GTFS-RT files match GTFS file (when sorted newer -> older)
    gtfs_archives = sorted([x.name for x in filter(lambda x: x.suffix == ".zip", gtfs_dir.iterdir())], reverse=True)
    timestamp_thresholds = {}
    for gtfs_name in gtfs_archives:
        date_str = gtfs_name[:8]
        threshold = datetime.strptime(date_str, "%Y%m%d")
        timestamp_thresholds[pathlib.Path(gtfs_dir/gtfs_name)] = threshold

    # Match GTFS-RT files to GTFS files and group them by date
    matches = {pathlib.Path(gtfs_dir/x): {} for x in gtfs_archives}
    for gtfs_rt_name in [x.name for x in filter(lambda x: x.suffix == "", gtfs_rt_dir.iterdir())]:
        timestamp = datetime.strptime(gtfs_rt_name, "%Y-%m-%dT%H-%M-%S")
        date = timestamp.date()
        for gtfs_file, threshold in timestamp_thresholds.items():
            if timestamp > threshold:
                if date not in matches[gtfs_file]:
                    matches[gtfs_file][date] = []
                matches[gtfs_file][date].append(pathlib.Path(gtfs_rt_dir/gtfs_rt_name))
                break

    # Return only GTFS files with matched GTFS-RT files
    matches = {key: value for key, value in matches.items() if len(value) > 0}
    return matches


def trips_stop_delays(trips: list[str], gtfs_file: pathlib.Path, gtfs_rt_files: list[pathlib.Path]) -> dict[str, dict[int, int | None]]:
    all_updates = {x: [] for x in trips}
    for rt_file in gtfs_rt_files:
        updates = reader.trip_updates(trips, rt_file)
        for trip in trips:
            all_updates[trip] += updates[trip]

    trip_stop_ids = reader.trips_to_stops(trips, gtfs_file)
    trip_stop_delays = {}
    for trip in trips:
        stop_ids = trip_stop_ids[trip]
        updates = all_updates[trip]
        stop_updates = {x: [] for x in stop_ids}
        for update in updates:
            stop_sequence = update["next_stop"]
            stop_id = stop_ids[stop_sequence]
            stop_updates[stop_id].append(update)
        stop_delays = {key: (max(value, key=lambda x: x["timestamp"])["delay"] if len(value) > 0 else None) for key, value in stop_updates.items()}
        trip_stop_delays[trip] = stop_delays
    return trip_stop_delays


def routes_stop_delays(routes: list[str], gtfs: pathlib.Path, gtfs_rt: list[pathlib.Path]) -> dict[str, dict[str, dict[int, int | None]]]:
    results = {}
    for route in routes:
        trips = reader.routes_to_trips([route], gtfs)[route]
        results[route] = trips_stop_delays(trips, gtfs, gtfs_rt)
    return results
