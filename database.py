import io
import sqlite3
import requests
import zipfile
import csv
import os


class Database:
    def __init__(self, db_name="gtfs.db"):
        self.db_name = db_name

    def reset_database(self):
        if os.path.exists(self.db_name):
            os.remove(self.db_name)

    def create_gtfs_tables(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        gtfs_tables = {
            "agency": """
                CREATE TABLE IF NOT EXISTS agency (
                    agency_id TEXT PRIMARY KEY,
                    agency_name TEXT NOT NULL,
                    agency_url TEXT NOT NULL,
                    agency_timezone TEXT NOT NULL,
                    agency_lang TEXT,
                    agency_phone TEXT,
                    agency_fare_url TEXT,
                    ticketing_deep_link_id TEXT,
                    agency_email TEXT
                )
            """,
            "stops": """
                CREATE TABLE IF NOT EXISTS stops (
                    stop_id TEXT PRIMARY KEY,
                    stop_code TEXT,
                    stop_name TEXT NOT NULL,
                    stop_desc TEXT,
                    stop_lat REAL NOT NULL,
                    stop_lon REAL NOT NULL,
                    zone_id TEXT,
                    stop_url TEXT,
                    location_type INTEGER,
                    parent_station TEXT,
                    stop_timezone TEXT,
                    wheelchair_boarding INTEGER,
                    platform_code TEXT,
                    level_id TEXT
                )
            """,
            "routes": """
                CREATE TABLE IF NOT EXISTS routes (
                    route_id TEXT PRIMARY KEY,
                    agency_id TEXT,
                    route_short_name TEXT NOT NULL,
                    route_long_name TEXT NOT NULL,
                    route_desc TEXT,
                    route_type INTEGER NOT NULL,
                    route_url TEXT,
                    route_color TEXT,
                    route_text_color TEXT,
                    route_sort_order INTEGER,
                    bikes_allowed INTEGER
                )
            """,
            "trips": """
                CREATE TABLE IF NOT EXISTS trips (
                    trip_id TEXT PRIMARY KEY,
                    route_id TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    trip_headsign TEXT,
                    trip_short_name TEXT,
                    direction_id INTEGER,
                    block_id TEXT,
                    shape_id TEXT,
                    wheelchair_accessible INTEGER,
                    bikes_allowed INTEGER,
                    peak_offpeak INTEGER,
                    route_short_name TEXT,
                    trip_bikes_allowed INTEGER,
                    ticketing_trip_id TEXT,
                    ticketing_type TEXT
                )
            """,
            "stop_times": """
                CREATE TABLE IF NOT EXISTS stop_times (
                    trip_id TEXT NOT NULL,
                    arrival_time TEXT NOT NULL,
                    departure_time TEXT NOT NULL,
                    stop_id TEXT NOT NULL,
                    stop_sequence INTEGER NOT NULL,
                    stop_headsign TEXT,
                    pickup_type INTEGER,
                    drop_off_type INTEGER,
                    shape_dist_traveled REAL,
                    timepoint INTEGER,
                    departure_buffer INTEGER,
                    route_short_name TEXT,
                    start_pickup_drop_off_window TEXT,
                    end_pickup_drop_off_window TEXT,
                    local_zone_id TEXT,
                    pickup_booking_rule_id TEXT,
                    drop_off_booking_rule_id TEXT,
                    PRIMARY KEY (trip_id, stop_id, stop_sequence)
                )
            """,
            "calendar": """
                CREATE TABLE IF NOT EXISTS calendar (
                    service_id TEXT PRIMARY KEY,
                    monday INTEGER NOT NULL,
                    tuesday INTEGER NOT NULL,
                    wednesday INTEGER NOT NULL,
                    thursday INTEGER NOT NULL,
                    friday INTEGER NOT NULL,
                    saturday INTEGER NOT NULL,
                    sunday INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL
                )
            """,
            "calendar_dates": """
                CREATE TABLE IF NOT EXISTS calendar_dates (
                    service_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    exception_type INTEGER NOT NULL,
                    PRIMARY KEY (service_id, date)
                )
            """,
            "shapes": """
                CREATE TABLE IF NOT EXISTS shapes (
                    shape_id TEXT NOT NULL,
                    shape_pt_lat REAL NOT NULL,
                    shape_pt_lon REAL NOT NULL,
                    shape_pt_sequence INTEGER NOT NULL,
                    shape_dist_traveled REAL,
                    PRIMARY KEY (shape_id, shape_pt_sequence)
                )
            """,
            "transfers": """
                CREATE TABLE IF NOT EXISTS transfers (
                    from_stop_id TEXT NOT NULL,
                    to_stop_id TEXT NOT NULL,
                    transfer_type INTEGER NOT NULL,
                    min_transfer_time INTEGER,
                    from_route_id TEXT,
                    from_trip_id TEXT,
                    to_route_id TEXT,
                    to_trip_id TEXT,
                    PRIMARY KEY (from_stop_id, to_stop_id)
                )
            """,
            "feed_info": """
                CREATE TABLE IF NOT EXISTS feed_info (
                    feed_id TEXT PRIMARY KEY,
                    feed_publisher_name TEXT NOT NULL,
                    feed_publisher_url TEXT NOT NULL,
                    feed_lang TEXT NOT NULL,
                    feed_start_date TEXT,
                    feed_end_date TEXT,
                    feed_version TEXT,
                    conv_rev TEXT,
                    plan_rev TEXT
                )
            """,
        }

        for table_name, create_statement in gtfs_tables.items():
            cursor.execute(create_statement)

        conn.commit()
        conn.close()

    def download_and_extract_gtfs(self, url):
        # Download the GTFS ZIP file
        response = requests.get(url)
        if response.status_code == 200:
            # Use BytesIO to handle the ZIP file in memory
            return io.BytesIO(response.content)
        else:
            raise Exception(
                f"Failed to download GTFS data. HTTP status code: {response.status_code}"
            )

    def populate_database(self, zip_buffer):
        # Connect to the database
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        # Map GTFS files to their corresponding tables
        gtfs_files = {
            "agency.txt": "agency",
            "stops.txt": "stops",
            "routes.txt": "routes",
            "trips.txt": "trips",
            "stop_times.txt": "stop_times",
            "calendar.txt": "calendar",
            "calendar_dates.txt": "calendar_dates",
            "shapes.txt": "shapes",
            "transfers.txt": "transfers",
            "feed_info.txt": "feed_info",
        }

        # Open the ZIP file in memory
        with zipfile.ZipFile(zip_buffer, "r") as zip_ref:
            # Iterate over GTFS files and insert data into tables
            for file_name, table_name in gtfs_files.items():
                if file_name in zip_ref.namelist():
                    with zip_ref.open(file_name) as file:
                        # Use TextIOWrapper to read the file as text
                        with io.TextIOWrapper(file, encoding="utf-8-sig") as f:
                            reader = csv.DictReader(f)
                            columns = reader.fieldnames
                            placeholders = ", ".join(["?"] * len(columns))
                            insert_query = f"INSERT OR IGNORE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
                            for row in reader:
                                values = [row[col] for col in columns]
                                cursor.execute(insert_query, values)

        # Commit and close the connection
        conn.commit()
        conn.close()

    def get_connection(self):
        """
        Get a connection to the database.
        """
        conn = sqlite3.connect(self.db_name)
        return conn, conn.cursor()
