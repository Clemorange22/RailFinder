import datetime
from database import Database
from models import StopTime, Stop, Transfer, Trip


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
        cursor.execute(
            f"""
            SELECT DISTINCT stop_times.trip_id, min(stop_times.arrival_time), max(stop_times.departure_time), routes.route_short_name, routes.route_long_name, trips.trip_headsign
            FROM stop_times
            JOIN trips ON stop_times.trip_id = trips.trip_id
            JOIN routes ON trips.route_id = routes.route_id
            WHERE stop_times.stop_id = ? AND stop_times.arrival_time BETWEEN ? AND ?
			AND (trips.service_id IN (SELECT calendar.service_id FROM calendar WHERE ? BETWEEN calendar.start_date AND calendar.end_date AND ?=1 )
			OR trips.service_id IN (SELECT calendar_dates.service_id FROM calendar_dates WHERE calendar_dates.date = ?))
            GROUP BY trips.trip_headsign
			ORDER BY stop_times.arrival_time
            LIMIT ?
            """,  # TODO: Retrieve the departures and add its own data class in models.py
            (
                stop_id,
                start_time.strftime("%H:%M:%S"),
                end_time.strftime("%H:%M:%S"),
                start_time.strftime("%Y%m%d"),
                start_time.strftime("%A").lower(),
                start_time.strftime("%Y%m%d"),
                limit,
            ),
        )
        departures = cursor.fetchall()
        conn.close()
        return departures
