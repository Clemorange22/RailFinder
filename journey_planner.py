from ast import parse
from calendar import c
import datetime
import sqlite3
import time

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
        start_time = departure
        end_time = departure + time_delta
        weekday = start_time.strftime("%A").lower()

        sql = f"""
        SELECT 
            st2.stop_id,
            MIN(st2.arrival_time) AS earliest_arrival,
            trips.trip_id,
            stops.stop_lat,
            stops.stop_lon
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

    def parse_gtfs_time(
        self, date_reference: datetime.datetime, time_str: str
    ) -> datetime.datetime:
        """
        Parse a GTFS time string (HH:MM:SS) into a datetime object.
        A GTFS time string does not include a date, so we assume the date is today, unless the hour is more than 23.
        """
        today = date_reference.date()
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
        conn: sqlite3.Connection | None = None,
        cursor: sqlite3.Cursor | None = None,
    ) -> tuple:
        if conn is None or cursor is None:
            conn, cursor = self.db.get_connection()
        sql = """SELECT stop_lat, stop_lon FROM stops WHERE stop_id = ?"""
        cursor.execute(sql, (stop_id,))
        return cursor.fetchone()

    def heuristic(self, lat1, lon1, lat2, lon2, ride_number: int) -> float:
        ASSUMED_SPEED_KMH = 150  # Assumed speed in km/h for the heuristic
        TRANSFER_PENALTY_MINUTES = 5  # Transfer penalty in minutes
        return (
            geodistance(lat1, lon1, lat2, lon2) / ASSUMED_SPEED_KMH * 3600
            + ride_number * 60 * TRANSFER_PENALTY_MINUTES
        )

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
        max_transfers: int = -1,
    ):
        """
        Search for a journey from one stop to another with a maximum number of transfers.
        This uses a modified A* algorithm to find the shortest path based on time since the departure time.
        The path is represented as a list of tuples (stop_id, time, optional trip_id).
        If the trip_id is None, it means the stop is a transfer and the time is the arrival time at that stop.
        The heuristic is based on the geographical distance between the stops.
        It assumes a straight line distance in km, converted to time in seconds, with a speed of 60 km/h.
        """
        conn, cursor = self.db.get_connection()
        visited = set()
        previous = {}
        previous[(from_stop_id, departure)] = (from_stop_id, departure)
        final_lat, final_lon = self.get_stop_pos(to_stop_id, conn, cursor)
        priority_queue = [
            (0, from_stop_id, departure, 0)
        ]  # (cost, stop_id, time, ride_number)
        earliest_arrival = {from_stop_id: departure}
        heapq.heapify(priority_queue)
        found = False

        neighbor_search_window = datetime.timedelta(hours=1)
        while len(priority_queue) > 0 and not found:
            u = heapq.heappop(priority_queue)
            current_stop_id = u[1]
            current_time = u[2]
            current_ride_number = u[3]
            if max_transfers >= 0 and current_ride_number > max_transfers + 1:
                continue
            if current_stop_id == to_stop_id:
                found = True
            else:
                for v in self.get_neighbors_stop_times(
                    current_stop_id,
                    current_time,
                    neighbor_search_window,
                    limit=-1,
                    conn=conn,
                    cursor=cursor,
                ):
                    v_datetime = self.parse_gtfs_time(current_time, v[1])
                    if (v[0], v_datetime) not in visited and (
                        v_datetime < earliest_arrival.get(v[0], datetime.datetime.max)
                    ):
                        vlat = v[3]
                        vlon = v[4]
                        trip_id = v[2]
                        visited.add((v[0], v_datetime))
                        previous[(v[0], v_datetime)] = (
                            current_stop_id,
                            current_time,
                            trip_id,
                        )
                        earliest_arrival[v[0]] = v_datetime
                        h = self.heuristic(
                            vlat, vlon, final_lat, final_lon, current_ride_number + 1
                        )
                        cost = int((v_datetime - departure).total_seconds() + h)
                        heapq.heappush(
                            priority_queue,
                            (cost, v[0], v_datetime, current_ride_number + 1),
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
                        h = self.heuristic(
                            tlat, tlon, final_lat, final_lon, current_ride_number
                        )
                        cost = int((t_datetime - departure).total_seconds() + h)
                        heapq.heappush(
                            priority_queue,
                            (
                                cost,
                                t[1],
                                t_datetime,
                                current_ride_number,  # Do not increment ride number for transfers
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
        path.insert(0, current)
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
        The times in the path are arrival times; departure_time should be fetched from the database.
        """
        if not path or len(path) < 2:
            return []
        journey_steps = []
        db = self.db
        for i in range(len(path) - 1):
            from_stop_id = path[i][0]
            from_arrival_time = path[i][1]
            to_stop_id = path[i + 1][0]
            to_arrival_time = path[i + 1][1]
            trip_id = path[i][2] if len(path[i]) > 2 else None

            from_stop = db.get_stop_by_id(from_stop_id)
            to_stop = db.get_stop_by_id(to_stop_id)
            from_stop_name = from_stop.stop_name if from_stop else ""
            from_stop_lat = from_stop.stop_lat if from_stop else 0.0
            from_stop_lon = from_stop.stop_lon if from_stop else 0.0
            to_stop_name = to_stop.stop_name if to_stop else ""
            to_stop_lat = to_stop.stop_lat if to_stop else 0.0
            to_stop_lon = to_stop.stop_lon if to_stop else 0.0
            arrival_time = to_arrival_time.strftime("%H:%M:%S")
            route_id = None
            route_short_name = None
            route_long_name = None
            trip_headsign = None
            transfer = trip_id is None
            transfer_time = None

            if trip_id:
                trip = db.get_trip_by_id(trip_id)
                route_id = trip.route_id if trip else None
                route_short_name = trip.route_short_name if trip else None
                route = db.get_route_by_id(route_id) if route_id else None
                route_long_name = route.route_long_name if route else None
                trip_headsign = trip.trip_headsign if trip else None
                # Get departure time from the database (since path times are arrivals)
                departure_time = self.get_next_departure(
                    from_stop_id, trip_id, from_arrival_time
                )
                if departure_time is None:
                    departure_time = from_arrival_time.strftime("%H:%M:%S")
            else:
                # Transfer: compute transfer time if possible
                transfer_time = int(
                    (to_arrival_time - from_arrival_time).total_seconds()
                )
                departure_time = from_arrival_time.strftime("%H:%M:%S")
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
                    trip_headsign=trip_headsign,
                    transfer=transfer,
                    transfer_time=transfer_time,
                )
            )
        # Remove the first step if its stop name is the same as the second step's stop name
        while (
            len(journey_steps) > 1
            and journey_steps[0].from_stop_name == journey_steps[1].from_stop_name
        ):
            journey_steps.pop(0)
        # Remove the last step if its stop name is the same as the second to last step's stop name
        while (
            len(journey_steps) > 1
            and journey_steps[-1].to_stop_name == journey_steps[-2].to_stop_name
        ):
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
                    route_name = (
                        step.route_short_name or step.route_long_name or "Unknown Route"
                    )
                    summary.append(
                        f"---------------------------------------------------------------------\n"
                        f"Ride on {route_name} ({step.route_id}) from {step.from_stop_name} ({step.from_stop_id}) to {step.to_stop_name} ({step.to_stop_id}).\n"
                        f"Trip {step.trip_headsign}, departing at {step.departure_time} and arriving at {step.arrival_time}"
                    )
            end_step = journey_steps[-1]
            summary.append(
                f"End at {end_step.to_stop_name} ({end_step.to_stop_id}) at {end_step.arrival_time}"
            )
        return "\n".join(summary) if summary else "No journey steps available."
