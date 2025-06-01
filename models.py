from dataclasses import dataclass
from typing import Optional


@dataclass
class Agency:
    agency_id: str
    agency_name: str
    agency_url: str
    agency_timezone: str
    agency_lang: Optional[str] = None
    agency_phone: Optional[str] = None
    agency_fare_url: Optional[str] = None
    ticketing_deep_link_id: Optional[str] = None
    agency_email: Optional[str] = None


@dataclass
class Route:
    route_id: str
    route_type: int
    route_short_name: str
    route_long_name: str
    agency_id: Optional[str] = None
    route_desc: Optional[str] = None
    route_url: Optional[str] = None
    route_color: Optional[str] = None
    route_text_color: Optional[str] = None
    route_sort_order: Optional[int] = None
    bikes_allowed: Optional[int] = None


@dataclass
class Shape:
    shape_id: str
    shape_pt_lat: float
    shape_pt_lon: float
    shape_pt_sequence: int
    shape_dist_traveled: Optional[float] = None


@dataclass
class StopTime:
    trip_id: str
    arrival_time: str
    departure_time: str
    stop_id: str
    stop_sequence: int
    stop_headsign: Optional[str] = None
    pickup_type: Optional[int] = None
    drop_off_type: Optional[int] = None
    shape_dist_traveled: Optional[float] = None
    timepoint: Optional[int] = None
    departure_buffer: Optional[int] = None
    route_short_name: Optional[str] = None
    start_pickup_drop_off_window: Optional[str] = None
    end_pickup_drop_off_window: Optional[str] = None
    local_zone_id: Optional[str] = None
    pickup_booking_rule_id: Optional[str] = None
    drop_off_booking_rule_id: Optional[str] = None


@dataclass
class Stop:
    stop_id: str
    stop_name: str
    stop_lat: float
    stop_lon: float
    stop_desc: Optional[str] = None
    stop_code: Optional[str] = None
    zone_id: Optional[str] = None
    stop_url: Optional[str] = None
    location_type: Optional[int] = None
    parent_station: Optional[str] = None
    stop_timezone: Optional[str] = None
    wheelchair_boarding: Optional[int] = None
    platform_code: Optional[str] = None
    level_id: Optional[str] = None


@dataclass
class Transfer:
    from_stop_id: str
    to_stop_id: str
    transfer_type: int
    min_transfer_time: Optional[int] = None
    from_route_id: Optional[str] = None
    from_trip_id: Optional[str] = None
    to_route_id: Optional[str] = None
    to_trip_id: Optional[str] = None


@dataclass
class Trip:
    trip_id: str
    route_id: str
    service_id: str
    trip_headsign: Optional[str] = None
    trip_short_name: Optional[str] = None
    direction_id: Optional[int] = None
    block_id: Optional[str] = None
    shape_id: Optional[str] = None
    wheelchair_accessible: Optional[int] = None
    bikes_allowed: Optional[int] = None
    peak_offpeak: Optional[int] = None
    route_short_name: Optional[str] = None
    trip_bikes_allowed: Optional[int] = None
    ticketing_trip_id: Optional[str] = None
    ticketing_type: Optional[str] = None


@dataclass
class JourneyStep:
    stop_id: str
    stop_name: str
    stop_lat: float
    stop_lon: float
    arrival_time: str
    departure_time: Optional[str] = None
    trip_id: Optional[str] = None
    route_id: Optional[str] = None
    route_short_name: Optional[str] = None
    route_long_name: Optional[str] = None
    transfer: bool = False
    transfer_time: Optional[int] = None  # in seconds or minutes
