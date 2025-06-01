from database import Database
from journey_planner import JourneyPlanner
import json, os


def load_data_db(db: Database, data_path: str):
    """
    Load GTFS data into the database.
    """
    db.reset_database()
    db.create_gtfs_tables()

    with open("data_sources.json", "r") as file:
        # Load the JSON data from the file
        data_sources = json.loads(file.read())

    for name, gtfs_url in data_sources.items():
        print(f"Downloading GTFS data from {name}: {gtfs_url}")
        try:
            # Check if the URL is valid
            db.download_and_populate_gtfs(gtfs_url)
        except Exception as e:
            print(f"Error downloading or populating data from {name}: {e}")
    print("Creating indexes for GTFS tables...")
    db.create_gtfs_indexes()
    print("Indexes created successfully.")
    print("GTFS data loaded successfully.")


# Example usage
if __name__ == "__main__":
    db = Database()
    data_path = "data_sources.json"
    # load_data_db(db, data_path)
    conn, cursor = db.get_connection()

    '''agencies = [
        "SNCF Voyageurs",
        "OCEdefault",
        "CFF",
        "SNCF Voyageurs SA",
        "SNCF Voyageurs EA",
        "SNCF Voyageurs LO",
    ]

    # for each agency, count the number of records in other tables
    for agency in agencies:
        cursor.execute(
            """
            SELECT COUNT(*) FROM routes
            JOIN agency ON routes.agency_id = agency.agency_id
              WHERE agency_name = ? 
            """,
            (agency,),
        )
        count = cursor.fetchone()[0]
        print(f"Number of routes for {agency}: {count}")

    '''
    jp = JourneyPlanner(db)

    print("placeholder line for stopping the debugger")
