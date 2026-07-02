"""Reads GTFS static archives and GTFS-RT feeds into plain Python data structures.

Assumes ZTM Poznan's non-standard GTFS/GTFS-RT data throughout (e.g. trip updates
carry only a single StopTimeUpdate for the next stop), not generic spec compliance.
"""

# Modules
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2
from datetime import datetime, time
import pathlib
import zipfile
import json
import csv
import io


# Utility functions
def pb_to_dict(pb_path: str | pathlib.Path) -> dict:
    """Return a GTFS-RT protobuf file as a dictionary.

    Args:
        pb_path: Path to the .pb feed file to parse.

    Returns:
        The decoded FeedMessage as a nested dict, matching the GTFS-RT protobuf schema.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    with open(pb_path, "rb") as file:
        feed.ParseFromString(file.read())
    return MessageToDict(feed)


def gtfs_to_list(gtfs_path: str | pathlib.Path, filename: str) -> list:
    """Return a GTFS file as a csv-like 2D list.

    Args:
        gtfs_path: Path to a GTFS zip archive, or to a directory containing an
            already-extracted archive.
        filename: Name of the file to read from the archive/directory (e.g.
            "routes.txt"), including the header row.

    Returns:
        Rows of the CSV file as a list of lists of strings, including the header row.

    Raises:
        Exception: If gtfs_path is neither a file nor a directory.
    """
    if isinstance(gtfs_path, str):
        gtfs_path = pathlib.Path(gtfs_path)
    if gtfs_path.is_file():  # Assume GTFS data is provided as a zip archive
        with zipfile.ZipFile(gtfs_path, "r") as zip_file:
            with zip_file.open(filename, "r") as bin_file:
                file = io.TextIOWrapper(bin_file, encoding="utf-8")
                csv_reader = list(csv.reader(file))
    elif gtfs_path.is_dir():  # Assume GTFS data is provided as an already extracted zip archive
        with open(gtfs_path/filename, "r", encoding="utf-8") as file:
            csv_reader = list(csv.reader(file))
    else:
        raise Exception("Invalid GTFS data")
    return csv_reader


def gtfs_rt_to_dict(feed_path: str | pathlib.Path) -> dict:
    """Return a GTFS-RT file (protobuf or JSON) as a dictionary.

    Args:
        feed_path: Path to a .pb, extension-less protobuf, or .json GTFS-RT feed file.

    Returns:
        The feed contents as a dictionary.

    Raises:
        Exception: If feed_path has an unsupported extension.
    """
    feed_file = pathlib.Path(feed_path)
    if feed_file.suffix == ".json":
        with open(feed_file, "r", encoding="utf-8") as file:
            feed = json.load(file)
    elif feed_file.suffix in (".pb", ""):
        feed = pb_to_dict(feed_file)
    else:
        raise Exception("Invalid GTFS-RT feed")
    return feed


# GTFS functions
def routes(gtfs_path: str | pathlib.Path) -> list[str]:
    """Return all route_ids in a GTFS file.

    Args:
        gtfs_path: Path to a GTFS zip archive, or an already-extracted directory.

    Returns:
        List of route_id strings.
    """
    routes_txt = gtfs_to_list(gtfs_path, "routes.txt")
    result = [x[0] for x in routes_txt[1:]]
    return result


def stops(gtfs_path: str | pathlib.Path) -> list[tuple[int, str, str]]:
    """Return all stops in a GTFS file.

    Args:
        gtfs_path: Path to a GTFS zip archive, or an already-extracted directory.

    Returns:
        List of tuples representing a stop (stop_id, stop_code, stop_name).
    """
    stops_txt = gtfs_to_list(gtfs_path, "stops.txt")
    result = [(int(x[0]), x[1], x[2]) for x in stops_txt[1:]]
    return result


def trips(gtfs_path: str | pathlib.Path) -> list[tuple[str, str]]:
    """Return all trips in a GTFS file.

    Args:
        gtfs_path: Path to a GTFS zip archive, or an already-extracted directory.

    Returns:
        List of tuples representing a trip (trip_id, route_id).
    """
    trips_txt = gtfs_to_list(gtfs_path, "trips.txt")
    result = [(x[2], x[0]) for x in trips_txt[1:]]
    return result


def routes_to_trips(routes: list[str], gtfs_path: str | pathlib.Path) -> dict[str, list[str]]:
    """Return all trips of a route, for multiple routes.

    Args:
        routes: List of route_ids to look up.
        gtfs_path: Path to a GTFS zip archive, or an already-extracted directory.

    Returns:
        Dictionary mapping a list of trip_ids to each route_id.
    """
    trips_txt = gtfs_to_list(gtfs_path, "trips.txt")
    trips = {x: [] for x in routes}
    for line in trips_txt[1:]:
        route = line[0]
        if route in routes:
            trips[route].append(line[2])
    return trips


def trips_to_stops(trips: list[str], gtfs_path: str | pathlib.Path) -> dict[str, list[tuple[int, time, int]]]:
    """Return all stops of a trip, in order, for multiple trips.

    Args:
        trips: List of trip_ids to look up.
        gtfs_path: Path to a GTFS zip archive, or an already-extracted directory.

    Returns:
        Dictionary mapping lists of tuples (stop_id, stop_time, stop_sequence),
        sorted by stop_sequence, to given trip_ids.
    """
    stop_times_txt = gtfs_to_list(gtfs_path, "stop_times.txt")
    stops = {x: [] for x in trips}
    for line in stop_times_txt[1:]:
        trip = line[0]
        if trip in trips:
            stop = (int(line[3]), datetime.strptime(line[2], "%H:%M:%S").time(), int(line[4]))
            stops[trip].append(stop)
            stops[trip].sort(key=lambda x: x[2])
    return stops


# GTFS-RT functions
def trip_updates(trips_or_routes: list[str], feed_path: str | pathlib.Path) -> dict[str, list[dict[str, str | int]]]:
    """Return all trip updates for route or trip, for multiple route_ids/trip_ids.

    Each update reflects a single StopTimeUpdate, since Poznan's GTFS-RT feed only
    ever reports the next stop for a trip rather than the full remaining sequence.

    Args:
        trips_or_routes: List of trip_ids or route_ids to collect updates for.
        feed_path: Path to a GTFS-RT trip_updates feed (protobuf or JSON).

    Returns:
        Dictionary mapping a list of updates (also dictionaries) to each route/trip id.
        Each update dict has keys "route", "trip", "next_stop" (stop_sequence),
        "delay" (seconds), and "timestamp".
    """
    feed = gtfs_rt_to_dict(feed_path)
    updates = {x: [] for x in trips_or_routes}
    for message in feed["entity"]:
        if "tripUpdate" in message:
            update = {"route": message["tripUpdate"]["trip"]["routeId"],
                      "trip": message["tripUpdate"]["trip"]["tripId"],
                      "next_stop": message["tripUpdate"]["stopTimeUpdate"][0]["stopSequence"],
                      "delay": message["tripUpdate"]["stopTimeUpdate"][0]["arrival"]["delay"],
                      "timestamp": message["tripUpdate"]["timestamp"]}
            if update["trip"] in trips_or_routes:
                updates[update["trip"]].append(update)
            elif update["route"] in trips_or_routes:
                updates[update["route"]].append(update)
    return updates
