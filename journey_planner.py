from ast import parse
from calendar import c
import datetime
import sqlite3

from database import Database
from models import StopTime, Stop, Transfer, Trip, JourneyStep
import heapq
from math import radians, sin, cos, sqrt, atan2


class JourneyPlanner:
    def __init__(self, db: Database):
        self.db = db

    def search_stop(self, name: str, limit: int = 10):
        """
        Get all stops from the database.
        """
        conn, cursor = self.db.get_connection()
        cursor.execute(
            "SELECT stop_id, stop_name FROM stops WHERE stop_name LIKE ? ORDER BY (stop_name LIKE ?) DESC LIMIT ?",
            (f"{name}%", f"%{name}%", limit),
        )  # TODO: Sort by relevance using the source of the stop: train, bus, tram
        stops = cursor.fetchall()
        conn.close()
        return stops

    def list_departures(
        self,
        stop_id: str,
        date: datetime.datetime,
        time_delta: datetime.timedelta,
        limit: int = 10,
    ):
        """
        Get all departures from a stop in a given time range.
        """
        conn, cursor = self.db.get_connection()
        start_time = date + time_delta
        end_time = start_time + datetime.timedelta(hours=1)
        weekday = start_time.strftime("%A").lower()
        sql = f"""
        SELECT DISTINCT stop_times.trip_id, stop_times.arrival_time, stop_times.departure_time, routes.route_short_name, routes.route_long_name, trips.trip_headsign
        FROM stop_times
        JOIN trips ON stop_times.trip_id = trips.trip_id
        JOIN routes ON trips.route_id = routes.route_id
        WHERE stop_times.stop_id = ?
          AND stop_times.departure_time BETWEEN ? AND ?
          AND (
            (
              trips.service_id IN (
                SELECT service_id FROM calendar
                WHERE ? BETWEEN start_date AND end_date
                  AND {weekday} = 1
              )
              AND trips.service_id NOT IN (
                SELECT service_id FROM calendar_dates
                WHERE date = ? AND exception_type = 2
              )
            )
            OR trips.service_id IN (
              SELECT service_id FROM calendar_dates
              WHERE date = ? AND exception_type = 1
            )
          )
        ORDER BY stop_times.arrival_time
        LIMIT ?
        """

        cursor.execute(
            sql,
            (
                stop_id,
                start_time.strftime("%H:%M:%S"),
                end_time.strftime("%H:%M:%S"),
                start_time.strftime("%Y%m%d"),
                start_time.strftime("%Y%m%d"),
                start_time.strftime("%Y%m%d"),
                limit,
            ),
        )
        departures = cursor.fetchall()
        conn.close()
        return departures

    def get_neighbors_stop_times(
        self,
        from_stop_id: str,
        departure: datetime.datetime,
        time_delta: datetime.timedelta,
        limit: int = 10,
        conn: sqlite3.Connection | None = None,
        cursor: sqlite3.Cursor | None = None,
    ):
        """
        Find all next stop_times reachable from the given stop and time, on valid trips.
        """
        if conn is None or cursor is None:
            conn, cursor = self.db.get_connection()
            close_conn = True
        else:
            close_conn = False
        start_time = departure + time_delta
        end_time = start_time + datetime.timedelta(hours=1)
        weekday = start_time.strftime("%A").lower()

        sql = f"""
        SELECT 
            st2.stop_id,
            MIN(st2.arrival_time) AS earliest_arrival,
            trips.trip_id,
            stops.stop_lat,
            stops.stop_lon,
            st2.trip_id
        FROM stop_times AS st1
        JOIN stop_times AS st2 
            ON st1.trip_id = st2.trip_id 
            AND st2.stop_sequence > st1.stop_sequence
        JOIN trips ON st1.trip_id = trips.trip_id
        JOIN stops ON st2.stop_id = stops.stop_id
        WHERE st1.stop_id = ?
          AND st1.departure_time BETWEEN ? AND ?
          AND (
            (
              trips.service_id IN (
                SELECT service_id FROM calendar
                WHERE ? BETWEEN start_date AND end_date
                  AND {weekday} = 1
              )
              AND trips.service_id NOT IN (
                SELECT service_id FROM calendar_dates
                WHERE date = ? AND exception_type = 2
              )
            )
            OR trips.service_id IN (
              SELECT service_id FROM calendar_dates
              WHERE date = ? AND exception_type = 1
            )
          )
        GROUP BY st2.stop_id, stops.stop_lat, stops.stop_lon
        LIMIT ?
        """

        cursor.execute(
            sql,
            (
                from_stop_id,
                start_time.strftime("%H:%M:%S"),
                end_time.strftime("%H:%M:%S"),
                start_time.strftime("%Y%m%d"),
                start_time.strftime("%Y%m%d"),
                start_time.strftime("%Y%m%d"),
                limit,
            ),
        )
        neighbors_stop_times = cursor.fetchall()
        if close_conn:
            conn.close()
        return neighbors_stop_times

    def get_transfers(
        self,
        from_stop_id: str,
        max_duration: int = 3600,
        conn: sqlite3.Connection | None = None,
        cursor: sqlite3.Cursor | None = None,
    ):
        """
        Get all transfers from a stop within a maximum duration.
        """
        if conn is None or cursor is None:
            conn, cursor = self.db.get_connection()
            close_conn = True
        else:
            close_conn = False
        sql = """
        SELECT 
            t.from_stop_id, 
            t.to_stop_id, 
            t.min_transfer_time
        FROM transfers AS t
        JOIN stops AS s1 ON t.from_stop_id = s1.stop_id
        JOIN stops AS s2 ON t.to_stop_id = s2.stop_id
        WHERE t.from_stop_id = ? AND t.min_transfer_time <= ?
        """
        cursor.execute(sql, (from_stop_id, max_duration))
        transfers = cursor.fetchall()
        if close_conn:
            conn.close()
        return transfers

    def parse_gtfs_time(self, time_str: str) -> datetime.datetime:
        """
        Parse a GTFS time string (HH:MM:SS) into a datetime object.
        A GTFS time string does not include a date, so we assume the date is today, unless the hour is more than 23.
        """
        today = datetime.datetime.now().date()
        time_parts = time_str.split(":")
        if len(time_parts) == 3:
            hour, minute, second = map(int, time_parts)
            if hour > 23:
                # If the hour is more than 23, we assume it's the next day
                return datetime.datetime.combine(
                    today + datetime.timedelta(days=1),
                    datetime.time(hour - 24, minute, second),
                )
            return datetime.datetime.combine(today, datetime.time(hour, minute, second))
        raise ValueError("Invalid GTFS time format. Expected HH:MM:SS.")

    def geodistance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """
        Calculate the distance between two stops using their latitude and longitude.
        This uses the Haversine formula to calculate the distance in kilometers.
        """

        R = 6371.0
        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = R * c
        return distance

    def get_stop_pos(
        self,
        stop_id: str,
        conn: sqlite3.Connection | None,
        cursor: sqlite3.Cursor | None,
    ) -> tuple:
        if conn is None or cursor is None:
            conn, cursor = self.db.get_connection()
        sql = """SELECT stop_lat, stop_lon FROM stops WHERE stop_id = ?"""
        cursor.execute(sql, (stop_id,))
        return cursor.fetchone()

    def heuristic(self, lat1, lon1, lat2, lon2):
        return self.geodistance(lat1, lon1, lat2, lon2) / 60 * 3600

    def get_node(self, t: tuple):
        """
        Extract the stop_id and time from a tuple.
        """
        return t[0], t[1]

    def journey_search(
        self,
        from_stop_id: str,
        to_stop_id: str,
        departure: datetime.datetime,
        departure_time_delta: datetime.timedelta,
        max_transfers: int = 5,
    ):
        """
        Search for a journey from one stop to another with a maximum number of transfers.
        """
        conn, cursor = self.db.get_connection()
        visited = set()
        previous = {}
        previous[(from_stop_id, departure)] = (from_stop_id, departure)
        final_lat, final_lon = self.get_stop_pos(to_stop_id, conn, cursor)
        priority_queue = [(0, from_stop_id, departure)]
        heapq.heapify(priority_queue)
        found = False
        while len(priority_queue) > 0 and not found:
            u = heapq.heappop(priority_queue)
            current_stop_id = u[1]
            current_time = u[2]
            if current_stop_id == to_stop_id:
                found = True
            else:
                for v in self.get_neighbors_stop_times(
                    current_stop_id,
                    current_time,
                    datetime.timedelta(minutes=30),
                    conn=conn,
                    cursor=cursor,
                ):
                    v_datetime = self.parse_gtfs_time(v[1])
                    if (v[0], v_datetime) not in visited:

                        vlat = v[3]
                        vlon = v[4]
                        trip_id = v[5]
                        visited.add((v[0], v_datetime))
                        previous[(v[0], v_datetime)] = (
                            current_stop_id,
                            current_time,
                            trip_id,
                        )
                        h = self.heuristic(vlat, vlon, final_lat, final_lon)

                        heapq.heappush(
                            priority_queue,
                            (
                                round((v_datetime - departure).total_seconds() + h),
                                v[0],
                                v_datetime,
                            ),
                        )

                for t in self.get_transfers(current_stop_id, -1, conn, cursor):
                    t_datetime = current_time + datetime.timedelta(seconds=t[2])
                    if (t[1], t_datetime) not in visited:
                        visited.add((t[1], t_datetime))
                        tlat, tlon = self.get_stop_pos(t[1], conn, cursor)
                        previous[(t[1], t_datetime)] = (
                            current_stop_id,
                            current_time,
                            None,
                        )
                        h = self.heuristic(tlat, tlon, final_lat, final_lon)
                        heapq.heappush(
                            priority_queue,
                            (
                                round((t_datetime - departure).total_seconds() + h),
                                t[1],
                                t_datetime,
                            ),
                        )

        conn.close()
        if not found:
            print("No journey found.")
            return None
        # Reconstruct the path
        path = []
        current = (current_stop_id, current_time)
        while previous[self.get_node(current)] != self.get_node(current):
            path.insert(0, current)
            current = previous[self.get_node(current)]

        path.insert(0, previous[self.get_node(current)])
        return path

    def get_journey_details(self, path: list):
        """Take a path and return the details of the journey as a list of JourneyStep objects.
        Each step in the path is a tuple of (stop_id, time, optional trip_id).
        The trip_id is None if the step is a transfer.
        If present the trip_id is the id of the trip that leads to this stop.
        """
        if not path or len(path) < 2:
            return []
        journey_steps = []
        db = self.db
        for i, step in enumerate(path):
            stop_id: str = step[0]
            time: datetime.datetime = step[1]
            trip_id: str | None = step[2] if len(step) > 2 else None
            stop = db.get_stop_by_id(stop_id)
            stop_name = stop.stop_name if stop else ""
            stop_lat = stop.stop_lat if stop else 0.0
            stop_lon = stop.stop_lon if stop else 0.0
            arrival_time = time.strftime("%H:%M:%S")
            departure_time = None
            route_id = None
            route_short_name = None
            route_long_name = None
            transfer = trip_id is None
            transfer_time = None
            if trip_id:
                trip = db.get_trip_by_id(trip_id)
                route_id = trip.route_id if trip else None
                route_short_name = trip.route_short_name if trip else None
                route = db.get_route_by_id(route_id) if route_id else None
                route_long_name = route.route_long_name if route else None
                # Set departure_time if previous step is same trip
                if i > 0 and len(path[i - 1]) > 2 and path[i - 1][2] == trip_id:
                    prev_time = path[i - 1][1]
                    departure_time = prev_time.strftime("%H:%M:%S")
            else:
                # Transfer: compute transfer time if possible
                if i > 0:
                    prev_time: datetime.datetime = path[i - 1][1]
                    transfer_time = int((time - prev_time).total_seconds())
            journey_steps.append(
                JourneyStep(
                    stop_id=stop_id,
                    stop_name=stop_name,
                    stop_lat=stop_lat,
                    stop_lon=stop_lon,
                    arrival_time=arrival_time,
                    departure_time=departure_time,
                    trip_id=trip_id,
                    route_id=route_id,
                    route_short_name=route_short_name,
                    route_long_name=route_long_name,
                    transfer=transfer,
                    transfer_time=transfer_time,
                )
            )
        return journey_steps
