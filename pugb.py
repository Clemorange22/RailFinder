
from database import Database

if __name__== "__main__":
    db = Database("gtfs.db")
    db.load_and_prepare_data("data_sources.json")