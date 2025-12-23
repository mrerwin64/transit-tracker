from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2
import pathlib
import zipfile
import json
import csv
import io


def pb_to_dict(pb_path: str | pathlib.Path) -> dict:
    feed = gtfs_realtime_pb2.FeedMessage()
    with open(pb_path, "rb") as file:
        feed.ParseFromString(file.read())
    return MessageToDict(feed)


def gtfs_to_csv(gtfs_path: str | pathlib.Path, filename: str) -> list:
    if type(gtfs_path) is str:
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
    

def route_to_trips(route: str, gtfs_path: str) -> list[str]:
    trips_txt = gtfs_to_csv(gtfs_path, "trips.txt")
    route_trips = []
    i = 0
    while i < len(trips_txt) and trips_txt[i][0] != route:
        i += 1
    while i < len(trips_txt) and trips_txt[i][0] == route:
        route_trips.append(trips_txt[i][2])
        i += 1
    return route_trips


def trip_updates(trip_or_route: str, feed_path: str) -> list[dict[str, int]]:
    feed_file = pathlib.Path(feed_path)
    if feed_file.suffix == ".json":
        with open(feed_file, "r") as file:
            feed = json.load(file)
    elif feed_file.suffix == ".pb":
        feed = pb_to_dict(feed_file)
    else:
        raise Exception("Invalid GTFS-RT feed")

    updates = []
    messages = feed["entity"]
    for message in messages:
        if "tripUpdate" in message:
            update = {"route": message["tripUpdate"]["trip"]["routeId"],
                      "trip": message["tripUpdate"]["trip"]["tripId"],
                      "next_stop": message["tripUpdate"]["stopTimeUpdate"][0]["stopSequence"],
                      "delay": message["tripUpdate"]["stopTimeUpdate"][0]["arrival"]["delay"]}
            if trip_or_route in (update["route"], update["trip"]):
                updates.append(update)
    return updates


def trip_to_stops(trip: str, gtfs_path: str) -> list[int]:
    stop_times_txt = gtfs_to_csv(gtfs_path, "stop_times.txt")
    stops = [x[3] for x in filter(lambda x: x[0] == trip, stop_times_txt)]
    return stops
