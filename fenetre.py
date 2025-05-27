import tkinter as tk
from tkinter import ttk, messagebox

liste_ville = ["Paris", "Lyon", "Limo"]


class RoutePlannerApp:
    def __init__(self, master, liste_ville):
        self.master = master
        self.liste_ville = liste_ville
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
        ttk.Label(control_frame, text="Ville de départ:").grid(
            row=0, column=0, padx=5, pady=5, sticky="w"
        )
        self.departure_city_entry = ttk.Entry(control_frame, width=30)
        self.departure_city_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.departure_city_entry.bind("<KeyRelease>", self.auto_completion_proposition)
        self.departure_city_entry.bind("<Down>", self.focus_suggestions_listbox)

        # Liste des suggestions affichée sous l'entrée
        self.suggestions_listbox = tk.Listbox(control_frame, width=30, height=5)
        self.suggestions_listbox.bind("<ButtonRelease-1>", self.select_suggestion)
        self.suggestions_listbox.bind("<Return>", self.select_suggestion)
        self.suggestions_listbox.bind("<Double-Button-1>", self.select_suggestion)
        self.suggestions_listbox.bind("<Up>", self.navigate_up)
        self.suggestions_listbox.bind("<Down>", self.navigate_down)

        # Arrival City
        ttk.Label(control_frame, text="Ville d'arrivée:").grid(
            row=1, column=0, padx=5, pady=5, sticky="w"
        )
        self.arrival_city_entry = ttk.Entry(control_frame, width=30)
        self.arrival_city_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        self.arrival_city_entry.bind("<KeyRelease>", self.auto_completion_proposition)
        self.arrival_city_entry.bind("<Down>", self.focus_suggestions_listbox)
        # Intermediate Stops
        ttk.Label(control_frame, text="Étapes intermédiaires:").grid(
            row=2, column=0, columnspan=2, padx=5, pady=5, sticky="w"
        )
        self.stops_frame = ttk.Frame(control_frame)
        self.stops_frame.grid(
            row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew"
        )
        self.intermediate_stops_entries = []
        self.add_stop_button = ttk.Button(
            control_frame, text="Ajouter une étape", command=self.add_stop
        )  # [cite: 6]
        self.add_stop_button.grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.remove_stop_button = ttk.Button(
            control_frame, text="Supprimer la dernière étape", command=self.remove_stop
        )  # [cite: 6]
        self.remove_stop_button.grid(row=4, column=1, padx=5, pady=5, sticky="e")

        # Train Type [cite: 7]
        ttk.Label(control_frame, text="Type de trains:").grid(
            row=5, column=0, columnspan=2, padx=5, pady=10, sticky="w"
        )
        self.train_type_var = tk.StringVar(value="TGV + TER")
        ttk.Radiobutton(
            control_frame,
            text="TGV uniquement",
            variable=self.train_type_var,
            value="TGV",
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(
            control_frame,
            text="TER uniquement",
            variable=self.train_type_var,
            value="TER",
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(
            control_frame,
            text="TGV + TER",
            variable=self.train_type_var,
            value="TGV + TER",
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=10)

        # Route Preference [cite: 7]
        ttk.Label(control_frame, text="Préférence de trajet:").grid(
            row=9, column=0, columnspan=2, padx=5, pady=10, sticky="w"
        )
        self.route_preference_var = tk.StringVar(value="Le plus rapide")
        ttk.Radiobutton(
            control_frame,
            text="Le plus rapide (durée)",
            variable=self.route_preference_var,
            value="Le plus rapide",
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(
            control_frame,
            text="Moins de correspondances",
            variable=self.route_preference_var,
            value="Moins de correspondances",
        ).grid(row=11, column=0, columnspan=2, sticky="w", padx=10)

        # Calculate Button
        calculate_button = ttk.Button(
            control_frame, text="Calculer l'itinéraire", command=self.calculate_route
        )
        calculate_button.grid(row=12, column=0, columnspan=2, padx=5, pady=20)

        # --- Display Frame Widgets ---

        # Map Area (Placeholder) [cite: 9]
        map_canvas_frame = ttk.LabelFrame(
            display_frame, text="Carte de l'itinéraire", width=400, height=250
        )
        map_canvas_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.map_canvas = tk.Canvas(map_canvas_frame, bg="lightgrey")
        self.map_canvas.pack(fill="both", expand=True)
        self.map_canvas.create_text(
            10,
            10,
            anchor="nw",
            text="Espace réservé pour la carte (matplotlib/tkinter)",
        )

        # Route Details Area (Placeholder) [cite: 11]
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

    def add_stop(self):  # [cite: 6]
        if (
            len(self.intermediate_stops_entries) < 5
        ):  # Limiting to 5 stops for simplicity
            row_num = len(self.intermediate_stops_entries)
            stop_label = ttk.Label(self.stops_frame, text=f"Étape {row_num + 1}:")
            stop_label.grid(row=row_num, column=0, padx=5, pady=2, sticky="w")
            stop_entry = ttk.Entry(self.stops_frame, width=28)
            stop_entry.grid(row=row_num, column=1, padx=5, pady=2, sticky="ew")
            self.intermediate_stops_entries.append((stop_label, stop_entry))
            # TODO: Implement autocompletion [cite: 5]
        else:
            messagebox.showinfo(
                "Limite atteinte", "Vous ne pouvez pas ajouter plus d'étapes."
            )

    def remove_stop(self):  # [cite: 6]
        if self.intermediate_stops_entries:
            label, entry = self.intermediate_stops_entries.pop()
            label.destroy()
            entry.destroy()
        else:
            messagebox.showinfo(
                "Aucune étape", "Il n'y a pas d'étape intermédiaire à supprimer."
            )

    def calculate_route(self):
        departure = self.departure_city_entry.get()
        arrival = self.arrival_city_entry.get()
        stops = [
            entry.get() for _, entry in self.intermediate_stops_entries if entry.get()
        ]
        train_type = self.train_type_var.get()
        preference = self.route_preference_var.get()

        if not departure or not arrival:
            messagebox.showerror(
                "Erreur", "Veuillez entrer une ville de départ et une ville d'arrivée."
            )
            return

        # Placeholder for route calculation logic [cite: 2, 8]
        # This is where you would integrate with SNCF data and algorithms like Dijkstra [cite: 12]

        # Displaying selected options (example)
        self.route_details_text.config(state=tk.NORMAL)
        self.route_details_text.delete(1.0, tk.END)
        details = f"Calcul de l'itinéraire:\n"
        details += f"Départ: {departure}\n"
        details += f"Arrivée: {arrival}\n"
        if stops:
            details += f"Étapes: {', '.join(stops)}\n"
        details += f"Type de trains: {train_type}\n"
        details += f"Préférence: {preference}\n\n"
        details += "--- (Logique de calcul et résultats réels à implémenter) ---"  # [cite: 2, 8, 11, 12]
        self.route_details_text.insert(tk.END, details)
        self.route_details_text.config(state=tk.DISABLED)

        # Placeholder for map update [cite: 9]
        self.map_canvas.delete("all")
        self.map_canvas.create_text(
            10,
            10,
            anchor="nw",
            text=f"Carte: {departure} -> {' -> '.join(stops) + ' -> ' if stops else ''}{arrival}",
        )

        print(
            f"Départ: {departure}, Arrivée: {arrival}, Étapes: {stops}, Type: {train_type}, Préférence: {preference}"
        )
        # Here, you'd call your backend logic to calculate the route and update the display

    def auto_completion_proposition(self, event):
        """Affiche les suggestions basées sur l'entrée utilisateur"""
        input_text = self.departure_city_entry.get()
        input_text2 = self.arrival_city_entry.get()
        if not input_text or input_text2:
            self.suggestions_listbox.delete(0, tk.END)
            self.suggestions_listbox.grid_remove()
            return
        if input_text:
            self.suggestions_listbox.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
            filtered_suggestions = [
                city
                for city in self.liste_ville
                if city.lower().startswith(input_text.lower())
            ]
        if input_text2:
            self.suggestions_listbox.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
            filtered_suggestions = [
                city
                for city in self.liste_ville
                if city.lower().startswith(input_text2.lower())
            ]
        self.suggestions_listbox.delete(0, tk.END)

        for city in filtered_suggestions:
            self.suggestions_listbox.insert(tk.END, city)

    def select_suggestion(self, event):
        """Remplace le texte de l'entrée par la suggestion choisie"""
        selected_index = self.suggestions_listbox.curselection()
        if selected_index:
            selected_city = self.suggestions_listbox.get(selected_index)
            self.departure_city_entry.delete(0, tk.END)
            self.departure_city_entry.insert(0, selected_city)
            self.arrival_city_entry.delete(0, tk.END)
            self.arrival_city_entry.insert(0, selected_city)
            self.suggestions_listbox.delete(0, tk.END)
            self.suggestions_listbox.grid_remove()

    def focus_suggestions_listbox(self, event):
        """Donne le focus à la listbox et sélectionne la première suggestion"""
        if self.suggestions_listbox.size() > 0:
            self.suggestions_listbox.focus_set()
            self.suggestions_listbox.selection_clear(0, tk.END)
            self.suggestions_listbox.selection_set(0)
            self.suggestions_listbox.activate(0)

    def navigate_up(self, event):
        """Navigue vers le haut dans la listbox"""
        cur = self.suggestions_listbox.curselection()
        if cur:
            idx = cur[0]
            if idx > 0:
                self.suggestions_listbox.selection_clear(0, tk.END)
                self.suggestions_listbox.selection_set(idx - 1)
                self.suggestions_listbox.activate(idx - 1)

    def navigate_down(self, event):
        """Navigue vers le bas dans la listbox"""
        cur = self.suggestions_listbox.curselection()
        size = self.suggestions_listbox.size()
        if cur:
            idx = cur[0]
            if idx < size - 1:
                self.suggestions_listbox.selection_clear(0, tk.END)
                self.suggestions_listbox.selection_set(idx + 1)
                self.suggestions_listbox.activate(idx + 1)


if __name__ == "__main__":
    root = tk.Tk()
    app = RoutePlannerApp(root, liste_ville)
    root.mainloop()
