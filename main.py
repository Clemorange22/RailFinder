from database import Database
from journey_planner import JourneyPlanner

import datetime


# Example usage
if __name__ == "__main__":
    db = Database()
    data_path = "data_sources.json"
    # db.load_and_prepare_data(data_path)

    jp = JourneyPlanner(db)

    """p = jp.journey_search(
        "StopPoint:OCETGV INOUI-87471003",
        "StopPoint:OCETGV INOUI-87773002",
        datetime.datetime.now() + datetime.timedelta(hours=10),
        datetime.timedelta(hours=2),
    )"""  # Rennes to Montpellier Saint-Roch
    """p = jp.journey_search(
        "StopPoint:OCETGV INOUI-87471003",
        "StopPoint:OCETrain TER-87478164",
        datetime.datetime.now(),
        datetime.timedelta(hours=2),
    )"""  # Rennes to Dinan
    p = jp.journey_search(
        "StopPoint:OCETGV INOUI-87471003",
        "IDFM:37354",
        datetime.datetime.now() + datetime.timedelta(hours=10),
        datetime.timedelta(hours=2),
    )  # Rennes to Louvres Rivoli

    if not p:
        print("No journey found")
        exit(1)
    details = jp.get_journey_details(p)
    summary = jp.get_journey_summary(details)
    print(summary)

    print("placeholder line for stopping the debugger")
