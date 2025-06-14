import tkinter as tk
from tkinter import BOTTOM, ttk, messagebox
from tkintermapview import TkinterMapView
from database import Database

from models import StopTime, Stop, Transfer, Trip, JourneyStep
import sqlite3
from journey_planner import JourneyPlanner
import datetime
import os
import pytz
import threading


class RoutePlannerApp:
    def __init__(self, master: tk.Tk, db_path="railfinder.db"):
        self.master = master
        self.db_path = db_path
        self.db = Database(self.db_path)
        # self.db.load_and_prepare_data()
        self.planner = JourneyPlanner(self.db)
        self.journey_geometry = []
        self.active_entry = None
        self.loading_label = ttk.Label(
            master, text="Chargement en cours...", font=("Arial", 14), foreground="blue"
        )
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center")
        self.master.update_idletasks()
        master.title("Rail Finder - Planificateur d'Itinéraires")
        master.geometry("800x600")

        # --- Main Frames ---

        map_canvas_frame = ttk.LabelFrame(master)
        map_canvas_frame.pack(pady=10, padx=10, fill="both", expand=True, side=tk.RIGHT)

        control_frame = ttk.LabelFrame(
            master, text="Définir l'itinéraire", padding="10"
        )
        control_frame.pack(side=tk.TOP, fill=tk.Y, padx=10, pady=10)

        # --- Control Frame Widgets ---

        # Departure City
        ttk.Label(control_frame, text="Ville/Arrêt de départ :").grid(
            row=0, column=0, padx=5, pady=5, sticky="w"
        )
        self.departure_city_entry = ttk.Entry(control_frame, width=30)
        self.departure_city_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.departure_city_entry.bind("<KeyRelease>", self.auto_completion_proposition)
        self.departure_city_entry.bind("<Down>", self.focus_suggestions_listbox)

        # Suggestions Listbox
        self.suggestions_listbox = tk.Listbox(master, width=30, height=5)
        self.suggestions_listbox.bind("<ButtonRelease-1>", self.select_suggestion)
        self.suggestions_listbox.bind("<Return>", self.select_suggestion)
        self.suggestions_listbox.bind("<Double-Button-1>", self.select_suggestion)
        self.suggestions_listbox.bind("<Up>", self.navigate_up)
        self.suggestions_listbox.bind("<Down>", self.navigate_down)

        # Arrival City
        ttk.Label(control_frame, text="Ville/Arrêt d'arrivée :").grid(
            row=1, column=0, padx=5, pady=5, sticky="w"
        )
        self.arrival_city_entry = ttk.Entry(control_frame, width=30)
        self.arrival_city_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.arrival_city_entry.bind("<KeyRelease>", self.auto_completion_proposition)
        self.arrival_city_entry.bind("<Down>", self.focus_suggestions_listbox)

        # Date & Time of Departure entries
        ttk.Label(control_frame, text="Date de départ (JJ/MM/AAAA) :").grid(
            row=2, column=0, padx=5, pady=5, sticky="w"
        )
        self.departure_date_entry = ttk.Entry(control_frame, width=15)
        self.departure_date_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        self.departure_date_entry.insert(0, datetime.date.today().strftime("%d/%m/%Y"))

        ttk.Label(control_frame, text="Heure de départ (HH:MM) :").grid(
            row=3, column=0, padx=5, pady=5, sticky="w"
        )
        self.departure_time_entry = ttk.Entry(control_frame, width=10)
        self.departure_time_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        self.departure_time_entry.insert(0, "08:00")

        # Route Preference
        ttk.Label(control_frame, text="Préférence de trajet:").grid(
            row=4, column=0, columnspan=2, padx=5, pady=10, sticky="w"
        )
        self.route_preference_var = tk.StringVar(value="Le plus rapide")
        ttk.Radiobutton(
            control_frame,
            text="Le plus rapide (durée)",
            variable=self.route_preference_var,
            value="Le plus rapide",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(
            control_frame,
            text="Moins de correspondances",
            variable=self.route_preference_var,
            value="Moins de correspondances",
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=10)

        # Calculate Button
        calculate_button = ttk.Button(
            control_frame, text="Calculer l'itinéraire", command=self.calculate_route
        )
        calculate_button.grid(row=7, column=0, columnspan=2, padx=5, pady=20)

        # Display Frame Widgets

        # Display travel map
        self.map_canvas = TkinterMapView(
            map_canvas_frame, width=400, height=260, corner_radius=0
        )
        # definition of initial zoom scale and map position
        self.map_canvas.set_position(46.7111, 1.7191)
        self.map_canvas.set_zoom(5)
        self.map_canvas.pack(fill="both", expand=True)

        # Display route details frame
        route_details_frame = ttk.LabelFrame(master, text="Détails du trajet")
        route_details_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.route_details_text = tk.Text(
            route_details_frame, height=10, width=50, wrap=tk.WORD
        )
        self.route_details_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.route_details_text.insert(
            tk.END, "Les détails de l'itinéraire s'afficheront ici..."
        )
        self.route_details_text.config(state=tk.DISABLED)
        self.loading_label.destroy()

        # Chargement label + progressbar
        self.loading_frame = ttk.Frame(master, relief="raised", padding=15)
        self.loading_label = ttk.Label(
            self.loading_frame,
            text="🔄 Calcul de l'itinéraire...",
            font=("Arial", 14, "bold"),
        )
        self.loading_bar = ttk.Progressbar(
            self.loading_frame, mode="indeterminate", length=200
        )

        self.loading_label.pack(pady=(0, 10))
        self.loading_bar.pack()

        self.suggestions = []
        self.suggestions_names = []
        self.suggestions_history = set()

    # Methods
    def get_all_stop_names(self):
        """
        Returns a sorted list of all unique stop names from the database.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops")
        stops = [Stop(*row) for row in cursor.fetchall()]
        conn.close()
        return sorted(set(stop.stop_name for stop in stops if stop.stop_name))

    def calculate_route(self):
        """Calculates the route based on the data entered by the user.
        Displays the route details and draws the route on the map.
        """

        def route_calculation():
            """
            Calculates the route in a separate thread to avoid blocking the UI.
            Displays a loading frame with a progress bar during the calculation of the route.
            """
            self.loading_frame.place(relx=0.5, rely=0.85, anchor="center")
            self.loading_bar.start(10)  # Démarrer la barre de chargement
            self.master.update_idletasks()
            self.departure_city_entry.config(state="disabled")
            self.arrival_city_entry.config(state="disabled")

            departure = self.departure_city_entry.get()
            arrival = self.arrival_city_entry.get()

            preference = self.route_preference_var.get()

            # --- Ajout récupération date et heure ---
            date_str = self.departure_date_entry.get()
            time_str = self.departure_time_entry.get()

            result_str = None

            def update_ui_final():
                """
                Final UI update after route calculation.
                Updates the UI with the route details and stops the loading bar.
                """
                self.route_details_text.config(state=tk.NORMAL)
                if result_str:
                    self.route_details_text.insert(tk.END, result_str)
                self.route_details_text.config(state=tk.DISABLED)
                self.map_canvas.delete("all")
                self.tracage_map()
                self.loading_bar.stop()
                self.loading_frame.place_forget()
                self.departure_city_entry.config(state="normal")
                self.arrival_city_entry.config(state="normal")

            try:
                departure_datetime_local = datetime.datetime.strptime(
                    f"{date_str} {time_str}", "%d/%m/%Y %H:%M"
                )
                local_tz = pytz.timezone("Europe/Paris")
                aware_local = local_tz.localize(departure_datetime_local)
                aware_utc = aware_local.astimezone(pytz.utc)
                departure_datetime_utc = aware_utc.replace(tzinfo=None)
            except ValueError:
                self.master.after(
                    0,
                    lambda: messagebox.showerror(
                        "Erreur",
                        "Veuillez entrer une date et une heure de départ valides (JJ/MM/AAAA HH:MM).",
                    ),
                )
                self.master.after(0, update_ui_final)
                return

            if not departure or not arrival:
                self.master.after(
                    0,
                    lambda: messagebox.showerror(
                        "Erreur",
                        "Veuillez entrer une ville de départ et une ville d'arrivée.",
                    ),
                )
                self.master.after(0, update_ui_final)
                return

            # Find stop IDs from self.suggestions
            from_stop_id = None
            for s in list(self.suggestions_history):
                if s[1] == departure:
                    from_stop_id = s[0]
                    break

            to_stop_id = None
            for s in list(self.suggestions_history):
                if s[1] == arrival:
                    to_stop_id = s[0]
                    break

            if not from_stop_id or not to_stop_id:
                self.master.after(
                    0,
                    lambda: messagebox.showerror(
                        "Erreur",
                        "Ville de départ ou d'arrivée non trouvée.",
                    ),
                )
                self.master.after(0, update_ui_final)
                return
            details = f"Calcul de l'itinéraire:\n"
            details += f"Départ: {departure}:{from_stop_id}\n"
            details += f"Arrivée: {arrival}:{to_stop_id}\n"
            details += f"Date et heure de départ (locale): {aware_local}\n"
            details += f"Date et heure de départ (UTC): {departure_datetime_utc}\n"
            details += f"Préférence: {preference}\n\n"
            details += f"Calcul en cours... (Temps de calcul max: 5 minutes)\n"

            def update_ui():
                """Updates the UI with the route details."""
                self.route_details_text.config(state=tk.NORMAL)
                self.route_details_text.delete(1.0, tk.END)
                self.route_details_text.insert(tk.END, details)
                self.route_details_text.config(state=tk.DISABLED)
                self.journey_geometry = []
                self.map_canvas.delete_all_marker()
                self.map_canvas.delete_all_path()
                self.map_canvas.set_position(46.7111, 1.7191)
                self.map_canvas.set_zoom(5)
                self.tracage_map()

            self.master.after(0, update_ui)

            if from_stop_id and to_stop_id:
                p, execution_time = self.planner.journey_search(
                    from_stop_id,
                    to_stop_id,
                    departure_datetime_utc,
                    "fastest" if preference == "Le plus rapide" else "least_transfers",
                    max_execution_time_seconds=300,  # 5 minutes
                    gui=self,
                )
                result_str = ""
                if p is not None:
                    journey_steps = self.planner.get_journey_details(p, tz=local_tz)
                    summary = self.planner.get_journey_summary_fr(journey_steps)
                    result_str += f"Temps d'exécution de la recherche: {execution_time:.2f} secondes\n"
                    result_str += summary
                    self.journey_geometry = []
                    line = self.planner.get_journey_geometry(journey_steps)
                    if line:
                        self.journey_geometry = line
                else:
                    result_str += "Aucun trajet trouvé.\n"

                self.master.after(0, update_ui_final)

        threading.Thread(target=route_calculation).start()

    def auto_completion_proposition(self, event):
        """Displays auto-completion suggestions for the departure, arrival, and intermediate stop entry fields.
        Method called every time a key is released in one of the entry fields.
        """
        widget = event.widget
        self.active_entry = widget
        input_text = widget.get()

        if not input_text:
            self.suggestions_listbox.delete(0, tk.END)
            self.suggestions_listbox.place_forget()
            return

        self.suggestions = self.planner.search_stop_custom(input_text)
        self.suggestions_names = [s[1] for s in self.suggestions]
        self.suggestions_history.update(set(self.suggestions))

        self.suggestions_listbox.delete(0, tk.END)
        for city in self.suggestions_names:
            self.suggestions_listbox.insert(tk.END, city)

        if self.suggestions_names:
            self.suggestions_listbox.selection_set(0)
            self.suggestions_listbox.activate(0)
            # Position dynamique sous le champ actif
            x = widget.winfo_rootx() - self.master.winfo_rootx()
            y = widget.winfo_rooty() - self.master.winfo_rooty() + widget.winfo_height()
            self.suggestions_listbox.place(x=x, y=y)
            self.suggestions_listbox.lift()
        else:
            self.suggestions_listbox.place_forget()

    def select_suggestion(self, event):
        """Selects a suggestion from the list and places it in the active entry field.
        Method called when the user clicks on a suggestion, presses "Enter", or double-clicks a suggestion.
        """
        selected_index = self.suggestions_listbox.curselection()
        if selected_index and self.active_entry:
            selected_city = self.suggestions_listbox.get(selected_index)
            self.active_entry.delete(0, tk.END)
            self.active_entry.insert(0, selected_city)
            self.suggestions_listbox.delete(0, tk.END)
            self.suggestions_listbox.place_forget()
            self.active_entry = None

    def focus_suggestions_listbox(self, event):#Generated AI (Copilot)
        if self.suggestions_listbox.size() > 0:
            self.active_entry = event.widget
            self.suggestions_listbox.focus_set()
            self.suggestions_listbox.selection_clear(0, tk.END)
            self.suggestions_listbox.selection_set(0)
            self.suggestions_listbox.activate(0)

    def navigate_up(self, _=None):#Generated AI (Copilot)
        """Navigates up in the suggestions list.
        Method called when the user presses the up arrow key."""
        cur = self.suggestions_listbox.curselection()
        if cur:
            idx = cur[0]
            if idx > 0:
                self.suggestions_listbox.selection_clear(0, tk.END)
                self.suggestions_listbox.selection_set(idx - 1)
                self.suggestions_listbox.see(idx - 1)
        else:
            if self.suggestions_listbox.size() > 0:
                self.suggestions_listbox.selection_set(0)
                self.suggestions_listbox.see(0)
        self.suggestions_listbox.focus_set()

    def navigate_down(self, _=None):#Generated AI (Copilot)
        """Navigates down in the suggestions list.
        Method called when the user presses the down arrow key."""
        cur = self.suggestions_listbox.curselection()
        size = self.suggestions_listbox.size()
        if cur:
            idx = cur[0]
            if idx < size - 1:
                self.suggestions_listbox.selection_clear(0, tk.END)
                self.suggestions_listbox.selection_set(idx + 1)
                self.suggestions_listbox.see(idx + 1)
        else:
            if size > 0:
                self.suggestions_listbox.selection_set(0)
                self.suggestions_listbox.see(0)
        self.suggestions_listbox.focus_set()

    def get_stop_lat_lon_by_name(self, stop_name):
        """
        Returns (lat, lon), the latitude and longitude coordinates for a given stop_name, or None if not found.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops WHERE stop_name = ? COLLATE NOCASE",
            (stop_name,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            stop = Stop(*row)
            return stop.stop_lat, stop.stop_lon
        else:
            return None

    def tracage_map(self):
        """Displays the route on the map and sets markers for the departure and arrival cities."""
        self.map_canvas.delete_all_marker()

        departure = self.departure_city_entry.get()
        arrival = self.arrival_city_entry.get()
        dep_coords = self.get_stop_lat_lon_by_name(departure)
        arr_coords = self.get_stop_lat_lon_by_name(arrival)

        if dep_coords:
            dep_lat, dep_lon = dep_coords
            icon_path = tk.PhotoImage(
                file=os.path.join(os.path.dirname(__file__), "dep_icon.png")
            )
            self.map_canvas.set_marker(dep_lat, dep_lon, icon=icon_path)
        if arr_coords:
            arr_lat, arr_lon = arr_coords
            icon_path = tk.PhotoImage(
                file=os.path.join(os.path.dirname(__file__), "icon_arrivee.png")
            )
            self.map_canvas.set_marker(arr_lat, arr_lon, icon=icon_path)

        self.map_canvas.delete_all_path()
        if len(self.journey_geometry) > 0:
            path_1 = self.map_canvas.set_path(
                self.journey_geometry, color="blue", width=5
            )

    def get_stop_id_by_name(self, stop_name):
        """
        Returns the stop_id for a given stop_name, or None if not found.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT stop_id FROM stops WHERE stop_name = ? COLLATE NOCASE", (stop_name,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None


if __name__ == "__main__":
    root = tk.Tk()
    app = RoutePlannerApp(root)
    root.mainloop()
