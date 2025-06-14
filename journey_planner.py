from calendar import c
import datetime
import re
import sqlite3
from turtle import st
from typing import Literal
import tkinter as tk
import pytz


from database import Database
from models import JourneyStep
import heapq
from utils import geodistance


class JourneyPlanner:
    def __init__(self, db: Database):
        self.db = db
        self._last_date = None

    def search_stop(self, name: str, limit: int = 10):
        """
        Get all stops that match the given name.
        This searches for stops whose names start with the given name, sorted by relevance.
        The relevance is determined by how closely the stop name matches the search term.
        """
        conn, cursor = self.db.get_connection()
        cursor.execute(
            "SELECT stop_id, stop_name FROM stops WHERE stop_name LIKE ? ORDER BY (stop_name LIKE ?) DESC LIMIT ?",
            (f"{name}%", f"%{name}%", limit),
        )  # TODO: Sort by relevance using the source of the stop: train, bus, tram
        stops = cursor.fetchall()
        conn.close()
        return stops

    def search_stop_custom(self, name: str, limit: int = 10):
        """
        Get all stops that match the given name using a custom ranking algorithm.
        This intends to improve the relevance of the search results, especially for stops with similar names.
        """
        stops = self.search_stop(name, limit)
        cities_exceptions = {
            "Paris": {"should_have_prefix": ["IDFM"], "should_not_have_prefix": []},
            "Lyon": {"should_have_prefix": [], "should_not_have_prefix": ["IDFM"]},
        }

        # Apply custom sorting based on cities_exceptions
        for city, criteria in cities_exceptions.items():
            if name.startswith(city):
                should_have_prefix = criteria["should_have_prefix"]
                should_not_have_prefix = criteria["should_not_have_prefix"]

                def custom_sort(stop):
                    stop_id = stop[0]
                    if any(stop_id.startswith(prefix) for prefix in should_have_prefix):
                        return 0  # High priority
                    if any(
                        stop_id.startswith(prefix) for prefix in should_not_have_prefix
                    ):
                        return 2  # Low priority
                    return 1  # Medium priority

                stops.sort(key=custom_sort)
                break

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
        Precompute valid service IDs for the given date and time, this has improved performance by 351%
        """
        if conn is None or cursor is None:
            conn, cursor = self.db.get_connection()
            close_conn = True
        else:
            close_conn = False
        start_time = departure
        end_time = departure + time_delta
        weekday = start_time.strftime("%A").lower()

        # Track the current date
        current_date = start_time.date()

        # If the temporary table doesn't exist or the date has changed, recreate it
        if self._last_date != current_date:
            cursor.execute("DROP TABLE IF EXISTS valid_service_ids")
            weekday = start_time.strftime("%A").lower()
            cursor.execute(
                f"""
                CREATE TEMP TABLE valid_service_ids AS
                SELECT service_id
                FROM calendar
                WHERE ? BETWEEN start_date AND end_date AND {weekday} = 1
                UNION
                SELECT service_id
                FROM calendar_dates
                WHERE date = ? AND exception_type = 1
                EXCEPT
                SELECT service_id
                FROM calendar_dates
                WHERE date = ? AND exception_type = 2;
                """,
                (
                    start_time.strftime("%Y%m%d"),
                    start_time.strftime("%Y%m%d"),
                    start_time.strftime("%Y%m%d"),
                ),
            )
            cursor.execute(
                "CREATE INDEX idx_valid_service_ids ON valid_service_ids(service_id);"
            )
            self._last_date = current_date

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
          AND trips.service_id IN valid_service_ids
        GROUP BY st2.stop_id
        LIMIT ?
        """

        # Debug: Print the query plan
        """cursor.execute(f"EXPLAIN QUERY PLAN {sql}", (
            from_stop_id,
            start_time.strftime("%H:%M:%S"),
            end_time.strftime("%H:%M:%S"),
            start_time.strftime("%Y%m%d"),
            start_time.strftime("%Y%m%d"),
            start_time.strftime("%Y%m%d"),
            limit,
        ))
        print("Query Plan:", cursor.fetchall())"""

        cursor.execute(
            sql,
            (
                from_stop_id,
                start_time.strftime("%H:%M:%S"),
                end_time.strftime("%H:%M:%S"),
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
    ) -> datetime.datetime | None:
        """
        Parse a GTFS time string (HH:MM:SS) into a datetime object.
        A GTFS time string does not include a date, so we assume the date is today, unless the hour exceeds 23.
        If the hour exceeds 23, we calculate the number of days to add and adjust the hour accordingly.
        """
        today = date_reference.date()
        time_parts = time_str.split(":")
        if len(time_parts) == 3:
            hour, minute, second = map(int, time_parts)
            if hour > 23:
                # Calculate the number of days to add and adjust the hour
                days_to_add = hour // 24
                adjusted_hour = hour % 24
                return datetime.datetime.combine(
                    today + datetime.timedelta(days=days_to_add),
                    datetime.time(adjusted_hour, minute, second),
                )
            return datetime.datetime.combine(today, datetime.time(hour, minute, second))
        return None
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

    def heuristic(
        self,
        lat1,
        lon1,
        lat2,
        lon2,
        ride_number: int,
        transfert_duration: int,
        mode_int: int = 0,
    ) -> float:
        """
        Heuristic function for the A* algorithm.
        This function calculates the heuristic cost based on the geographical distance between the current stop and the destination stop.
        It assumes a straight line distance in km, converted to time in seconds, with a speed of 60 km/h.
        The ride_number is used to add a penalty for each ride, and the transfert_duration is used to add a penalty for transfers.
        The mode_int parameter is used to differentiate between the two modes of the journey search, where 0 is for the fastest route and 1 is for the least transfers.
        """
        if mode_int not in [0, 1]:
            raise ValueError(
                f"Invalid mode_int: {mode_int}. Must be 0 (fastest) or 1 (least transfers)."
            )
        ASSUMED_SPEED_KMH = 100
        distance_km = geodistance(
            lat1, lon1, lat2, lon2
        )  # Distance between current stop and destination stop

        # Adjust ride penalty dynamically based on the number of rides
        RIDE_PENALTY_MINUTES_BASE = 3 if mode_int == 0 else 5
        RIDE_PENALTY_ADJUSTMENT_FACTOR = 1 + (
            ride_number / 10
        )  # Increase penalty for more rides
        adjusted_ride_penalty_minutes = (
            RIDE_PENALTY_MINUTES_BASE * RIDE_PENALTY_ADJUSTMENT_FACTOR
        )

        # Scale transfer duration penalty based on total journey distance

        TRANSFER_PENALTY_MULTIPLIER = 1.5 if mode_int == 0 else 2.0
        h_convenience = (
            ride_number * 60 * adjusted_ride_penalty_minutes
            + transfert_duration * TRANSFER_PENALTY_MULTIPLIER
        )

        return distance_km / ASSUMED_SPEED_KMH * 3600 + h_convenience

    def get_node(self, t: tuple):
        """
        Extract the stop_id and time from a tuple.
        """
        return t[0], t[1]

    def update_gui(self, gui, path: list[tuple[float, float]]):
        """
        Update the GUI with the current state of the journey search.
        If a GUI is provided, it will update the marker position and redraw the map.
        """
        journey_steps = self.get_journey_details(path)
        geometry = self.get_journey_geometry(journey_steps)
        gui.map_canvas.delete_all_path()
        gui.map_canvas.set_path(geometry, color="purple", width=3)

    def journey_search(
        self,
        from_stop_id: str,
        to_stop_id: str,
        departure: datetime.datetime,
        mode: 'Literal["fastest", "least_transfers"]' = "fastest",
        max_rides: int = -1,
        max_execution_time_seconds: int = 60,
        gui=None,
    ):
        """
        Search for a journey from one stop to another with a maximum number of transfers.
        This uses a modified A* algorithm to find the shortest path based on time since the departure time.
        The path is represented as a list of tuples (stop_id, time, optional trip_id).
        If the trip_id is None, it means the stop is a transfer and the time is the arrival time at that stop.
        The heuristic is based on the geographical distance between the stops.
        It assumes a straight line distance in km, converted to time in seconds, with constant speed.
        """
        if mode not in ["fastest", "least_transfers"]:
            raise ValueError(
                f"Invalid mode: {mode}. Must be 'fastest' or 'least_transfers'."
            )

        if mode == "least_transfers":
            max_rides = 5
            mode_int = 1
        else:
            max_rides = 20
            mode_int = 0
        start_execution_time = datetime.datetime.now()
        conn, cursor = self.db.get_connection()

        # Increase cache size and use memory for temporary tables, improves performance by ~200%
        cursor.execute("PRAGMA cache_size = 20000")
        cursor.execute("PRAGMA temp_store = MEMORY")

        visited = set()
        previous = {}
        previous[(from_stop_id, departure)] = (from_stop_id, departure)
        start_pos = self.get_stop_pos(from_stop_id)
        if not start_pos:
            return None, 0.0
        stop_pos = self.get_stop_pos(to_stop_id, conn, cursor)
        if not stop_pos:
            return None, 0.0
        final_lat, final_lon = stop_pos

        if gui:
            gui.master.after(0, gui.map_canvas.set_zoom, 5)
            # calculate the medium position of the two stops
            if start_pos:
                start_lat, start_lon = start_pos
                gui.master.after(
                    0,
                    gui.map_canvas.set_position,
                    (final_lat + start_lat) / 2,
                    (final_lon + start_lon) / 2,
                )

                zoom_level = 6

                gui.master.after(0, gui.map_canvas.set_zoom, zoom_level)

        priority_queue = [
            (0, from_stop_id, departure, 0, 0)
        ]  # (cost, stop_id, time, ride_count, transfert_duration)
        earliest_arrival = {from_stop_id: departure}
        best_cost = {from_stop_id: 0}  # Track the best cost to each stop
        heapq.heapify(priority_queue)
        found = False

        nodes_processed = 0

        neighbor_search_window = datetime.timedelta(hours=5)
        update_start_time = datetime.datetime.now()
        while len(priority_queue) > 0 and not found:
            if (
                nodes_processed % 1000 == 0
                and datetime.datetime.now() - start_execution_time
                > datetime.timedelta(seconds=max_execution_time_seconds)
            ):
                break
            u = heapq.heappop(priority_queue)
            current_cost = u[0]
            current_stop_id = u[1]
            current_time = u[2]
            current_ride_count = u[3]
            current_transfert_duration = u[4]

            if gui and datetime.datetime.now() - update_start_time > datetime.timedelta(
                milliseconds=40
            ):
                path = self.reconstruct_path(previous, current_stop_id, current_time)

                gui.master.after(
                    0,
                    self.update_gui,
                    gui,
                    path,
                )
                update_start_time = datetime.datetime.now()

            # Skip if this path is not optimal
            if current_cost > best_cost.get(current_stop_id, float("inf")):
                continue

            if max_rides >= 0 and current_ride_count > max_rides + 1:
                continue

            """print(
                f"Processing node {nodes_processed}: {current_stop_id} at {current_time.strftime('%H:%M:%S')} with cost {current_cost}, ride count {current_ride_count}, transfer duration {current_transfert_duration}"
            )"""
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
                    if not v_datetime:
                        continue
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
                            vlat,
                            vlon,
                            final_lat,
                            final_lon,
                            current_ride_count + 1,
                            current_transfert_duration,
                            mode_int=mode_int,
                        )
                        cost = int((v_datetime - departure).total_seconds() + h)
                        # Update best cost and push to queue
                        if cost < best_cost.get(v[0], float("inf")):
                            best_cost[v[0]] = cost
                            heapq.heappush(
                                priority_queue,
                                (
                                    cost,
                                    v[0],
                                    v_datetime,
                                    current_ride_count + 1,
                                    current_transfert_duration,
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
                        h = self.heuristic(
                            tlat,
                            tlon,
                            final_lat,
                            final_lon,
                            current_ride_count,
                            current_transfert_duration + t[2],
                            mode_int=mode_int,
                        )
                        cost = int((t_datetime - departure).total_seconds() + h)
                        # Update best cost and push to queue
                        if cost < best_cost.get(t[1], float("inf")):
                            best_cost[t[1]] = cost
                            heapq.heappush(
                                priority_queue,
                                (
                                    cost,
                                    t[1],
                                    t_datetime,
                                    current_ride_count,
                                    current_transfert_duration + t[2],
                                ),
                            )
            nodes_processed += 1
        conn.close()
        self._last_date = None  # Reset last date after search
        if not found:
            execution_time_seconds = (
                datetime.datetime.now() - start_execution_time
            ).total_seconds()
            return None, execution_time_seconds
        # Reconstruct the path
        path = self.reconstruct_path(previous, current_stop_id, current_time)

        execution_time_seconds = (
            datetime.datetime.now() - start_execution_time
        ).total_seconds()
        return path, execution_time_seconds

    def reconstruct_path(self, previous, current_stop_id, current_time):
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

    def get_journey_details(self, path: list, tz: pytz.BaseTzInfo = pytz.UTC):
        """Take a path and return the details of the journey as a list of JourneyStep objects.

        Args:
            path (list): A list of tuples representing the journey path.
            timezone (str): The timezone to localize the dates.

        Returns:
            list[JourneyStep]: A list of JourneyStep objects with localized times.
        """
        if not path or len(path) < 2:
            return []
        journey_steps = []
        db = self.db
        for i in range(len(path) - 1):
            from_stop_id = path[i][0]
            from_arrival_time = tz.fromutc(path[i][1])
            to_stop_id = path[i + 1][0]
            to_arrival_time = tz.fromutc(path[i + 1][1])
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
            from_stop_sequence = None
            to_stop_sequence = None
            trip_headsign = None
            transfer = trip_id is None
            transfer_time = None
            agency_id = None
            agency_name = None

            if trip_id:
                trip = db.get_trip_by_id(trip_id)
                route_id = trip.route_id if trip else None
                route_short_name = trip.route_short_name if trip else None
                route = db.get_route_by_id(route_id) if route_id else None
                route_long_name = route.route_long_name if route else None
                try:
                    from_stop_sequence, to_stop_sequence = db.get_stop_sequences(
                        from_stop_id, to_stop_id, trip_id
                    )
                except ValueError:
                    from_stop_sequence = None
                    to_stop_sequence = None
                trip_headsign = trip.trip_headsign if trip else None
                # Get departure time from the database (since path times are arrivals)
                departure_time = self.get_next_departure(
                    from_stop_id, trip_id, from_arrival_time
                )
                if departure_time is None:
                    departure_time = from_arrival_time.strftime("%H:%M:%S")

                agency_id = route.agency_id if route else None
                agency = db.get_agency_by_id(agency_id) if agency_id else None
                agency_name = agency.agency_name if agency else None
            else:
                # Transfer: compute transfer time if possible
                transfer_time = int(
                    (to_arrival_time - from_arrival_time).total_seconds()
                )
                departure_time = from_arrival_time.strftime("%H:%M:%S")
            journey_steps.append(
                JourneyStep(
                    start_time=from_arrival_time,
                    end_time=to_arrival_time,
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
                    from_stop_sequence=from_stop_sequence,
                    to_stop_sequence=to_stop_sequence,
                    trip_headsign=trip_headsign,
                    transfer=transfer,
                    transfer_time=transfer_time,
                    agency_id=agency_id,
                    agency_name=agency_name,
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
        """Get a summary of the journey steps.

        Returns:
            str: A formatted string summarizing the journey, including start and end stops,
            transfers, and rides on routes, as well as total duration and number of transfers.
        """
        if not journey_steps:
            return "❌ No journey steps available."

        summary = []
        if journey_steps:
            start_step = journey_steps[0]
            end_step = journey_steps[-1]

            start_time = start_step.start_time
            end_time = end_step.end_time

            # Calculate total duration
            total_duration = (end_time - start_time).total_seconds() / 60

            # Format duration in hours and minutes
            if total_duration >= 60:
                hours = int(total_duration // 60)
                minutes = int(total_duration % 60)
                duration_str = f"{hours} hours and {minutes} minutes"
            else:
                duration_str = f"{int(total_duration)} minutes"

            # Calculate number of transfers
            num_transfers = sum(1 for step in journey_steps if not step.transfer) - 1

            summary.append(
                f"🚦 Start at: {start_step.from_stop_name} ({start_step.from_stop_id})\n"
                f"⏰ Departure time: {start_step.departure_time}\n"
            )
            for step in journey_steps:
                if step.transfer:
                    summary.append(
                        f"🔄 Transfer:\n"
                        f"  ➡️ From: {step.from_stop_name} ({step.from_stop_id})\n"
                        f"  ➡️ To: {step.to_stop_name} ({step.to_stop_id})\n"
                        f"  ⏳ Duration: {step.transfer_time} seconds\n"
                    )
                else:
                    route_name = (
                        step.route_short_name or step.route_long_name or "Unknown Route"
                    )
                    summary.append(
                        f"🚅 Ride:\n"
                        f"  🛤️ Route: {route_name} ({step.route_id})\n"
                        f"  ➡️ From: {step.from_stop_name} ({step.from_stop_id})\n"
                        f"  ➡️ To: {step.to_stop_name} ({step.to_stop_id})\n"
                        f"  🪧 Trip: {step.trip_headsign}\n"
                        f"  🏢 Operator: {step.agency_name}\n"
                        f"  ⏰ Departure: {step.departure_time}\n"
                        f"  ⏱️ Arrival: {step.arrival_time}\n"
                    )
            summary.append(
                f"🏁 End at: {end_step.to_stop_name} ({end_step.to_stop_id})\n"
                f"⏱️ Arrival time: {end_step.arrival_time}\n"
            )
            summary.append(
                f"📊 Total duration: {duration_str}\n"
                f"🔢 Number of transfers: {num_transfers}\n"
            )
        return "\n".join(summary) if summary else "❌ No journey steps available."

    def get_journey_summary_fr(self, journey_steps: list[JourneyStep]):
        """Get a summary of the journey steps in French.
        This returns a formatted string summarizing the journey, including start and end stops,
        transfers, and rides on routes, as well as total duration and number of transfers.
        """
        if not journey_steps:
            return "❌ Aucun trajet disponible."

        summary = []
        if journey_steps:
            start_step = journey_steps[0]
            end_step = journey_steps[-1]

            # Calculate total duration
            start_time = start_step.start_time
            end_time = end_step.end_time
            total_duration = (end_time - start_time).total_seconds() / 60

            # Format duration in hours and minutes
            if total_duration >= 60:
                hours = int(total_duration // 60)
                minutes = int(total_duration % 60)
                duration_str = f"{hours} heures et {minutes} minutes"
            else:
                duration_str = f"{int(total_duration)} minutes"

            # Calculate number of transfers
            num_transfers = sum(1 for step in journey_steps if not step.transfer) - 1

            summary.append(
                f"🚦 Départ:\n"
                f"  🛑 De: {start_step.from_stop_name} ({start_step.from_stop_id})\n"
                f"  ⏰ Heure de départ: {start_step.departure_time}\n"
            )
            for step in journey_steps:
                if step.transfer:
                    summary.append(
                        f"🔄 Correspondance:\n"
                        f"  ➡️ De: {step.from_stop_name} ({step.from_stop_id})\n"
                        f"  ➡️ À: {step.to_stop_name} ({step.to_stop_id})\n"
                        f"  ⏳ Durée: {step.transfer_time} secondes\n"
                    )
                else:
                    route_name = (
                        step.route_short_name
                        or step.route_long_name
                        or "Ligne inconnue"
                    )
                    summary.append(
                        f"🚅 Trajet:\n"
                        f"  🛤️ Ligne: {route_name} ({step.route_id})\n"
                        f"  ➡️ De: {step.from_stop_name} ({step.from_stop_id})\n"
                        f"  ➡️ À: {step.to_stop_name} ({step.to_stop_id})\n"
                        f"  🪧 Trajet: {step.trip_headsign}\n"
                        f"  🏢 Opérateur: {step.agency_name}\n"
                        f"  ⏰ Départ: {step.departure_time}\n"
                        f"  ⏱️ Arrivée: {step.arrival_time}\n"
                    )
            summary.append(
                f"🏁 Arrivée:\n"
                f"  🛑 À: {end_step.to_stop_name} ({end_step.to_stop_id})\n"
                f"  ⏱️ Heure d'arrivée: {end_step.arrival_time}\n"
            )
            summary.append(
                f"📊 Durée totale: {duration_str}\n"
                f"🔢 Nombre de correspondances: {num_transfers}\n"
            )
        return "\n".join(summary) if summary else "❌ Aucun trajet disponible."

    def get_journey_step_geometry(
        self,
        step: JourneyStep,
        conn: sqlite3.Connection | None = None,
        cursor: sqlite3.Cursor | None = None,
    ) -> list[tuple[float, float]]:
        """
        Get the geographical coordinates for a single journey step.
        Returns a list of tuples (latitude, longitude).
        """
        if conn is None or cursor is None:
            conn, cursor = self.db.get_connection()
            close_conn = True
        else:
            close_conn = False
        geometry = [(step.from_stop_lat, step.from_stop_lon)]
        if (
            step.trip_id
            and step.from_stop_sequence is not None
            and step.to_stop_sequence is not None
        ):
            sql = """
            SELECT stop_lat, stop_lon
            FROM stop_times
            JOIN stops ON stop_times.stop_id = stops.stop_id
            WHERE trip_id = ? AND stop_sequence > ? AND stop_sequence < ?
            ORDER BY stop_sequence
            """
            cursor.execute(
                sql,
                (
                    step.trip_id,
                    step.from_stop_sequence,
                    step.to_stop_sequence,
                ),
            )
            intermediate_stops = cursor.fetchall()
            for lat, lon in intermediate_stops:
                geometry.append((lat, lon))
        geometry.append((step.to_stop_lat, step.to_stop_lon))
        if close_conn:
            conn.close()
        return geometry

    def get_journey_geometry(
        self, journey_steps: list[JourneyStep]
    ) -> list[tuple[float, float]]:
        """
        Get the geographical coordinates of the journey steps.
        Returns a list of tuples (latitude, longitude).
        """
        geometry = []
        conn, cursor = self.db.get_connection()
        for step in journey_steps:
            step_geometry = self.get_journey_step_geometry(step, conn, cursor)
            if geometry and step_geometry:
                # Avoid duplicate points between steps
                geometry.extend(step_geometry[1:])
            else:
                geometry.extend(step_geometry)
        conn.close()
        return geometry
