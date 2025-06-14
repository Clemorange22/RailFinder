from database import Database
from interface import RoutePlannerApp
import tkinter as tk


# Example usage
if __name__ == "__main__":
    db = Database()
    data_path = "data_sources.json"
    db.update_database(data_path, force_update=False)

    root = tk.Tk()
    app = RoutePlannerApp(root)
    root.mainloop()
