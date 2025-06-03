import tkinter as tk
from tkinter import ttk, messagebox
from tkintermapview import TkinterMapView
import database
import journey_planner
from models import StopTime, Stop, Transfer, Trip, JourneyStep
import sqlite3
from journey_planner import JourneyPlanner
import datetime
import pytz  # Ajoute cette importation en haut du fichier


class RoutePlannerApp:
    def __init__(self, master, db_path="gtfs.db"):
        self.master = master
        self.db_path = db_path
        self.liste_ville = self.get_all_stop_names()
        self.planner = JourneyPlanner(self.db_path)
        print("Exemple de villes chargées :", self.liste_ville[:10])
        self.active_entry = None
        self.loading_label = ttk.Label(master, text="Chargement en cours...", font=("Arial", 14), foreground="blue")
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center")
        self.master.update_idletasks()
        master.title("Rail Finder - Planificateur d'Itinéraires")
        master.geometry("800x600")

        # --- Main Frames ---
        control_frame = ttk.LabelFrame(
            master, text="Définir l'itinéraire", padding="10"
        )
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        display_frame = ttk.LabelFrame(
            master, text="Informations de l'itinéraire", padding="10"
        )
        display_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Control Frame Widgets ---

        # Departure City
        ttk.Label(control_frame, text="Ville de départ :").grid(
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
        ttk.Label(control_frame, text="Ville d'arrivée :").grid(
            row=1, column=0, padx=5, pady=5, sticky="w"
        )
        self.arrival_city_entry = ttk.Entry(control_frame, width=30)
        self.arrival_city_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.arrival_city_entry.bind("<KeyRelease>", self.auto_completion_proposition)
        self.arrival_city_entry.bind("<Down>", self.focus_suggestions_listbox)

        # Date & Time of Departure
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

        # Intermediate Stops
        ttk.Label(control_frame, text="Étapes :").grid(
            row=4, column=0, columnspan=2, padx=5, pady=5, sticky="w"
        )
        self.stops_frame = ttk.Frame(control_frame)
        self.stops_frame.grid(
            row=5, column=0, columnspan=2, padx=5, pady=5, sticky="ew"
        )
        self.intermediate_stops_entries = []
        self.add_stop_button = ttk.Button(
            control_frame, text="Ajouter une étape", command=self.add_stop
        )
        self.add_stop_button.grid(row=6, column=0, padx=5, pady=5, sticky="w")
        self.add_stop_button = ttk.Entry(control_frame, width=30)
        self.remove_stop_button = ttk.Button(
            control_frame, text="Supprimer la dernière étape", command=self.remove_stop
        )
        self.remove_stop_button.grid(row=6, column=1, padx=5, pady=5, sticky="e")

        # Train Type
        ttk.Label(control_frame, text="Type de trains:").grid(
            row=7, column=0, columnspan=2, padx=5, pady=10, sticky="w"
        )
        self.train_type_var = tk.StringVar(value="TGV + TER")
        ttk.Radiobutton(
            control_frame,
            text="TGV uniquement",
            variable=self.train_type_var,
            value="TGV",
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(
            control_frame,
            text="TER uniquement",
            variable=self.train_type_var,
            value="TER",
        ).grid(row=9, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(
            control_frame,
            text="TGV + TER",
            variable=self.train_type_var,
            value="TGV + TER",
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=10)

        # Route Preference
        ttk.Label(control_frame, text="Préférence de trajet:").grid(
            row=11, column=0, columnspan=2, padx=5, pady=10, sticky="w"
        )
        self.route_preference_var = tk.StringVar(value="Le plus rapide")
        ttk.Radiobutton(
            control_frame,
            text="Le plus rapide (durée)",
            variable=self.route_preference_var,
            value="Le plus rapide",
        ).grid(row=12, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(
            control_frame,
            text="Moins de correspondances",
            variable=self.route_preference_var,
            value="Moins de correspondances",
        ).grid(row=13, column=0, columnspan=2, sticky="w", padx=10)

        # Calculate Button
        calculate_button = ttk.Button(
            control_frame, text="Calculer l'itinéraire", command=self.calculate_route
        )
        calculate_button.grid(row=14, column=0, columnspan=2, padx=5, pady=20)

        # Display Frame Widgets
        
        #Display travel map
        map_canvas_frame = ttk.LabelFrame(display_frame)
        map_canvas_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.map_canvas = TkinterMapView(map_canvas_frame, width=400, height=260, corner_radius=0)
        #definition of zoom scale and map position
        self.map_canvas.set_position(46.7111, 1.7191)
        self.map_canvas.set_zoom(5)
        self.map_canvas.pack(fill="both", expand=True)
        

        route_details_frame = ttk.LabelFrame(display_frame, text="Détails du trajet")
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
        self.loading_label = ttk.Label(self.loading_frame, text="🔄 Calcul de l'itinéraire...", font=("Arial", 14, "bold"))
        self.loading_bar = ttk.Progressbar(self.loading_frame, mode="indeterminate", length=200)

        self.loading_label.pack(pady=(0, 10))
        self.loading_bar.pack()


    def get_all_stop_names(self):
        """
        Retourne la liste de tous les noms de stops présents dans la base de données.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops")
        stops = [Stop(*row) for row in cursor.fetchall()]
        conn.close()
        return sorted(set(stop.stop_name for stop in stops if stop.stop_name))

    def add_stop(self):
        if len(self.intermediate_stops_entries) < 5:
            row_num = len(self.intermediate_stops_entries)
            stop_label = ttk.Label(self.stops_frame, text=f"Étape {row_num + 1}:")
            stop_label.grid(row=row_num, column=0, padx=5, pady=2, sticky="w")
            stop_entry = ttk.Entry(self.stops_frame, width=28)
            stop_entry.grid(row=row_num, column=1, padx=5, pady=2, sticky="ew")
            stop_entry.bind("<KeyRelease>", self.auto_completion_proposition)
            stop_entry.bind("<Down>", self.focus_suggestions_listbox)
            self.intermediate_stops_entries.append((stop_label, stop_entry))
        else:
            messagebox.showinfo(
                "Limite atteinte", "Vous ne pouvez pas ajouter plus d'étapes."
            )

    def remove_stop(self):
        if self.intermediate_stops_entries:
            label, entry = self.intermediate_stops_entries.pop()
            label.destroy()
            entry.destroy()
        else:
            messagebox.showinfo(
                "Aucune étape", "Il n'y a pas d'étape intermédiaire à supprimer."
            )

    def calculate_route(self):
        self.loading_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.loading_bar.start(10)  # Démarrer la barre de chargement
        self.master.update_idletasks()
        self.departure_city_entry.config(state="disabled")
        self.arrival_city_entry.config(state="disabled")

        departure = self.departure_city_entry.get()
        arrival = self.arrival_city_entry.get()
        stops = [
            entry.get() for _, entry in self.intermediate_stops_entries if entry.get()
        ]
        train_type = self.train_type_var.get()
        preference = self.route_preference_var.get()

        # --- Ajout récupération date et heure ---
        date_str = self.departure_date_entry.get()
        time_str = self.departure_time_entry.get()
        try:
            departure_datetime = datetime.datetime.strptime(
                f"{date_str} {time_str}", "%d/%m/%Y %H:%M"
            )
            # Conversion en UTC (en supposant que l'entrée est en heure locale France)
            local_tz = pytz.timezone("Europe/Paris")
            departure_datetime = local_tz.localize(departure_datetime)
            departure_datetime_utc = departure_datetime.astimezone(pytz.utc)
        except ValueError:
            messagebox.showerror(
                "Erreur", "Veuillez entrer une date et une heure de départ valides (JJ/MM/AAAA HH:MM)."
            )
            return
        # ----------------------------------------

        if not departure or not arrival:
            messagebox.showerror(
                "Erreur", "Veuillez entrer une ville de départ et une ville d'arrivée."
            )
            return

        self.route_details_text.config(state=tk.NORMAL)
        self.route_details_text.delete(1.0, tk.END)
        from_stop_id = self.get_stop_id_by_name(departure)
        to_stop_id = self.get_stop_id_by_name(arrival)
        details = f"Calcul de l'itinéraire:\n"
        details += f"Départ: {departure}:{from_stop_id}\n"
        details += f"Arrivée: {arrival}:{to_stop_id}\n"
        details += f"Date et heure de départ (locale): {departure_datetime}\n"
        details += f"Date et heure de départ (UTC): {departure_datetime_utc}\n"
        if stops:
            details += f"Étapes: {', '.join(stops)}\n"
        details += f"Type de trains: {train_type}\n"
        details += f"Préférence: {preference}\n\n"
        details += "--- (Logique de calcul et résultats réels à implémenter) ---"
        details+= self.planner.journey_search(from_stop_id,to_stop_id,departure_datetime_utc,datetime.timedelta(1))
        self.route_details_text.insert(tk.END, details)
        self.route_details_text.config(state=tk.DISABLED)

        self.map_canvas.delete("all")
        self.tracage_map()
        # Simuler le calcul de l'itinéraire
        self.loading_bar.stop()
        self.loading_frame.place_forget()

        # Réactiver les champs de saisie
        self.departure_city_entry.config(state="normal")
        self.arrival_city_entry.config(state="normal")

        

    def auto_completion_proposition(self, event):
        widget = event.widget
        self.active_entry = widget
        input_text = widget.get()

        if not input_text:
            self.suggestions_listbox.delete(0, tk.END)
            self.suggestions_listbox.place_forget()
            return

        filtered_suggestions = [
            city
            for city in self.liste_ville
            if city.lower().startswith(input_text.lower())
        ]
        self.suggestions_listbox.delete(0, tk.END)
        for city in filtered_suggestions:
            self.suggestions_listbox.insert(tk.END, city)

        if filtered_suggestions:
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
        selected_index = self.suggestions_listbox.curselection()
        if selected_index and self.active_entry:
            selected_city = self.suggestions_listbox.get(selected_index)
            self.active_entry.delete(0, tk.END)
            self.active_entry.insert(0, selected_city)
            self.suggestions_listbox.delete(0, tk.END)
            self.suggestions_listbox.place_forget()
            self.active_entry = None

    def focus_suggestions_listbox(self, event):
        if self.suggestions_listbox.size() > 0:
            self.active_entry = event.widget
            self.suggestions_listbox.focus_set()
            self.suggestions_listbox.selection_clear(0, tk.END)
            self.suggestions_listbox.selection_set(0)
            self.suggestions_listbox.activate(0)

    def navigate_up(self, event):
        cur = self.suggestions_listbox.curselection()
        if cur:
            idx = cur[0]
            if idx > 0:
                self.suggestions_listbox.selection_clear(0, tk.END)
                self.suggestions_listbox.selection_set(idx - 1)
                self.suggestions_listbox.activate(idx - 1)

    def navigate_down(self, event):
        cur = self.suggestions_listbox.curselection()
        size = self.suggestions_listbox.size()
        if cur:
            idx = cur[0]
            if idx < size - 1:
                self.suggestions_listbox.selection_clear(0, tk.END)
                self.suggestions_listbox.selection_set(idx + 1)
                self.suggestions_listbox.activate(idx + 1)
    
    # Function to get latitude and longitude by stop name
    def get_stop_lat_lon_by_name(self, stop_name):
        """
        Retourne (lat, lon) pour un stop_name donné, ou None si non trouvé.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops WHERE stop_name = ? COLLATE NOCASE",
            (stop_name,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            stop = Stop(*row)
            return stop.stop_lat, stop.stop_lon
        else:
            return None
        

    def tracage_map(self):
        self.departure = self.departure_city_entry.get()
        self.arrival = self.arrival_city_entry.get()
        self.dep_lat, self.dep_lon = self.get_stop_lat_lon_by_name(self.departure)
        self.dep_marker = self.map_canvas.set_marker(self.dep_lat, self.dep_lon)
        self.arr_lat, self.arr_lon = self.get_stop_lat_lon_by_name(self.arrival)
        #self.arrival_icon = tk.PhotoImage(file=r"C:\Users\nbaur\Documents\Travail Noelie\INSA\FIMI 2A\ISN\RailFinder\icon_arrivee.png")
        self.arr_marker = self.map_canvas.set_marker(self.arr_lat, self.arr_lon, icon=self.arrival_icon)
        
        
        
    # Ajoute cette méthode dans ta classe RoutePlannerApp
    def get_stop_id_by_name(self, stop_name):
        """
        Retourne le stop_id pour un stop_name donné, ou None si non trouvé.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT stop_id FROM stops WHERE stop_name = ? COLLATE NOCASE",
            (stop_name,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

"""db = database.Database()

planner = journey_planner.JourneyPlanner(db)  # Création de l'instance
details = planner.get_journey_details(["Paris", "Lyon"])"""

if __name__ == "__main__":
    root = tk.Tk()
    app = RoutePlannerApp(root)
    root.mainloop()
