import tkinter as tk
from tkinter import ttk, messagebox
from tkintermapview import TkinterMapView
from database import Database
from models import StopTime, Stop, Transfer, Trip, JourneyStep
import sqlite3
from journey_planner import JourneyPlanner
import datetime
import customtkinter as ctk
import pytz


class RoutePlannerApp:
    def __init__(self, master, db_path="gtfs.db"):
        self.master = master
        self.db_path = db_path
        self.planner = JourneyPlanner(Database(db_path))
        self.liste_ville = []  # Initialisé vide, sera rempli au démarrage de l'UI
        self.active_entry = None

        master.title("Rail Finder - Planificateur d'Itinéraires")
        master.geometry("800x600")

        # --- Chargement des données initiales en arrière-plan sans bloquer l'UI ---
        # On va charger la liste des villes *avant* de construire les widgets qui en dépendent.
        # Mais sans afficher de splash screen explicite.
        # On peut bloquer un instant si la liste des villes n'est pas énorme,
        # sinon on peut la charger dans un thread APRES la construction de l'UI si nécessaire
        # pour la rendre immédiatement visible (mais avec auto-complétion inactive au début).
        # Pour cet exemple, on suppose que get_all_stop_names() est assez rapide
        # ou qu'un léger délai au démarrage est acceptable.
        self.liste_ville = self.get_all_stop_names()
        print("Exemple de villes chargées :", self.liste_ville[:10])

        # --- Construction directe de l'interface utilisateur principale ---
        self._build_main_ui()

        # Le cadre de chargement pour le calcul d'itinéraire est initialisé ici, mais caché
        self.loading_frame = ctk.CTkFrame(
            self.master, corner_radius=10, fg_color=("gray85", "gray15")
        )  # A slightly different color for prominence
        self.loading_label = ctk.CTkLabel(
            self.loading_frame,
            text="🔄 Calcul de l'itinéraire...",
            font=("Arial", 16, "bold"),
        )
        self.loading_bar = ctk.CTkProgressBar(
            self.loading_frame, mode="indeterminate", width=200
        )

        self.loading_label.pack(pady=(0, 10))
        self.loading_bar.pack()
        self.loading_frame.place_forget()  # Cache-le initialement

    def _build_main_ui(self):
        """Construit et affiche l'interface utilisateur principale de l'application."""
        # --- Main Frames (using CTkFrame) ---
        # 1. Create and pack the main frames first, dividing the master window
        # Control Frame (left half)
        self.control_frame = ctk.CTkFrame(
            self.master, corner_radius=0, fg_color="transparent", border_width=0
        )
        self.control_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=0, pady=0)

        # Display Frame (right half)
        self.display_frame = ctk.CTkFrame(
            self.master, corner_radius=0, fg_color="transparent", border_width=0
        )
        self.display_frame.pack(
            side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=0, pady=0
        )

        # 2. Now, pack the titles *inside* their respective frames.
        # Control Frame Title (inside control_frame)
        control_frame_title = ctk.CTkLabel(
            self.control_frame,
            text="Définir l'itinéraire",
            font=("Arial", 16, "bold"),
            fg_color="transparent",
        )
        control_frame_title.pack(side=tk.TOP, anchor="n", padx=10, pady=(10, 0))

        # Nested frame for control widgets to better manage padding within the main control_frame
        # This frame will now be packed *below* the title within control_frame.
        self.control_widgets_frame = ctk.CTkFrame(self.control_frame, corner_radius=10)
        self.control_widgets_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Display Frame Title (inside display_frame)
        display_frame_title = ctk.CTkLabel(
            self.display_frame,
            text="Informations de l'itinéraire",
            font=("Arial", 16, "bold"),
            fg_color="transparent",
        )
        display_frame_title.pack(side=tk.TOP, anchor="n", padx=10, pady=(10, 0))

        # --- Rest of your widgets follow, packed into control_widgets_frame or display_frame directly ---

        # --- Control Frame Widgets ---

        # Departure City
        ctk.CTkLabel(self.control_widgets_frame, text="Ville de départ :").grid(
            row=0, column=0, padx=5, pady=5, sticky="w"
        )
        self.departure_city_entry = ctk.CTkEntry(self.control_widgets_frame, width=220)
        self.departure_city_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.departure_city_entry.bind("<KeyRelease>", self.auto_completion_proposition)
        self.departure_city_entry.bind("<Down>", self.focus_suggestions_listbox)

        # Suggestions Listbox (Parent is master, not control_widgets_frame)
        self.suggestions_listbox = tk.Listbox(
            self.master,
            width=25,
            height=5,
            relief="flat",
            highlightthickness=0,
            bd=1,
            font=("Arial", 18),
        )
        self.suggestions_listbox.bind("<ButtonRelease-1>", self.select_suggestion)
        self.suggestions_listbox.bind("<Return>", self.select_suggestion)
        self.suggestions_listbox.bind("<Double-Button-1>", self.select_suggestion)
        self.suggestions_listbox.bind("<Up>", self.navigate_up)
        self.suggestions_listbox.bind("<Down>", self.navigate_down)
        self.suggestions_listbox.configure(
            bg=self.get_ctk_color("CTkFrame"),
            fg=self.get_ctk_color("text"),
            selectbackground=self.get_ctk_color("selection_color"),
            selectforeground=self.get_ctk_color("text"),
        )

        # Arrival City
        ctk.CTkLabel(self.control_widgets_frame, text="Ville d'arrivée :").grid(
            row=1, column=0, padx=5, pady=5, sticky="w"
        )
        self.arrival_city_entry = ctk.CTkEntry(self.control_widgets_frame, width=220)
        self.arrival_city_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.arrival_city_entry.bind("<KeyRelease>", self.auto_completion_proposition)
        self.arrival_city_entry.bind("<Down>", self.focus_suggestions_listbox)

        # Date & Time of Departure
        ctk.CTkLabel(
            self.control_widgets_frame, text="Date de départ (JJ/MM/AAAA) :"
        ).grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.departure_date_entry = ctk.CTkEntry(self.control_widgets_frame, width=120)
        self.departure_date_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        self.departure_date_entry.insert(0, datetime.date.today().strftime("%d/%m/%Y"))

        ctk.CTkLabel(self.control_widgets_frame, text="Heure de départ (HH:MM) :").grid(
            row=3, column=0, padx=5, pady=5, sticky="w"
        )
        self.departure_time_entry = ctk.CTkEntry(self.control_widgets_frame, width=80)
        self.departure_time_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        self.departure_time_entry.insert(0, "08:00")

        # Intermediate Stops
        ctk.CTkLabel(self.control_widgets_frame, text="Étapes :").grid(
            row=4, column=0, columnspan=2, padx=5, pady=5, sticky="w"
        )
        self.stops_frame = ctk.CTkFrame(
            self.control_widgets_frame, fg_color="transparent"
        )
        self.stops_frame.grid(
            row=5, column=0, columnspan=2, padx=5, pady=5, sticky="ew"
        )
        self.intermediate_stops_entries = []

        # Buttons for adding/removing stops
        self.add_stop_button = ctk.CTkButton(
            self.control_widgets_frame, text="Ajouter une étape", command=self.add_stop
        )
        self.add_stop_button.grid(row=6, column=0, padx=5, pady=5, sticky="w")

        self.remove_stop_button = ctk.CTkButton(
            self.control_widgets_frame,
            text="Supprimer la dernière étape",
            command=self.remove_stop,
        )
        self.remove_stop_button.grid(row=6, column=1, padx=5, pady=5, sticky="e")

        # Train Type
        ctk.CTkLabel(self.control_widgets_frame, text="Type de trains:").grid(
            row=7, column=0, columnspan=2, padx=5, pady=10, sticky="w"
        )
        self.train_type_var = ctk.StringVar(value="TGV + TER")
        ctk.CTkRadioButton(
            self.control_widgets_frame,
            text="TGV uniquement",
            variable=self.train_type_var,
            value="TGV",
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=10)
        ctk.CTkRadioButton(
            self.control_widgets_frame,
            text="TER uniquement",
            variable=self.train_type_var,
            value="TER",
        ).grid(row=9, column=0, columnspan=2, sticky="w", padx=10)
        ctk.CTkRadioButton(
            self.control_widgets_frame,
            text="TGV + TER",
            variable=self.train_type_var,
            value="TGV + TER",
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=10)

        # Route Preference
        ctk.CTkLabel(self.control_widgets_frame, text="Préférence de trajet:").grid(
            row=11, column=0, columnspan=2, padx=5, pady=10, sticky="w"
        )
        self.route_preference_var = ctk.StringVar(value="Le plus rapide")
        ctk.CTkRadioButton(
            self.control_widgets_frame,
            text="Le plus rapide (durée)",
            variable=self.route_preference_var,
            value="Le plus rapide",
        ).grid(row=12, column=0, columnspan=2, sticky="w", padx=10)
        ctk.CTkRadioButton(
            self.control_widgets_frame,
            text="Moins de correspondances",
            variable=self.route_preference_var,
            value="Moins de correspondances",
        ).grid(row=13, column=0, columnspan=2, sticky="w", padx=10)

        # Calculate Button
        calculate_button = ctk.CTkButton(
            self.control_widgets_frame,
            text="Calculer l'itinéraire",
            command=self.calculate_route,
        )
        calculate_button.grid(row=14, column=0, columnspan=2, padx=5, pady=20)

        # --- Display Frame Widgets ---

        # Display travel map (packed directly into display_frame, below its title)
        self.map_canvas_frame = ctk.CTkFrame(self.display_frame)  # Using CTkFrame
        self.map_canvas_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.map_canvas = TkinterMapView(
            self.map_canvas_frame, width=400, height=260, corner_radius=0
        )
        # Definition of zoom scale and map position
        self.map_canvas.set_position(46.7111, 1.7191)
        self.map_canvas.set_zoom(5)
        self.map_canvas.pack(fill="both", expand=True)

        # Pre-load arrival icon to avoid error at runtime
        try:
            self.arrival_icon_image = tk.PhotoImage(
                file=r"C:\Users\nbaur\Documents\Travail Noelie\INSA\FIMI 2A\ISN\RailFinder\icon_arrivee.png"
            )
        except tk.TclError as e:
            print(
                f"Erreur lors du chargement de l'icône de l'arrivée: {e}. Le marqueur utilisera le style par défaut."
            )
            self.arrival_icon_image = None  # Set to None if loading fails

        self.route_details_frame = ctk.CTkFrame(self.display_frame)  # Using CTkFrame
        ctk.CTkLabel(
            self.route_details_frame,
            text="Détails du trajet",
            font=("Arial", 16, "bold"),
        ).pack(
            pady=(5, 0)
        )  # Title for the text box
        self.route_details_frame.pack(pady=10, padx=10, fill="both", expand=True)

        # Still tk.Text, will not be fully themed by CustomTkinter
        self.route_details_text = tk.Text(
            self.route_details_frame,
            height=10,
            width=50,
            wrap=tk.WORD,
            bg=self.get_ctk_color("CTkFrame"),  # Try to match background of CTkFrames
            fg=self.get_ctk_color("text"),  # Try to match text color
            insertbackground=self.get_ctk_color("text"),  # Cursor color
            selectbackground=self.get_ctk_color(
                "selection_color"
            ),  # Selection highlight color
            relief="flat",
            bd=0,
        )
        self.route_details_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.route_details_text.insert(
            tk.END, "Les détails de l'itinéraire s'afficheront ici..."
        )
        self.route_details_text.config(state=tk.DISABLED, font=("Arial", 16))

    def get_all_stop_names(self):
        """
        Retourne la liste de tous les noms de stops présents dans la base de données.
        Cette fonction est potentiellement longue et est appelée dans un thread séparé.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops")
        stops = [Stop(*row) for row in cursor.fetchall()]
        conn.close()
        return sorted(
            list(set(stop.stop_name for stop in stops if stop.stop_name))
        )  # Utiliser list(set(...)) pour les noms uniques

    def add_stop(self):
        if len(self.intermediate_stops_entries) < 5:
            row_num = len(self.intermediate_stops_entries)
            stop_label = ctk.CTkLabel(self.stops_frame, text=f"Étape {row_num + 1}:")
            stop_label.grid(row=row_num, column=0, padx=5, pady=2, sticky="w")
            stop_entry = ctk.CTkEntry(
                self.stops_frame, width=200
            )  # Adjusted width for CTkEntry
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
                "Erreur",
                "Veuillez entrer une date et une heure de départ valides (JJ/MM/AAAA HH:MM).",
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
        details += self.planner.journey_search(
            from_stop_id, to_stop_id, departure_datetime_utc, datetime.timedelta(1)
        )
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

    def _perform_calculation_in_thread(self):
        """Effectue la logique de calcul d'itinéraire dans un thread séparé."""
        try:
            departure = self.departure_city_entry.get()
            arrival = self.arrival_city_entry.get()
            stops = [
                entry.get()
                for _, entry in self.intermediate_stops_entries
                if entry.get()
            ]
            train_type = self.train_type_var.get()
            preference = self.route_preference_var.get()

            date_str = self.departure_date_entry.get()
            time_str = self.departure_time_entry.get()

            try:
                departure_datetime = datetime.datetime.strptime(
                    f"{date_str} {time_str}", "%d/%m/%Y %H:%M"
                )
                local_tz = pytz.timezone("Europe/Paris")
                departure_datetime = local_tz.localize(departure_datetime)
                departure_datetime_utc = departure_datetime.astimezone(pytz.utc)
            except ValueError:
                self.master.after(
                    0,
                    lambda: messagebox.showerror(
                        "Erreur",
                        "Veuillez entrer une date et une heure de départ valides (JJ/MM/AAAA HH:MM).",
                    ),
                )
                self.master.after(0, self.reset_ui_after_calculation)
                return

            if not departure or not arrival:
                self.master.after(
                    0,
                    lambda: messagebox.showerror(
                        "Erreur",
                        "Veuillez entrer une ville de départ et une ville d'arrivée.",
                    ),
                )
                self.master.after(0, self.reset_ui_after_calculation)
                return

            from_stop_id = self.get_stop_id_by_name(departure)
            to_stop_id = self.get_stop_id_by_name(arrival)

            details = f"Calcul de l'itinéraire:\n"
            details += f"Départ: {departure} (ID: {from_stop_id})\n"
            details += f"Arrivée: {arrival} (ID: {to_stop_id})\n"
            details += f"Date et heure de départ (locale): {departure_datetime.strftime('%d/%m/%Y %H:%M')}\n"
            details += f"Date et heure de départ (UTC): {departure_datetime_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            if stops:
                details += f"Étapes: {', '.join(stops)}\n"
            details += f"Type de trains: {train_type}\n"
            details += f"Préférence: {preference}\n\n"

            if from_stop_id and to_stop_id:
                journey_result = self.planner.journey_search(
                    from_stop_id,
                    to_stop_id,
                    departure_datetime_utc,
                    datetime.timedelta(days=1),
                )
                details += journey_result
            else:
                details += (
                    "Impossible de trouver les IDs des arrêts de départ ou d'arrivée.\n"
                )

            # Mettre à jour l'interface via master.after
            self.master.after(0, lambda: self._update_ui_after_calculation(details))

        except Exception as e:
            print(f"Erreur lors du calcul de l'itinéraire : {e}")
            self.master.after(
                0,
                lambda: messagebox.showerror(
                    "Erreur de calcul", f"Une erreur est survenue lors du calcul : {e}"
                ),
            )
            self.master.after(0, self.reset_ui_after_calculation)

    def _update_ui_after_calculation(self, details):
        """Met à jour les éléments de l'interface utilisateur après le calcul."""
        self.route_details_text.config(state=tk.NORMAL)
        self.route_details_text.delete(1.0, tk.END)
        self.route_details_text.insert(tk.END, details)
        self.route_details_text.config(state=tk.DISABLED)

        self.tracage_map()

        self.loading_bar.stop()
        self.loading_frame.place_forget()
        self.reset_ui_after_calculation()

    def _set_input_states(self, state):
        """Active ou désactive tous les champs de saisie de l'UI."""
        self.departure_city_entry.configure(state=state)
        self.arrival_city_entry.configure(state=state)
        self.departure_date_entry.configure(state=state)
        self.departure_time_entry.configure(state=state)
        self.add_stop_button.configure(state=state)
        self.remove_stop_button.configure(state=state)
        for _, entry in self.intermediate_stops_entries:
            entry.configure(state=state)

    def reset_ui_after_calculation(self):
        """Réactive tous les champs de saisie après le calcul ou en cas d'erreur."""
        self._set_input_states("normal")

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
            x = widget.winfo_rootx() - self.master.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height() - self.master.winfo_rooty()

            self.suggestions_listbox.place(x=x, y=y)
            self.suggestions_listbox.lift()
            self.suggestions_listbox.selection_set(0)
            self.suggestions_listbox.activate(0)
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
                self.suggestions_listbox.see(idx - 1)
                self.active_entry.delete(0, tk.END)
                self.active_entry.insert(0, self.suggestions_listbox.get(idx - 1))

    def navigate_down(self, event):
        cur = self.suggestions_listbox.curselection()
        size = self.suggestions_listbox.size()
        if cur:
            idx = cur[0]
            if idx < size - 1:
                self.suggestions_listbox.selection_clear(0, tk.END)
                self.suggestions_listbox.selection_set(idx + 1)
                self.suggestions_listbox.activate(idx + 1)
                self.suggestions_listbox.see(idx + 1)
                self.active_entry.delete(0, tk.END)
                self.active_entry.insert(0, self.suggestions_listbox.get(idx + 1))

    # FONCTION AMÉLIORÉE pour récupérer les couleurs du thème CustomTkinter
    def get_ctk_color(self, key_name):
        """
        Récupère une couleur du thème CustomTkinter actuel en fonction d'une clé
        et du mode d'apparence (clair/sombre).
        Garantit de retourner une chaîne de couleur unique et valide pour Tkinter.
        """
        try:
            theme_data = ctk.ThemeManager.theme["CTk"]
            appearance_mode = ctk.get_appearance_mode()  # "light" or "dark"

            # Mappage des noms "logiques" aux clés réelles du thème CTk
            color_key_map = {
                "CTkFrame": "fg_color",
                "text": "text_color",
                "selection_color": "button_color",  # Couleur des boutons (souvent utilisée pour la sélection)
            }

            ctk_color_key = color_key_map.get(key_name)

            if ctk_color_key and ctk_color_key in theme_data:
                color_value = theme_data[ctk_color_key]

                # Cas 1: C'est un tuple (couleur_claire, couleur_sombre) - standard CustomTkinter
                if isinstance(color_value, tuple) and len(color_value) == 2:
                    return (
                        color_value[0] if appearance_mode == "light" else color_value[1]
                    )

                # Cas 2: C'est une chaîne, potentiellement "couleur_claire couleur_sombre"
                elif isinstance(color_value, str):
                    # Utiliser .strip().split() pour gérer les espaces multiples et les espaces de début/fin
                    parts = color_value.strip().split()

                    if len(parts) == 2:  # Format "couleur_claire couleur_sombre" trouvé
                        return parts[0] if appearance_mode == "light" else parts[1]
                    else:
                        # C'est une chaîne de couleur unique (ex: "red", "#RRGGBB"), ou un format inattendu.
                        # On la retourne telle quelle, en espérant que Tkinter la reconnaisse.
                        return color_value

            # Fallback pour les clés CTk connues qui n'ont pas pu être résolues ou les clés personnalisées
            print(
                f"Attention: La couleur de thème CTk pour '{key_name}' (mappée à '{ctk_color_key}') n'a pas été trouvée ou n'a pas pu être analysée. Utilisation d'une couleur générique par défaut."
            )
            if appearance_mode == "light":
                # Fournir des noms de couleurs Tkinter standard pour le mode clair
                if key_name == "CTkFrame":
                    return "SystemButtonFace"  # Fond de fenêtre par défaut
                elif key_name == "text":
                    return "black"
                elif key_name == "selection_color":
                    return "SystemHighlight"  # Couleur de sélection par défaut
                else:
                    return "black"  # Couleur de texte générique
            else:
                # Fournir des noms de couleurs Tkinter standard pour le mode sombre (approximations)
                if key_name == "CTkFrame":
                    return "#2b2b2b"  # Fond gris foncé
                elif key_name == "text":
                    return "white"
                elif key_name == "selection_color":
                    return "#3e70cf"  # Surlignage bleu plus foncé
                else:
                    return "white"  # Couleur de texte générique

        except Exception as e:
            print(
                f"ERREUR CRITIQUE dans get_ctk_color pour '{key_name}': {e}. Utilisation d'une couleur par défaut absolue."
            )
            # Fallback absolu en cas d'erreur inattendue
            if ctk.get_appearance_mode() == "light":
                return "white"
            else:
                return "#2b2b2b"

    # Function to get latitude and longitude by stop name
    def get_stop_lat_lon_by_name(self, stop_name):
        """
        Retourne (lat, lon) pour un stop_name donné, ou None si non trouvé.
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
        # Clear existing markers and lines before drawing new ones
        self.map_canvas.delete_all_markers()
        self.map_canvas.delete_all_lines()

        self.departure = self.departure_city_entry.get()
        self.arrival = self.arrival_city_entry.get()

        dep_coords = self.get_stop_lat_lon_by_name(self.departure)
        arr_coords = self.get_stop_lat_lon_by_name(self.arrival)

        if dep_coords:
            self.dep_lat, self.dep_lon = dep_coords
            self.map_canvas.set_marker(self.dep_lat, self.dep_lon, text=self.departure)
        else:
            print(f"Coordonnées non trouvées pour le départ: {self.departure}")

        if arr_coords:
            self.arr_lat, self.arr_lon = arr_coords
            # Use the pre-loaded image if available, otherwise use default marker
            if self.arrival_icon_image:
                self.map_canvas.set_marker(
                    self.arr_lat,
                    self.arr_lon,
                    icon=self.arrival_icon_image,
                    text=self.arrival,
                )
            else:
                self.map_canvas.set_marker(
                    self.arr_lat, self.arr_lon, text=self.arrival
                )
        else:
            print(f"Coordonnées non trouvées pour l'arrivée: {self.arrival}")

        # Draw a line between departure and arrival if both are found
        if dep_coords and arr_coords:
            self.map_canvas.set_path([dep_coords, arr_coords], width=3, color="blue")

    # Ajoute cette méthode dans ta classe RoutePlannerApp
    def get_stop_id_by_name(self, stop_name):
        """
        Retourne le stop_id pour un stop_name donné, ou None si non trouvé.
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
    ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
    ctk.set_default_color_theme(
        "blue"
    )  # Themes: "blue" (default), "dark-blue", "green"

    root = ctk.CTk()  # Use ctk.CTk() for the main window
    app = RoutePlannerApp(root)
    root.mainloop()
