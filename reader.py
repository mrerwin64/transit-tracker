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


def route_to_trips(route: str, gtfs_path: str) -> list[str]:
    gtfs = pathlib.Path(gtfs_path)
    if gtfs.is_file():  # Assume GTFS data is provided as a zip archive
        with zipfile.ZipFile(gtfs, "r") as zip_file:
            with zip_file.open("trips.txt", "r") as bin_file:
                file = io.TextIOWrapper(bin_file, encoding="utf-8")
                csv_reader = list(csv.reader(file))
    elif gtfs.is_dir():  # Assume GTFS data is provided as an already extracted zip archive
        with open(gtfs/"trips.txt", "r") as file:
            csv_reader = list(csv.reader(file))
    else:
        raise Exception("Invalid GTFS data")

    trips = []
    i = 0
    while i < len(csv_reader) and csv_reader[i][0] != route:
        i += 1
    while i < len(csv_reader) and csv_reader[i][0] == route:
        trips.append(csv_reader[i][2])
        i += 1
    return trips


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
