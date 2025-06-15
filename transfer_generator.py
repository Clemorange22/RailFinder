from calendar import c
import sqlite3
import math
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from utils import geodistance_meters
from typing import TYPE_CHECKING
import concurrent.futures
import threading
import cProfile
import pstats

if TYPE_CHECKING:
    from database import Database

EXCLUDED_PREFIXES = ("IDFM", "de", "NSR", "cz", "ch", "pl")

DEBUG = False


class TransferGenerator:
    def __init__(
        self, db: "Database", max_distance_m=100, transfer_time_sec=120, batch_size=1000
    ):
        """
        This class handles the generation of transfers between close stops in a public transport network.
        It avoids creating transfers between stops that are too far apart or already have a transfer defined.
        It allows interoperability between different transport networks, especially for cross-border journeys.
        """
        self.db = db
        self.max_distance_m = max_distance_m
        self.transfer_time_sec = transfer_time_sec
        self.batch_size = batch_size
        self.db_write_lock = threading.Lock()

    def ensure_spatial_index(self):
        """
        Ensure the spatial index on stops is created and populated.
        This creates an R-tree index on the stop coordinates to speed up spatial queries.
        """
        conn, cur = self.db.get_connection()
        # Add stop_idx column to stops if it doesn't exist
        cur.execute("PRAGMA table_info(stops)")
        columns = [row[1] for row in cur.fetchall()]
        if "stop_idx" not in columns:
            cur.execute("ALTER TABLE stops ADD COLUMN stop_idx INTEGER")
            # Populate stop_idx with rowid for existing rows if not already set
            cur.execute("UPDATE stops SET stop_idx = rowid WHERE stop_idx IS NULL")
        else:
            # Ensure all stop_idx are set
            cur.execute("UPDATE stops SET stop_idx = rowid WHERE stop_idx IS NULL")
        # Create rtree index on stop_idx (integer)
        cur.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS stop_index USING rtree(
                id, min_lat, max_lat, min_lon, max_lon
            )
        """
        )
        # Always clear and repopulate to avoid UNIQUE constraint errors
        cur.execute("DELETE FROM stop_index")
        cur.execute(
            """
            INSERT INTO stop_index (id, min_lat, max_lat, min_lon, max_lon)
            SELECT stop_idx, stop_lat, stop_lat, stop_lon, stop_lon FROM stops WHERE stop_idx IS NOT NULL
            """
        )
        cur.execute(
            """CREATE INDEX IF NOT EXISTS idx_stops_stop_idx ON stops(stop_idx);
        """
        )
        conn.commit()
        conn.close()

    def latlon_bbox(self, lat, distance):
        """
        Calculate the latitude and longitude deltas for a square bounding box whose sides
        are approximately `distance` meters long at the given latitude.
        This uses the fact that 1 degree of latitude is approximately 111.32 km,
        and 1 degree of longitude varies with latitude.
        """
        delta_lat = distance / 111320
        delta_lon = distance / (40075000 * math.cos(math.radians(lat)) / 360)
        return delta_lat, delta_lon

    def process_chunk(self, args):
        """
        Process a chunk of stops to find potential transfers.
        This function is run in parallel for each chunk of stops.
        Args:
            args (tuple): A tuple containing:
                - stop_chunk: List of tuples (stop_id, lat, lon) for the chunk of stops
                - existing_transfers: Set of existing transfers to avoid duplicates
                - pbar: progress bar instance for updating progress
                - lock: threading lock for thread-safe updates to the progress bar
                - update_every: Number of stops after which to update the progress bar
        Returns:
            tuple: A tuple containing:
                - stops_processed: Number of stops processed in the chunk
                - insertions_total: Total number of new transfers found in this chunk
                - insertions: List of tuples (from_stop_id, to_stop_id) for new transfers
        """
        stop_chunk, existing_transfers, pbar, lock, update_every = args
        conn, cur = self.db.get_connection()
        insertions = set()
        stops_processed = 0
        insertions_total = 0
        insertions_since_pbar = 0
        batch_size = self.batch_size
        if DEBUG:
            # Only profile if this is the first thread (lowest thread ident among all threads)
            is_first_thread = (
                threading.current_thread().name == "ThreadPoolExecutor-0_0"
            )
            profiler = cProfile.Profile() if is_first_thread else None
            if profiler:
                profiler.enable()

        for i, (stop_id, lat, lon) in enumerate(stop_chunk, 1):
            delta_lat, delta_lon = self.latlon_bbox(lat, self.max_distance_m)
            candidates = cur.execute(
                """
                SELECT s2.stop_id, s2.stop_lat, s2.stop_lon
                FROM stop_index AS si
                JOIN stops AS s2 ON s2.stop_idx = si.id
                WHERE si.min_lat BETWEEN ? AND ? AND
                      si.min_lon BETWEEN ? AND ? AND
                      s2.stop_id != ?
                      AND NOT (
    (substr(s2.stop_id, 4) LIKE 'IDFM%' AND substr(?, 4) LIKE 'IDFM%')
 OR (substr(s2.stop_id, 4) LIKE 'de%'   AND substr(?, 4) LIKE 'de%')
 OR (substr(s2.stop_id, 4) LIKE 'NSR%'  AND substr(?, 4) LIKE 'NSR%')
 OR (substr(s2.stop_id, 4) LIKE 'cz%'   AND substr(?, 4) LIKE 'cz%')
 OR (substr(s2.stop_id, 4) LIKE 'ch%'   AND substr(?, 4) LIKE 'ch%')
 OR (substr(s2.stop_id, 4) LIKE 'pl%'   AND substr(?, 4) LIKE 'pl%')
)
                """,
                (
                    lat - delta_lat,
                    lat + delta_lat,
                    lon - delta_lon,
                    lon + delta_lon,
                    stop_id,
                    stop_id,  # for IDFM
                    stop_id,  # for de
                    stop_id,  # for NSR
                    stop_id,  # for cz
                    stop_id,  # for ch
                    stop_id,  # for pl
                ),
            ).fetchall()
            for other_id, other_lat, other_lon in candidates:
                if (stop_id, other_id) in existing_transfers or (
                    other_id,
                    stop_id,
                ) in existing_transfers:
                    continue
                dist = geodistance_meters(lat, lon, other_lat, other_lon)
                if dist <= self.max_distance_m:
                    insertions.add((min(stop_id, other_id), max(stop_id, other_id)))
                    insertions_total += 1
                    insertions_since_pbar += 1
            stops_processed += 1

            if DEBUG:
                # Print profiler stats every 100 stops for the first thread
                if profiler and stops_processed % 10 == 0:
                    profiler.disable()
                    print(
                        f"\n[Profiler] Stats after {stops_processed} stops (first thread):"
                    )
                    stats = pstats.Stats(profiler).sort_stats("cumtime")
                    stats.print_stats(10)
                    profiler.enable()

            if stops_processed % update_every == 0:
                with lock:
                    pbar.update(update_every)
                    pbar.set_postfix({"new transfers": insertions_since_pbar})
                insertions_since_pbar = 0

        conn.close()

        # Return all insertions for this chunk to be written in main thread
        return stops_processed, insertions_total, list(insertions)

    def chunkify(self, lst: list, n: int) -> list:
        """
        Split a list into n nearly equal chunks.

        Args:
            lst (list): list to be split
            n (int): number of chunks

        Returns:
            list: list of n chunks
        """
        k, m = divmod(len(lst), n)
        return [lst[i * k + min(i, m) : (i + 1) * k + min(i + 1, m)] for i in range(n)]

    def generate_transfers(self):
        """Generate transfers between stops that are close to each other."""
        self.ensure_spatial_index()
        conn, cur = self.db.get_connection()
        stops = cur.execute("SELECT stop_id, stop_lat, stop_lon FROM stops").fetchall()
        # Fetch all existing transfers ONCE
        cur.execute("SELECT from_stop_id, to_stop_id FROM transfers")
        existing_transfers = set(cur.fetchall())
        conn.close()
        nproc = cpu_count()
        print(f"Processing {len(stops)} stops across {nproc} threads...")
        lock = threading.Lock()
        update_every = 100
        chunks = self.chunkify(stops, nproc)
        total_stops = 0
        total_inserted = 0
        all_insertions = set()
        with tqdm(total=len(stops), desc="Stops processed") as pbar:
            with concurrent.futures.ThreadPoolExecutor(max_workers=nproc) as executor:
                futures = [
                    executor.submit(
                        self.process_chunk,
                        (chunk, existing_transfers, pbar, lock, update_every),
                    )
                    for chunk in chunks
                ]
                for future in concurrent.futures.as_completed(futures):
                    stops_processed, inserted, insertions = future.result()
                    total_stops += stops_processed
                    total_inserted += inserted
                    all_insertions.update(insertions)
        print(f"Writing {len(all_insertions)} transfers to database...")
        conn, cur = self.db.get_connection()
        cur.executemany(
            "INSERT OR IGNORE INTO transfers (from_stop_id, to_stop_id, transfer_type, min_transfer_time) VALUES (?, ?, 2, ?)",
            [(a, b, self.transfer_time_sec) for a, b in all_insertions]
            + [(b, a, self.transfer_time_sec) for a, b in all_insertions],
        )
        conn.commit()
        conn.close()
        print(f"Inserted {len(all_insertions) * 2} new transfers.")
