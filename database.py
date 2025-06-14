import datetime
import io
import sqlite3
import requests
import zipfile
import csv
import os
from models import Agency, Route, Shape, StopTime, Stop, Transfer, Trip
from typing import Optional
import json
from transfer_generator import TransferGenerator
from tqdm import tqdm


class Database:
    def __init__(self, db_name="railfinder.db"):
        self.db_name = db_name

    def reset_database(self):
        if os.path.exists(self.db_name):
            os.remove(self.db_name)

    def create_metadata_table(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def set_metadata(self, key: str, value: str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value)
        )
        conn.commit()
        conn.close()

    def get_metadata(self, key: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # has the metadata table been created?
        cursor.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='metadata'"
        )
        row = cursor.fetchone()
        if row[0] == 0:
            conn.close()
            return None
        cursor.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

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
                    level_id TEXT,
                    alias TEXT,
                    stop_area TEXT,
                    lest_x REAL,
                    lest_y REAL,
                    zone_name TEXT,
                    authority TEXT,
                    stop_direction TEXT,
                    vehicle_type TEXT,
                    mta_stop_id TEXT,
                    regional_fare_card TEXT,
                    tts_stop_name TEXT,
                    stop_elevation REAL,
                    ch_station_long_name TEXT,
                    ch_station_synonym1 TEXT,
                    ch_station_synonym2 TEXT,
                    ch_station_synonym3 TEXT,
                    ch_station_synonym4 TEXT,
                    stop_idx INTEGER
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
                    bikes_allowed INTEGER,
                    competent_authority TEXT,
                    network_id TEXT,
                    eligibility_restricted INTEGER,
                    regional_fare_card TEXT
                )
            """,
            "trips": """
                CREATE TABLE IF NOT EXISTS trips (
                    trip_id TEXT PRIMARY KEY,
                    route_id TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    trip_headsign TEXT,
                    trip_short_name TEXT,
                    trip_long_name TEXT,
                    direction_id INTEGER,
                    block_id TEXT,
                    shape_id TEXT,
                    wheelchair_accessible INTEGER,
                    bikes_allowed INTEGER,
                    peak_offpeak INTEGER,
                    route_short_name TEXT,
                    trip_bikes_allowed INTEGER,
                    ticketing_trip_id TEXT,
                    ticketing_type TEXT,
                    direction_code TEXT,
                    note_id TEXT,
                    mean_duration_factor REAL,
                    mean_duration_offset REAL,
                    safe_duration_factor REAL,
                    safe_duration_offset REAL,
                    cars_allowed INTEGER,
                    mta_trip_id TEXT,
                    boarding_type INTEGER,
                    attributes_ch TEXT,
                    realtime_trip_id TEXT
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
                    note_id TEXT,
                    location_id TEXT,
                    location_group_id TEXT,
                    continuous_pickup INTEGER,
                    continuous_drop_off INTEGER,
                    attributes_ch TEXT,
                    fare_units_traveled INTEGER,
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
                    plan_rev TEXT,
                    default_lang TEXT,
                    feed_contact_mail TEXT,
                    feed_contact_url TEXT
                )
            """,
        }

        for table_name, create_statement in gtfs_tables.items():
            cursor.execute(create_statement)

        conn.commit()
        conn.close()

    def download_gtfs(self, url):
        # Download the GTFS ZIP file
        response = requests.get(url)
        if response.status_code == 200:
            # Use BytesIO to handle the ZIP file in memory
            return io.BytesIO(response.content)
        else:
            raise Exception(
                f"Failed to download GTFS data. HTTP status code: {response.status_code}"
            )

    def populate_database(self, zip_buffer, id: int):
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
                            if columns is None:
                                raise ValueError(
                                    f"CSV file {file_name} has no header or is improperly formatted."
                                )
                            placeholders = ", ".join(["?"] * len(columns))
                            insert_query = f"INSERT OR IGNORE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
                            should_prefix_columns = [
                                True if col.endswith("_id") else False
                                for col in columns
                            ]

                            for row in reader:
                                values = [row[col] for col in columns]
                                if should_prefix_columns:
                                    values = [
                                        f"{id:02}/{val}" if prefix else val
                                        for val, prefix in zip(
                                            values, should_prefix_columns
                                        )
                                    ]
                                cursor.execute(insert_query, values)

        # Commit and close the connection
        conn.commit()
        conn.close()

    def download_and_populate_gtfs(self, url: str, id: int):
        """
        Download GTFS data from the given URL and populate the database.
        """
        zip_buffer = self.download_gtfs(url)
        self.populate_database(zip_buffer, id)

    def get_connection(self):
        """
        Get a connection to the database.
        """
        conn = sqlite3.connect(self.db_name)
        return conn, conn.cursor()

    def create_gtfs_indexes(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_stop_times_stop_id_arrival ON stop_times (stop_id, arrival_time)",
            "CREATE INDEX IF NOT EXISTS idx_stop_times_trip_id ON stop_times (trip_id)",
            "CREATE INDEX IF NOT EXISTS idx_trips_service_id ON trips (service_id)",
            "CREATE INDEX IF NOT EXISTS idx_trips_route_id ON trips (route_id)",
            "CREATE INDEX IF NOT EXISTS idx_routes_agency_id ON routes (agency_id)",
            "CREATE INDEX IF NOT EXISTS idx_calendar_service_id ON calendar (service_id)",
            "CREATE INDEX IF NOT EXISTS idx_calendar_dates_service_id_date ON calendar_dates (service_id, date)",
            "CREATE INDEX IF NOT EXISTS idx_stops_stop_name ON stops (stop_name)",
            "CREATE INDEX IF NOT EXISTS idx_transfers_from_stop_id ON transfers (from_stop_id)",
            "CREATE INDEX IF NOT EXISTS idx_transfers_to_stop_id ON transfers (to_stop_id)",
            "CREATE INDEX IF NOT EXISTS idx_shapes_shape_id ON shapes (shape_id)",
            "CREATE INDEX IF NOT EXISTS idx_stop_times_stop_sequence ON stop_times (stop_sequence)",  # Adding this index and the 4 following ones sped up journey searches by 1128% !!!
            "CREATE INDEX IF NOT EXISTS idx_stop_times_trip_id_stop_sequence ON stop_times (trip_id, stop_sequence)",
            "CREATE INDEX IF NOT EXISTS idx_calendar_start_end_date ON calendar (start_date, end_date)",
            "CREATE INDEX IF NOT EXISTS idx_calendar_dates_date_exception_type ON calendar_dates (date, exception_type)",
            "CREATE INDEX IF NOT EXISTS idx_stops_lat_lon ON stops (stop_lat, stop_lon)",
        ]

        for index in tqdm(indexes, desc="Creating GTFS indexes"):
            cursor.execute(index)

        print("GTFS indexes created successfully.")

        conn.commit()
        conn.close()

    def add_nearby_transfers(self, max_distance_m=100, transfer_time_sec=120):
        """
        Add transfers between all stops within max_distance_m meters of each other,
        except if a transfer already exists between the stops or if both stop_id starts with excluded prefixes.
        Uses multiprocessing and a spatial index for efficiency.
        """
        tg = TransferGenerator(
            self,
            max_distance_m=max_distance_m,
            transfer_time_sec=transfer_time_sec,
        )
        tg.generate_transfers()

    def load_and_prepare_data(self, data_path: str):
        """
        Load GTFS data from sources in data_path, create tables, indexes, and generate nearby transfers.
        """
        self.reset_database()
        self.create_metadata_table()
        self.create_gtfs_tables()

        with open(data_path, "r") as file:
            data_sources = json.loads(file.read())

        for i, (name, gtfs_url) in enumerate(data_sources.items()):
            print(f"Downloading GTFS data from {name}: {gtfs_url}")
            try:
                self.download_and_populate_gtfs(
                    gtfs_url, i
                )  # the index is used to identify the source, to prefix all the ids with it
            except Exception as e:
                print(f"Error downloading or populating data from {name}: {e}")
        print("Creating indexes for GTFS tables...")
        self.create_gtfs_indexes()
        print("Indexes created successfully.")
        print("Generating nearby transfers...")
        self.add_nearby_transfers(max_distance_m=100, transfer_time_sec=120)
        print("GTFS data loaded and transfers generated successfully.")
        self.set_metadata("updated_at", datetime.datetime.now().isoformat())

    def update_database(self, data_path: str, force_update: bool = False):
        """
        Reload GTFS data from sources if the database is empty or if the last update was more than 24 hours ago.
        """
        last_update = self.get_metadata("updated_at")

        if (
            not last_update
            or (
                datetime.datetime.now() - datetime.datetime.fromisoformat(last_update)
            ).total_seconds()
            > 24 * 3600
            or force_update
        ):
            if not last_update:
                print("Database is empty, loading GTFS data for the first time.")
            elif force_update:
                print("Forcing reload of GTFS data.")
            else:
                print(
                    "Database is outdated, reloading GTFS data as last update was more than 24 hours ago."
                )
            self.load_and_prepare_data(data_path)
        else:
            print("Database is up-to-date, no need to reload GTFS data.")

    def get_agency_by_id(self, agency_id: str) -> Optional[Agency]:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agency WHERE agency_id = ?", (agency_id,))
        row = cursor.fetchone()
        conn.close()
        return Agency(**dict(row)) if row else None

    def get_route_by_id(self, route_id: str) -> Optional[Route]:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM routes WHERE route_id = ?", (route_id,))
        row = cursor.fetchone()
        conn.close()
        return Route(**dict(row)) if row else None

    def get_shape_by_id(self, shape_id: str) -> Optional[Shape]:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM shapes WHERE shape_id = ?", (shape_id,))
        row = cursor.fetchone()
        conn.close()
        return Shape(**dict(row)) if row else None

    def get_stop_time_by_id(
        self, trip_id: str, stop_id: str, stop_sequence: int
    ) -> Optional[StopTime]:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM stop_times WHERE trip_id = ? AND stop_id = ? AND stop_sequence = ?",
            (trip_id, stop_id, stop_sequence),
        )
        row = cursor.fetchone()
        conn.close()
        return StopTime(**dict(row)) if row else None

    def get_stop_by_id(self, stop_id: str) -> Optional[Stop]:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stops WHERE stop_id = ?", (stop_id,))
        row = cursor.fetchone()
        conn.close()
        return Stop(**dict(row)) if row else None

    def get_transfer_by_id(
        self, from_stop_id: str, to_stop_id: str
    ) -> Optional[Transfer]:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM transfers WHERE from_stop_id = ? AND to_stop_id = ?",
            (from_stop_id, to_stop_id),
        )
        row = cursor.fetchone()
        conn.close()
        return Transfer(**dict(row)) if row else None

    def get_trip_by_id(self, trip_id: str) -> Optional[Trip]:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trips WHERE trip_id = ?", (trip_id,))
        row = cursor.fetchone()
        conn.close()
        return Trip(**dict(row)) if row else None

    def get_stop_sequences(self, from_stop_id: str, to_stop_id: str, trip_id: str):
        """
        Get the stop sequences for the departure and arrival stops for a given trip.
        """
        conn, cursor = self.get_connection()
        cursor.execute(
            """
            SELECT stop_sequence
            FROM stop_times
            WHERE trip_id = ? AND stop_id IN (?, ?)
            ORDER BY stop_sequence
            """,
            (trip_id, from_stop_id, to_stop_id),
        )
        stop_sequences = cursor.fetchall()
        conn.close()
        if len(stop_sequences) != 2:
            raise ValueError(
                f"Expected exactly two stop sequences for trip {trip_id}, got {len(stop_sequences)}"
            )
        return stop_sequences[0][0], stop_sequences[1][0]
