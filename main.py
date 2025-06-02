from math import e
from database import Database
from journey_planner import JourneyPlanner

import datetime


# Example usage
if __name__ == "__main__":
    db = Database()
    data_path = "data_sources.json"
    # db.load_and_prepare_data(data_path)

    jp = JourneyPlanner(db)

    """print("Rennes to Louvres Rivoli journey search")
    p = jp.journey_search(
        "StopPoint:OCETGV INOUI-87471003",
        "IDFM:37354",
        datetime.datetime.now() + datetime.timedelta(hours=10),
        datetime.timedelta(hours=2),
    )
    if not p:
        print("No journey found")
        exit(1)
    details = jp.get_journey_details(p)
    summary = jp.get_journey_summary(details)
    print(summary)
    print("Montparnasse Bienvenue to Louvre Rivoli journey search")
    p = jp.journey_search(
        "IDFM:462996",
        "IDFM:22092",
        datetime.datetime.now() + datetime.timedelta(hours=10),
        datetime.timedelta(hours=2),
    )
    if not p:
        print("No journey found")
        exit(1)
    details = jp.get_journey_details(p)
    summary = jp.get_journey_summary(details)
    print(summary)"""
    print("Brest to Bruxelles journey search")


print("placeholder line for stopping the debugger")
