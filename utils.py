import math


def geodistance(lat1, lon1, lat2, lon2):
    """
    Calculate the geographical distance between two points on the Earth.

    Args:
        lat1 (float): Latitude of the first point.
        lon1 (float): Longitude of the first point.
        lat2 (float): Latitude of the second point.
        lon2 (float): Longitude of the second point.

    Returns:
        float: Distance between the two points in kilometers.
    """
    R = 6371.0  # km
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def geodistance_meters(lat1, lon1, lat2, lon2):
    """
    Calculate the distance between two geographical points in meters.
    """
    return geodistance(lat1, lon1, lat2, lon2) * 1000  # Convert km to meters
