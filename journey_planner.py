from ast import parse
from calendar import c
import datetime
import sqlite3

from database import Database
from models import StopTime, Stop, Transfer, Trip, JourneyStep
import heapq
from math import radians, sin, cos, sqrt, atan2
from utils import geodistance


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
        return geodistance(lat1, lon1, lat2, lon2) / 60 * 3600

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
        earliest_arrival = {from_stop_id: departure}
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
                    limit=-1,
                    conn=conn,
                    cursor=cursor,
                ):
                    v_datetime = self.parse_gtfs_time(v[1])
                    if (v[0], v_datetime) not in visited and (
                        v_datetime < earliest_arrival.get(v[0], datetime.datetime.max)
                    ):

                        vlat = v[3]
                        vlon = v[4]
                        trip_id = v[5]
                        visited.add((v[0], v_datetime))
                        previous[(v[0], v_datetime)] = (
                            current_stop_id,
                            current_time,
                            trip_id,
                        )
                        earliest_arrival[v[0]] = v_datetime
                        h = self.heuristic(vlat, vlon, final_lat, final_lon)

                        heapq.heappush(
                            priority_queue,
                            (
                                round((v_datetime - departure).total_seconds() + h),
                                v[0],
                                v_datetime,
                            ),
                        )

                for t in self.get_transfers(current_stop_id, conn=conn, cursor=cursor):
                    t_datetime = current_time + datetime.timedelta(seconds=t[2])
                    if (t[1], t_datetime) not in visited and (
                        t_datetime < earliest_arrival.get(t[1], datetime.datetime.max)
                    ):
                        visited.add((t[1], t_datetime))
                        tlat, tlon = self.get_stop_pos(t[1], conn, cursor)
                        previous[(t[1], t_datetime)] = (
                            current_stop_id,
                            current_time,
                            None,
                        )
                        earliest_arrival[t[1]] = t_datetime
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
            return None
        # Reconstruct the path
        path = []
        current = (current_stop_id, current_time)
        while previous[self.get_node(current)] != self.get_node(current):
            path.insert(0, current)
            current = previous[self.get_node(current)]

        # Fix: ensure the first step has the correct trip_id
        first = previous[self.get_node(current)]
        # If the first step is missing trip_id, infer it from the next step
        if len(first) == 2 and len(path) > 0 and len(path[0]) > 2:
            first = (first[0], first[1], path[0][2])
        elif len(first) == 2:
            first = (first[0], first[1], None)
        path.insert(0, first)
        return path

    def get_next_departure(
        self,
        stop_id: str,
        trip_id: str,
        arrival_time: datetime.datetime,
        conn: sqlite3.Connection | None = None,
        cursor: sqlite3.Cursor | None = None,
    ):
        """
        Get the next departure from a stop after a given arrival time on a specific trip.
        """
        if conn is None or cursor is None:
            conn, cursor = self.db.get_connection()
            close_conn = True
        else:
            close_conn = False
        sql = """
        SELECT departure_time 
        FROM stop_times 
        WHERE stop_id = ? AND trip_id = ? AND arrival_time > ?
        ORDER BY arrival_time ASC
        LIMIT 1
        """
        cursor.execute(sql, (stop_id, trip_id, arrival_time.strftime("%H:%M:%S")))
        result = cursor.fetchone()
        if close_conn:
            conn.close()
        return result[0] if result else None

    def get_journey_details(self, path: list):
        """Take a path and return the details of the journey as a list of JourneyStep objects.
        Each step in the path is a tuple of (stop_id, time, optional trip_id).
        The trip_id is the id of the trip that departs from this stop (i.e., the trip after this stop),
        except for the last stop, which has trip_id=None unless it's a transfer.
        """
        if not path or len(path) < 2:
            return []
        journey_steps = []
        db = self.db
        for i in range(len(path) - 1):
            from_stop_id = path[i][0]
            from_time = path[i][1]
            to_stop_id = path[i + 1][0]
            to_time = path[i + 1][1]
            trip_id = path[i][2] if len(path[i]) > 2 else None

            from_stop = db.get_stop_by_id(from_stop_id)
            to_stop = db.get_stop_by_id(to_stop_id)
            from_stop_name = from_stop.stop_name if from_stop else ""
            from_stop_lat = from_stop.stop_lat if from_stop else 0.0
            from_stop_lon = from_stop.stop_lon if from_stop else 0.0
            to_stop_name = to_stop.stop_name if to_stop else ""
            to_stop_lat = to_stop.stop_lat if to_stop else 0.0
            to_stop_lon = to_stop.stop_lon if to_stop else 0.0
            departure_time = from_time.strftime("%H:%M:%S")
            arrival_time = to_time.strftime("%H:%M:%S")
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
            else:
                # Transfer: compute transfer time if possible
                transfer_time = int((to_time - from_time).total_seconds())
            journey_steps.append(
                JourneyStep(
                    from_stop_id=from_stop_id,
                    from_stop_name=from_stop_name,
                    from_stop_lat=from_stop_lat,
                    from_stop_lon=from_stop_lon,
                    to_stop_id=to_stop_id,
                    to_stop_name=to_stop_name,
                    to_stop_lat=to_stop_lat,
                    to_stop_lon=to_stop_lon,
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    trip_id=trip_id,
                    route_id=route_id,
                    route_short_name=route_short_name,
                    route_long_name=route_long_name,
                    transfer=transfer,
                    transfer_time=transfer_time,
                )
            )
        # Remove leading and trailing transfers if any
        while len(journey_steps) > 0 and journey_steps[0].transfer:
            journey_steps.pop(0)
        while len(journey_steps) > 0 and journey_steps[-1].transfer:
            journey_steps.pop()
        return journey_steps

    def get_journey_summary(self, journey_steps: list[JourneyStep]):
        summary = []
        if journey_steps:
            start_step = journey_steps[0]
            summary.append(
                f"Start at {start_step.from_stop_name} ({start_step.from_stop_id}) at {start_step.departure_time}"
            )
            for step in journey_steps:
                if step.transfer:
                    summary.append(
                        f"Transfer from {step.from_stop_name} ({step.from_stop_id}) to {step.to_stop_name} ({step.to_stop_id}) during {step.transfer_time} seconds"
                    )
                else:
                    summary.append(
                        f"Ride on {step.route_short_name} ({step.route_id}) from {step.from_stop_name} ({step.from_stop_id}) to {step.to_stop_name} ({step.to_stop_id}) "
                        f"departing at {step.departure_time} and arriving at {step.arrival_time}"
                    )
            end_step = journey_steps[-1]
            summary.append(
                f"End at {end_step.to_stop_name} ({end_step.to_stop_id}) at {end_step.arrival_time}"
            )
        return summary
