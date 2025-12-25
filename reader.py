# Modules
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2
import pathlib
import zipfile
import json
import csv
import io


# Utility functions
def pb_to_dict(pb_path: str | pathlib.Path) -> dict:
    """Return a GTFS-RT protobuf file as a dictionary."""
    feed = gtfs_realtime_pb2.FeedMessage()
    with open(pb_path, "rb") as file:
        feed.ParseFromString(file.read())
    return MessageToDict(feed)


def gtfs_to_list(gtfs_path: str | pathlib.Path, filename: str) -> list:
    """Return a GTFS file as a csv-like 2D list."""
    if isinstance(gtfs_path, str):
        gtfs_path = pathlib.Path(gtfs_path)
    if gtfs_path.is_file():  # Assume GTFS data is provided as a zip archive
        with zipfile.ZipFile(gtfs_path, "r") as zip_file:
            with zip_file.open(filename, "r") as bin_file:
                file = io.TextIOWrapper(bin_file, encoding="utf-8")
                csv_reader = list(csv.reader(file))
    elif gtfs_path.is_dir():  # Assume GTFS data is provided as an already extracted zip archive
        with open(gtfs_path/filename, "r") as file:
            csv_reader = list(csv.reader(file))
    else:
        raise Exception("Invalid GTFS data")
    return csv_reader


def gtfs_rt_to_dict(feed_path: str | pathlib.Path) -> dict:
    """Return a GTFS-RT file (protobuf or JSON) as a dictionary."""
    feed_file = pathlib.Path(feed_path)
    if feed_file.suffix == ".json":
        with open(feed_file, "r") as file:
            feed = json.load(file)
    elif feed_file.suffix in (".pb", ""):
        feed = pb_to_dict(feed_file)
    else:
        raise Exception("Invalid GTFS-RT feed")
    return feed


# GTFS functions
def routes(gtfs_path: str | pathlib.Path) -> list[str]:
    """Return all route_ids in a GTFS file."""
    routes_txt = gtfs_to_list(gtfs_path, "routes.txt")
    result = [x[0] for x in routes_txt[1:]]
    return result


def stops(gtfs_path: str | pathlib.Path) -> list[tuple[int, str, str]]:
    """Return all stops in a GTFS file.

    Returns:
        List of tuples representing a stop (stop_id, stop_code, stop_name).
    """
    stops_txt = gtfs_to_list(gtfs_path, "stops.txt")
    result = [(int(x[0]), x[1], x[2]) for x in stops_txt[1:]]
    return result


def trips(gtfs_path: str | pathlib.Path) -> list[tuple[str, str]]:
    """Return all trips in a GTFS file.

    Returns:
        List of tuples representing a trip (trip_id, route_id).
    """
    trips_txt = gtfs_to_list(gtfs_path, "trips.txt")
    result = [(x[2], x[0]) for x in trips_txt[1:]]
    return result


def routes_to_trips(routes: list[str], gtfs_path: str | pathlib.Path) -> dict[str, list[str]]:
    """Return all trips of a route, for multiple routes.

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


def trips_to_stops(trips: list[str], gtfs_path: str | pathlib.Path) -> dict[str, list[int]]:
    """Return all stop_ids of a trip, for multiple trips."""
    stop_times_txt = gtfs_to_list(gtfs_path, "stop_times.txt")
    stops = {x: [] for x in trips}
    for line in stop_times_txt[1:]:
        trip = line[0]
        if trip in trips:
            stops[trip].append(int(line[3]))
    return stops


# GTFS-RT functions
def trip_updates(trips_or_routes: list[str], feed_path: str | pathlib.Path) -> dict[str, list[dict[str, str | int]]]:
    """Return all trip updates for route or trip, for multiple route_ids/trip_ids.

    Returns:
        Dictionary mapping a list of updates (also dictionaries) to each route/trip id.
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
