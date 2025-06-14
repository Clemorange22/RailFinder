from database import Database
from journey_planner import JourneyPlanner

import datetime


# Example usage
if __name__ == "__main__":
    db = Database()
    data_path = "data_sources.json"
    db.update_database(data_path, force_update=False)

    jp = JourneyPlanner(db)

    # Tests for the JourneyPlanner class
    SEARCHES = [
        {
            "name": "Amsterdam to Rennes",
            "from": "2992194",
            "to": "StopPoint:OCETGV INOUI-87471003",
        },
        {
            "name": "Paris-Nord to Lyon Part-Dieu",
            "from": "2993634",
            "to": "8772319",
        },
        # Now farther apart, in Europe
        {
            "name": "Berlin to Stockholm",
            "from": "394a5408-d778-4959-a63e-973253443ed2",
            "to": "NSR:Quay:100390",
        },
        {
            "name": "Madrid to Venice",
            "from": "MDS",
            "to": "3012019",
        },
    ]
    print("Starting journey search tests...")
    for search in SEARCHES:
        p, execution_time = jp.journey_search(
            search["from"],
            search["to"],
            datetime.datetime.now() + datetime.timedelta(hours=10),
        )
        if not p:
            print(f"No journey found for {search['name']}")
        else:
            print(f"Journey found for {search['name']} in {execution_time:.2f} seconds")
            details = jp.get_journey_details(p)
            summary = jp.get_journey_summary(details)
            geometry = jp.get_journey_geometry(details)
            print(summary)
            print(geometry)
        input("Press Enter to continue...")
    print("All tests completed successfully.")

    print("placeholder for stopping the debugger")
