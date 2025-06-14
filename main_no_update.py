from database import Database
from interface import RoutePlannerApp
import tkinter as tk


# Example usage
if __name__ == "__main__":
    db = Database()

    root = tk.Tk()
    app = RoutePlannerApp(root)
    root.mainloop()
