import tkinter as tk

def trajet_simple_temps(critere):
    """
    Calcul le plus court trajet en temps entre deux gares
    """

def trajet_simple_correspondances(critere):
    """
    Calcul le plus court trajet en temps entre deux gares
    """

class Trajet():

    def __init__(self,ville_depart,_ville_arrivee,horaire_depart,horaire_arrivee,type):
        self.ville_depart = ville_depart
        self.ville_arrivee = _ville_arrivee
        self.horaire_depart = horaire_depart
        self.horaire_arrivee = horaire_arrivee
        self.duree = self.horaire_arrivee - self.horaire_depart
        self.type = type

def auto_completion(texte):
    """
    Renvoie une liste des mots ressemblant aux texte dans le dictionnaire des gares
    """

class Etape():
    def __init__(self,ville,duree):
        self.ville = ville
        self.duree = duree

class main_Fenetre(tk.Tk):

    def __init__(self):
        super().__init__()
        self.label_depart = tk.Label(text="Départ")
        self.label_depart.grid(column=0, row=0)
        self.text_depart = tk.Entry(text="Départ")
        self.text_depart.grid(column=1, row=0)
        self.label_arrivee = tk.Label(text="Arrivée")
        self.label_arrivee.grid(column=0, row=1)
        self.text_arrivee = tk.Entry(text="Arrivée")
        self.text_arrivee.grid(column=1, row=1)
        self.label_date = tk.Label(text="Date")
        self.label_date.grid(column=0, row=2)
        self.jour = tk.StringVar(self)
        self.jour.set("1")  # Valeur par défaut
        self.mois = tk.StringVar(self)
        self.mois.set("1")  # Valeur par défaut
        self.annee = tk.StringVar(self)
        self.annee.set("2025")  # Valeur par défaut

        # Liste déroulante pour les jours de 1 à 31
        self.menu_jour = tk.OptionMenu(self, self.jour, *[str(i) for i in range(1, 32)])
        self.menu_jour.grid(column=1, row=2)

        self.menu_mois = tk.OptionMenu(self, self.mois, *[str(i) for i in range(1, 13)])
        self.menu_mois.grid(column=2, row=2)

        self.menu_annee = tk.OptionMenu(self, self.annee, *[str(i) for i in range(2025, 2030)])
        self.menu_annee.grid(column=3, row=2)

        self.button_etape = tk.Button(text="Ajouter Etape")
        self.button_etape.grid(column=0, row=3, columnspan=3)
        self.button_etape.bind("<Button-1>", self.ajouter_etapes)

    def ajouter_etapes(self, event):
        fenetre_etape = Fenetre_Etape()
        fenetre_etape.mainloop()

class Fenetre_Etape(tk.Tk):

    def __init__(self):
        super().__init__()
        self.ville = tk.StringVar()
        self.date_debut = tk.StringVar()
        self.date_debut.set("JJ/MM/AAAA")
        self.date_fin = tk.StringVar()

        self.ville_label = tk.Label(text="Ville")
        self.ville_label.grid(column=0,row=0)

        self.ville_entry = tk.Entry(text="Ville")
        self.ville_entry.grid(column=1,row=0)

        self.date_debut_label = tk.Label(text="Début")
        self.date_debut_label.grid(column=0,row=1)

        self.date_debut_entry = tk.Entry(textvariable=self.date_debut)
        self.date_debut_entry.grid(column=1,row=1)


fenetre_0= main_Fenetre()
fenetre_0.mainloop()
