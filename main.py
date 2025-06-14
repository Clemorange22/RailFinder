import os
from database import Database
from interface import RoutePlannerApp
import tkinter as tk

DATA_SOURCES_PATH = "data_sources.json"
DB_PATH = "railfinder.db"
STATIC_DB_PATH = "railfinder_static.db"

# Example usage
if __name__ == "__main__":
    print("Welcome to RailFinder!")
    print("Initializing database...")
    if os.path.exists(STATIC_DB_PATH):
        print(f"Using static database at {STATIC_DB_PATH}")
        db_path = STATIC_DB_PATH
    else:
        db_path = DB_PATH
        db = Database(db_path)
        db.update_database(DATA_SOURCES_PATH, force_update=False)

    root = tk.Tk()
    app = RoutePlannerApp(root, db_path)
    root.mainloop()
