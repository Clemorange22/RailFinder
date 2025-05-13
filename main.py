from database import Database
import json, os

ine=2

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
            zip_buffer = db.download_and_extract_gtfs(gtfs_url)
            print(f"Populating database with data from {name}...")
            db.populate_database(zip_buffer)
            print(f"Data from {name} populated successfully.")
        except Exception as e:
            print(f"Error downloading or populating data from {name}: {e}")


# Example usage
if __name__ == "__main__":
    db = Database()
    data_path = "data_sources.json"
    load_data_db(db, data_path)
    conn, cursor = db.get_connection()

    agencies = [
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
