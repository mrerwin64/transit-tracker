import pathlib
import zipfile
import csv
import io


def route_to_trips(route: str, gtfs_path: str):
    gtfs = pathlib.Path(gtfs_path)
    trips = []
    if gtfs.is_file():  # Assume GTFS data is provided as a zip archive
        with zipfile.ZipFile(gtfs, "r") as zip_file:
            with zip_file.open("trips.txt", "r") as bin_file:
                file = io.TextIOWrapper(bin_file, encoding="utf-8")
                csv_reader = list(csv.reader(file))

                i = 0
                while i < len(csv_reader) and csv_reader[i][0] != route:
                    i += 1
                while i < len(csv_reader) and csv_reader[i][0] == route:
                    trips.append(csv_reader[i][2])
                    i += 1
    elif gtfs.is_dir():  # Assume GTFS data is provided as an already extracted zip archive
        with open(gtfs/"trips.txt", "r") as file:
            csv_reader = list(csv.reader(file))

            i = 0
            while i < len(csv_reader) and csv_reader[i][0] != route:
                i += 1
            while i < len(csv_reader) and csv_reader[i][0] == route:
                trips.append(csv_reader[i][2])
                i += 1
    else:
        raise Exception("Corrupted GTFS data")

    return trips
