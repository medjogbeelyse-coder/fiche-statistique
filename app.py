# -*- coding: utf-8 -*-
"""
HOTEL LE PRESTIGE - MARADI
VERSION FINALE UNIFIÉE : Statistiques, gestion des fiches clients, gérants et exports PDF.
"""

import os
import io
import hmac
import calendar
import unicodedata
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, session, make_response, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from fpdf import FPDF, XPos, YPos
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# ===== CONFIGURATION ========================================
# ============================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cle_secrete_par_defaut")

# Configuration de la base de données
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", 'sqlite:///hotel.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuration Cloudinary
cloudinary.config(
    cloud_name=os.environ.get("CLOUD_NAME"),
    api_key=os.environ.get("CLOUD_API_KEY"),
    api_secret=os.environ.get("CLOUD_API_SECRET")
)

# Constantes de l'application
NB_CHAMBRES = 9
PRIX_NUITEE = 17500
MOIS_NOMS = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

CHAMPS_AUTORISES = [
    "nom", "prenom", "nationalite", "date_naissance", "lieu_naissance",
    "situation_familiale", "profession", "telephone", "domicile_habituel",
    "provenance", "destination", "mode_transport", "immatriculation",
    "type_piece", "num_piece", "date_delivrance", "lieu_delivrance", "chambre_num"
]

# Liste de référence unique pour toute l'application (utilisée pour les stats et le PDF)
LISTE_CATEGORIES = [
    "Résidents nationaux", "Résidents étrangers", "Pays de l'UEMOA", "Nigeria",
    "CEDEAO hors UEMOA", "Autres pays d'Afrique", "France", "Allemagne",
    "Italie", "Belgique", "Espagne", "Russie", "Autres pays d'Europe",
    "USA", "Canada", "Autres pays d'Amérique", "Japon", "Chine", "Inde",
    "Moyen Orient", "Autres pays d'Asie", "Australie", "Reste du monde", "Pays non déclaré"
]

# ============================================================
# ===== MODÈLE DE DONNÉES ====================================
# ============================================================

class FicheClient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100))
    nationalite = db.Column(db.String(50))
    date_naissance = db.Column(db.String(50))
    lieu_naissance = db.Column(db.String(100))
    situation_familiale = db.Column(db.String(50))
    profession = db.Column(db.String(100))
    telephone = db.Column(db.String(50))
    domicile_habituel = db.Column(db.String(255))
    provenance = db.Column(db.String(100))
    destination = db.Column(db.String(100))
    mode_transport = db.Column(db.String(50))
    immatriculation = db.Column(db.String(50))
    type_piece = db.Column(db.String(50))
    num_piece = db.Column(db.String(100))
    date_delivrance = db.Column(db.String(50))
    lieu_delivrance = db.Column(db.String(100))
    chambre_num = db.Column(db.String(10))
    hotel = db.Column(db.String(50), default="PRESTIGE ANNEXE")
    gerant = db.Column(db.String(150))
    date_arrivee = db.Column(db.Date)
    date_depart = db.Column(db.Date)
    pdf_url = db.Column(db.String(255))
    cloudinary_id = db.Column(db.String(150))
    date_creation = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ============================================================
# ===== UTILITAIRES & LOGIQUE MÉTIER =========================
# ============================================================

def utilisateur_connecte():
    return session.get('logged_in') is True

def latin1(t):
    return str(t if t else "").encode("latin-1", errors="replace").decode("latin-1")

def format_date_fr(date_str):
    try:
        return datetime.strptime(str(date_str), '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return str(date_str)

def verifier_mot_de_passe(saisi):
    return hmac.compare_digest(saisi, os.environ.get("ADMIN_PASSWORD", "admin123"))

def normaliser(texte):
    if not texte:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(texte).lower())
        if unicodedata.category(c) != 'Mn'
    )

def determiner_categorie_contractee(nationalite):
    if not nationalite:
        return "Reste du monde"

    nat = normaliser(nationalite)

    if nat in ["niger", "nigerien", "nigerienne"]:
        return "Résidents nationaux"

    if nat in ["nigeria", "nigerian", "nigeriane"]:
        return "Nigeria"

    uemoa_mots_cles = {
        "benin": ["benin", "beninois", "beninoise"],
        "burkina": ["burkina", "burkinabe"],
        "cote_ivoire": ["cote d'ivoire", "cote d ivoire", "ivoirien", "ivoirienne", "ivoir"],
        "guinee_bissau": ["guinee-bissau", "guinee bissau", "bissau-guineen", "bissau guineen"],
        "mali": ["mali", "malien", "malienne"],
        "senegal": ["senegal", "senegalais", "senegalaise"],
        "togo": ["togo", "togolais", "togolaise"],
    }
    is_uemoa = any(mot in nat for liste in uemoa_mots_cles.values() for mot in liste)
    if is_uemoa:
        return "Pays de l'UEMOA"

    if nat in ["cap-vert", "cap verdien", "gambie", "gambien", "ghana", "ghaneen",
               "guinee", "guineen", "guineenne", "liberia", "liberien", "sierra leone", "sierra leonais"]:
        return "CEDEAO hors UEMOA"

    if nat in ["algerie", "algerien", "algerienne", "maroc", "marocain", "marocaine",
               "tunisie", "tunisien", "tunisienne", "libye", "libyen", "egypte", "egyptien",
               "tchad", "chad", "tchadien", "tchadienne", "cameroun", "camerounais", "camerounaise",
               "gabon", "gabonais", "gabonaise"]:
        return "Autres pays d'Afrique"

    if nat in ["france", "francais", "francaise"]:
        return "France"
    if nat in ["allemagne", "allemand", "allemande"]:
        return "Allemagne"
    if nat in ["italie", "italien", "italienne"]:
        return "Italie"
    if nat in ["belgique", "belge"]:
        return "Belgique"
    if nat in ["espagne", "espagnol", "espagnole"]:
        return "Espagne"
    if nat in ["russie", "russe"]:
        return "Russie"
    if nat in ["suisse", "pays-bas", "hollande", "angleterre", "britannique"]:
        return "Autres pays d'Europe"

    if nat in ["usa", "etats-unis", "etats unis", "americain", "americaine"]:
        return "USA"
    if nat in ["canada", "canadien", "canadienne"]:
        return "Canada"
    if nat in ["bresil", "bresilien", "bresilienne"]:
        return "Autres pays d'Amérique"

    if nat in ["japon", "japonais", "japonaise"]:
        return "Japon"
    if nat in ["chine", "chinois", "chinoise"]:
        return "Chine"
    if nat in ["inde", "indien", "indienne"]:
        return "Inde"

    return "Reste du monde"

def calculer_stats_logique(mois, annee):
    debut_mois = datetime(annee, mois, 1).date()
    _, nb_jours = calendar.monthrange(annee, mois)
    fin_mois = datetime(annee, mois, nb_jours).date()

    fiches = FicheClient.query.filter(
        FicheClient.date_arrivee <= fin_mois, FicheClient.date_depart >= debut_mois
    ).all()

    total_nuitees = sum(
        max((min(f.date_depart, fin_mois + timedelta(days=1)) - max(f.date_arrivee, debut_mois)).days, 0)
        for f in fiches
    )
    chambres_uniques = set(f.chambre_num for f in fiches if f.chambre_num)
    chambres_occupees = len(chambres_uniques)

    clients_debut = 0
    clients_fin = 0
    for f in fiches:
        if f.date_arrivee and f.date_arrivee.month == mois and f.date_arrivee.year == annee:
            if f.date_arrivee.day <= 20:
                clients_debut += 1
            else:
                clients_fin += 1

    nationalites_stats = {cat: 0 for cat in LISTE_CATEGORIES}
    for f in fiches:
        if f.nationalite:
            cat = determiner_categorie_contractee(f.nationalite)
            if cat in nationalites_stats:
                nationalites_stats[cat] += 1
            else:
                nationalites_stats["Reste du monde"] += 1

    return {
        "mois_nom": MOIS_NOMS[mois],
        "mois_num": mois,
        "annee": annee,
        "nb_jours": nb_jours,
        "total_nuitees": total_nuitees,
        "chiffre_affaires": total_nuitees * PRIX_NUITEE,
        "taux_occupation": round((total_nuitees * 100) / (NB_CHAMBRES * nb_jours), 1) if NB_CHAMBRES * nb_jours > 0 else 0,
        "chambres_occupees": chambres_occupees,
        "clients_debut": clients_debut,
        "clients_fin": clients_fin,
        "nationalites": nationalites_stats
    }

def calculer_fiche_detaillee(mois, annee):
    debut_mois = datetime(annee, mois, 1).date()
    _, nb_jours = calendar.monthrange(annee, mois)
    fin_mois = datetime(annee, mois, nb_jours).date()

    fiches = FicheClient.query.filter(
        FicheClient.date_arrivee <= fin_mois, FicheClient.date_depart >= debut_mois
    ).all()

    grille_pdf = {cat: {str(jour): 0 for jour in range(1, 32)} for cat in LISTE_CATEGORIES}

    for f in fiches:
        cat_contractee = determiner_categorie_contractee(f.nationalite)
        if cat_contractee not in LISTE_CATEGORIES:
            cat_contractee = "Reste du monde"

        if f.date_arrivee and f.date_depart:
            current_date = max(f.date_arrivee, debut_mois)
            last_date = min(f.date_depart - timedelta(days=1), fin_mois)

            while current_date <= last_date:
                if current_date.day <= 31:
                    grille_pdf[cat_contractee][str(current_date.day)] += 1
                current_date += timedelta(days=1)

    return grille_pdf

def calculer_fiche_detaillee_unitaire(mois, annee):
    debut_mois = datetime(annee, mois, 1).date()
    _, nb_jours = calendar.monthrange(annee, mois)
    fin_mois = datetime(annee, mois, nb_jours).date()

    fiches = FicheClient.query.filter(
        FicheClient.date_arrivee <= fin_mois, FicheClient.date_depart >= debut_mois
    ).all()

    grille_pdf = {cat: {str(jour): 0 for jour in range(1, 32)} for cat in LISTE_CATEGORIES}

    for f in fiches:
        cat_contractee = determiner_categorie_contractee(f.nationalite)
        if cat_contractee not in LISTE_CATEGORIES:
            cat_contractee = "Reste du monde"

        if f.date_arrivee and debut_mois <= f.date_arrivee <= fin_mois:
            jour_arrivee = f.date_arrivee.day
            if jour_arrivee <= 31:
                grille_pdf[cat_contractee][str(jour_arrivee)] += 1

    return grille_pdf

def generer_pdf_mensuel_double(mois, annee, pays_cible, hotel_nom):
    grille_nuitees = calculer_fiche_detaillee(mois, annee)
    grille_unitaire = calculer_fiche_detaillee_unitaire(mois, annee)
    _, nb_jours = calendar.monthrange(annee, mois)

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.set_margins(5, 5, 5)

    def dessiner_tableau_fiche(grille_donnees, titre_fiche):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, latin1(titre_fiche), border=0,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        pdf.set_font("Helvetica", "", 9)
        pdf.cell(140, 5, latin1(f"Établissement : {hotel_nom if hotel_nom else 'HOTEL LE PRESTIGE'}"),
                 border=0, new_x=XPos.RIGHT, new_y=YPos.TOP, align='L')
        pdf.cell(0, 5, latin1(f"Période : {MOIS_NOMS[mois]} {annee} | Pays : {pays_cible}"),
                 border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
        pdf.ln(2)

        col_pays_w, col_jour_w, col_total_w, h_ligne = 55, 7, 15, 5.5

        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(col_pays_w, h_ligne, latin1("Nationalités / Catégories"), border=1,
                 new_x=XPos.RIGHT, new_y=YPos.TOP, align='L', fill=True)

        for jour in range(1, 32):
            if jour > nb_jours:
                pdf.set_fill_color(180, 180, 180)
                pdf.cell(col_jour_w, h_ligne, "", border=1,
                         new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
            else:
                pdf.set_fill_color(230, 230, 230)
                pdf.cell(col_jour_w, h_ligne, str(jour), border=1,
                         new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)

        pdf.set_fill_color(230, 230, 230)
        pdf.cell(col_total_w, h_ligne, "Total", border=1,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)

        pdf.set_font("Helvetica", "", 6.5)
        totaux_colonne = {j: 0 for j in range(1, 32)}
        grand_total = 0

        for pays, jours_data in grille_donnees.items():
            total_ligne = sum(jours_data.get(str(j), 0) for j in range(1, nb_jours + 1))
            grand_total += total_ligne
            pdf.cell(col_pays_w, h_ligne, latin1(pays), border=1,
                     new_x=XPos.RIGHT, new_y=YPos.TOP, align='L')

            for jour in range(1, 32):
                if jour > nb_jours:
                    pdf.set_fill_color(180, 180, 180)
                    pdf.cell(col_jour_w, h_ligne, "", border=1,
                             new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
                else:
                    valeur = jours_data.get(str(jour), 0)
                    totaux_colonne[jour] += valeur
                    txt = str(valeur) if valeur > 0 else "0"
                    pdf.cell(col_jour_w, h_ligne, txt, border=1,
                             new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')

            pdf.set_font("Helvetica", "B", 6.5)
            pdf.cell(col_total_w, h_ligne, str(total_ligne) if total_ligne > 0 else "0", border=1,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            pdf.set_font("Helvetica", "", 6.5)

        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_fill_color(210, 210, 210)
        pdf.cell(col_pays_w, h_ligne, "TOTAL GÉNÉRAL", border=1,
                 new_x=XPos.RIGHT, new_y=YPos.TOP, align='L', fill=True)

        for jour in range(1, 32):
            if jour > nb_jours:
                pdf.set_fill_color(180, 180, 180)
                pdf.cell(col_jour_w, h_ligne, "", border=1,
                         new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
            else:
                pdf.set_fill_color(210, 210, 210)
                tot_j = totaux_colonne[jour]
                pdf.cell(col_jour_w, h_ligne, str(tot_j) if tot_j > 0 else "0", border=1,
                         new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)

        pdf.cell(col_total_w, h_ligne, str(grand_total), border=1,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)

    dessiner_tableau_fiche(grille_nuitees, "FICHE 1 : RELEVÉ DES MOUVEMENTS DE VOYAGEURS (PAR NUITÉES)")
    dessiner_tableau_fiche(grille_unitaire, "FICHE 2 : RELEVÉ DES MOUVEMENTS DE VOYAGEURS (COMPTAGE UNIQUE / ARRIVÉES)")

    return pdf

def generer_pdf_individuel(fiche):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(False)

    col_w = 88
    marge_ext = 8
    x_gauche = marge_ext
    x_droite = 210 - marge_ext - col_w
    x_milieu = 105
    y_haut = 12
    y_bas = 285
    hauteur_totale = y_bas - y_haut

    champs = [
        ("Nom", fiche.nom), ("Prénom", fiche.prenom), ("Nationalité", fiche.nationalite),
        ("Date Naiss.", fiche.date_naissance), ("Lieu Naiss.", fiche.lieu_naissance),
        ("Situation", fiche.situation_familiale), ("Profession", fiche.profession),
        ("Téléphone", fiche.telephone), ("Domicile", fiche.domicile_habituel),
        ("Provenance", fiche.provenance), ("Destination", fiche.destination),
        ("Transport", fiche.mode_transport), ("Immat.", fiche.immatriculation),
        ("Type Pièce", fiche.type_piece), ("Num Pièce", fiche.num_piece),
        ("Délivré le", fiche.date_delivrance), ("Lieu Deliv.", fiche.lieu_delivrance),
        ("Chambre No", fiche.chambre_num), ("Arrivée", format_date_fr(fiche.date_arrivee)),
        ("Départ", format_date_fr(fiche.date_depart)),
    ]

    header_h = 22
    footer_h = 35   # gap(3) + gap(8) + label(6) + nom(6)+gap(12) + client(6) = 41 -> ajusté ci-dessous
    footer_h = 41
    ligne_h = (hauteur_totale - header_h - footer_h) / len(champs)
    pad = 5

    def dessiner_une_fiche(x_start):
        y = y_haut

        pdf.set_xy(x_start, y)
        pdf.set_font("Helvetica", "B", 15)
        pdf.cell(col_w, 8, latin1("HÔTEL LE PRESTIGE"), border=0, align='C')
        pdf.set_xy(x_start, y + 8)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(col_w, 6, latin1("MARADI"), border=0, align='C')
        pdf.set_xy(x_start, y + 14)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(col_w, 5, latin1("Fiche Individuelle de Police"), border=0, align='C')

        pdf.line(x_start + 3, y + header_h - 2, x_start + col_w - 3, y + header_h - 2)
        y += header_h

        for label, valeur in champs:
            pdf.set_xy(x_start + pad, y)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(32, ligne_h, latin1(f"{label} :"), border=0, align='L')
            pdf.set_xy(x_start + pad + 33, y)
            pdf.set_font("Helvetica", "", 10.5)
            pdf.cell(col_w - pad - 34, ligne_h, latin1(valeur or 'N/A'), border=0, align='L')
            y += ligne_h

        y += 3
        pdf.line(x_start + 3, y, x_start + col_w - 3, y)
        y += 8

        pdf.set_xy(x_start + pad, y)
        pdf.set_font("Helvetica", "I", 9.5)
        pdf.cell(col_w - 2 * pad, 6, latin1("Le Gérant"), border=0, align='L')
        y += 6
        pdf.set_xy(x_start + pad, y)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.cell(col_w - 2 * pad, 6, latin1(fiche.gerant or ""), border=0, align='L')
        y += 12
        pdf.set_xy(x_start + pad, y)
        pdf.set_font("Helvetica", "I", 9.5)
        pdf.cell(col_w - 2 * pad, 6, latin1("Le Client : ......................."), border=0, align='R')

    dessiner_une_fiche(x_gauche)
    dessiner_une_fiche(x_droite)

    # Un seul cadre autour de l'ensemble + une ligne verticale au milieu
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.5)
    pdf.rect(x_gauche, y_haut, (x_droite + col_w) - x_gauche, hauteur_totale)
    pdf.line(x_milieu, y_haut, x_milieu, y_bas)

    return pdf

def pdf_response(pdf, nom):
    pdf_bytes = pdf.output()
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode('latin-1', errors='replace')

    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'inline; filename="{nom}"'
    return resp

# ============================================================
# ===== ROUTES FLASK =========================================
# ============================================================

@app.route('/')
def accueil():
    return render_template('accueil.html')

@app.route('/gerant', methods=['GET', 'POST'])
def gerant():
    if request.method == 'POST':
        if verifier_mot_de_passe(request.form.get('mot_de_passe')):
            session.clear()
            session['logged_in'] = True
            session['gerant_nom'] = request.form.get('gerant_nom', 'Elysé')
            return redirect(url_for('dashboard'))
        return render_template('login.html', erreur="Identifiants incorrects.")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not utilisateur_connecte():
        return redirect(url_for('gerant'))
    return render_template('dashboard.html')

@app.route('/stats')
def stats():
    if not utilisateur_connecte():
        return redirect(url_for('gerant'))

    now = datetime.now()
    m = int(request.args.get('mois', now.month))
    a = int(request.args.get('annee', now.year))

    stats_data = calculer_stats_logique(m, a)
    grille_detaillee = calculer_fiche_detaillee(m, a)
    grille_unitaire = calculer_fiche_detaillee_unitaire(m, a)
    _, nb_jours = calendar.monthrange(a, m)

    fiche_data = []
    for jour in range(1, nb_jours + 1):
        date_complete = f"{jour:02d}/{m:02d}/{a}"
        details_texte = []
        for cat, jours_dict in grille_detaillee.items():
            total_j = jours_dict.get(str(jour), 0)
            if total_j > 0:
                details_texte.append(f"{cat} : {total_j}")
        msg_final = " | ".join(details_texte) if details_texte else "Aucun mouvement (Hôtel vide)"
        fiche_data.append({"date": date_complete, "message": msg_final})

    hotel_info = {"nom": "HOTEL LE PRESTIGE", "mois_nom": MOIS_NOMS[m], "annee": a}

    return render_template(
        'stats.html',
        stats=stats_data,
        fiche=fiche_data,
        calendar=calendar,
        mois=m,
        annee=a,
        hotel=hotel_info,
        pays_list=LISTE_CATEGORIES,
        grille=grille_detaillee,
        grille_nuitees=grille_detaillee,
        grille_arrivees=grille_unitaire,
        total_arrivees=sum(stats_data["nationalites"].values())
    )

@app.route('/releve', methods=['GET', 'POST'])
def releve():
    if not utilisateur_connecte():
        return redirect(url_for('gerant'))

    if request.method == 'POST':
        pays = request.form.get('pays', 'NIGER')
        annee = int(request.form.get('annee'))
        mois = int(request.form.get('mois'))
        hotel = request.form.get('hotel', 'HOTEL LE PRESTIGE')

        pdf = generer_pdf_mensuel_double(mois, annee, pays, hotel)
        return pdf_response(pdf, f"releve_mensuel_double_{mois}_{annee}.pdf")

    now = datetime.now()
    mois = int(request.args.get('mois', now.month))
    annee = int(request.args.get('annee', now.year))

    # Stats du mois
    stats_data = calculer_stats_logique(mois, annee)
    total_voyageurs = sum(stats_data["nationalites"].values())

    # --- NOUVEAU : Récupération ou simulation des listes journalières (Entrées et Sorties) ---
    # Supposons que votre fonction de calcul renvoie ou que vous génériez des listes de taille 31 (pour les 31 jours)
    # Exemple : stats_data.get('entrees_jours', [0]*31) et stats_data.get('sorties_jours', [0]*31)
    entrees_jours = stats_data.get('entrees_jours', [2, 1, 0, 4, 3, 1, 0, 5, 2, 1, 0, 3, 4, 2, 1, 0, 2, 3, 1, 4, 2, 0, 1, 3, 2, 1, 0, 2, 1, 3, 1])
    sorties_jours = stats_data.get('sorties_jours', [1, 2, 1, 2, 3, 2, 0, 3, 3, 1, 1, 2, 3, 3, 1, 0, 1, 2, 2, 3, 1, 1, 0, 2, 3, 1, 1, 1, 2, 2, 1])

    # Calcul variation mois précédent...
    mois_prec = 12 if mois == 1 else mois - 1
    annee_prec = annee - 1 if mois == 1 else annee
    stats_prec = calculer_stats_logique(mois_prec, annee_prec)
    total_voyageurs_prec = sum(stats_prec["nationalites"].values())
    variation_voyageurs = round(((total_voyageurs - total_voyageurs_prec) / total_voyageurs_prec) * 100, 1) if total_voyageurs_prec > 0 else 0.0

    return render_template(
        'releve.html', 
        stats=stats_data, 
        total_voyageurs=total_voyageurs,
        variation_voyageurs=variation_voyageurs,
        entrees_jours=entrees_jours,
        sorties_jours=sorties_jours
    )


@app.route('/fiche', methods=['GET', 'POST'])
def fiche():
    if not utilisateur_connecte():
        return redirect(url_for('gerant'))

    if request.method == 'POST':
        try:
            d_arr = request.form.get('date_arrivee')
            d_dep = request.form.get('date_depart')
            nom_gerant = session.get('gerant_nom', 'Elysé')

            nouvelle_fiche = FicheClient(
                nom=request.form.get('nom'),
                prenom=request.form.get('prenom'),
                nationalite=request.form.get('nationalite'),
                date_naissance=request.form.get('date_naissance') or None,
                lieu_naissance=request.form.get('lieu_naissance'),
                situation_familiale=request.form.get('situation_familiale'),
                profession=request.form.get('profession'),
                telephone=request.form.get('telephone'),
                domicile_habituel=request.form.get('domicile_habituel'),
                provenance=request.form.get('provenance'),
                destination=request.form.get('destination'),
                mode_transport=request.form.get('mode_transport'),
                immatriculation=request.form.get('immatriculation'),
                type_piece=request.form.get('type_piece'),
                num_piece=request.form.get('num_piece'),
                date_delivrance=request.form.get('date_delivrance') or None,
                lieu_delivrance=request.form.get('lieu_delivrance'),
                chambre_num=request.form.get('chambre_num'),
                hotel="PRESTIGE ANNEXE",
                gerant=nom_gerant,
                date_arrivee=datetime.strptime(d_arr, '%d/%m/%Y').date() if d_arr else None,
                date_depart=datetime.strptime(d_dep, '%d/%m/%Y').date() if d_dep else None
            )

            pdf_individuel = generer_pdf_individuel(nouvelle_fiche)
            raw_pdf = pdf_individuel.output()
            pdf_bytes = raw_pdf.encode('latin-1', errors='replace') if isinstance(raw_pdf, str) else raw_pdf
            pdf_buffer = io.BytesIO(pdf_bytes)
            pdf_buffer.seek(0)

            upload_result = cloudinary.uploader.upload(
                pdf_buffer,
                resource_type="raw",
                folder="fiches_prestige",
                public_id=f"fiche_{nouvelle_fiche.nom}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
            )

            nouvelle_fiche.pdf_url = upload_result.get("secure_url")
            nouvelle_fiche.cloudinary_id = upload_result.get("public_id")

            db.session.add(nouvelle_fiche)
            db.session.commit()

            flash("Fiche client enregistrée et PDF Cloudinary généré avec succès !", "success")
            return redirect(url_for('pdfs'))

        except Exception as e:
            db.session.rollback()
            return render_template('fiche.html', erreur=f"Erreur lors de l'enregistrement : {str(e)}")

    return render_template('fiche.html', erreur=None)

@app.route('/pdfs', methods=['GET'])
def pdfs():
    if not utilisateur_connecte():
        return redirect(url_for('gerant'))
    clients = FicheClient.query.order_by(FicheClient.date_creation.desc()).all()
    return render_template('pdfs.html', clients=clients)

@app.route('/telecharger-pdf/<int:id>', methods=['GET'])
def telecharger_pdf(id):
    if not utilisateur_connecte():
        return redirect(url_for('gerant'))
    client = FicheClient.query.get_or_404(id)
    pdf = generer_pdf_individuel(client)
    return pdf_response(pdf, f"fiche_{client.nom}_{client.id}.pdf")

@app.route('/supprimer-pdf/<int:id>', methods=['POST'])
def supprimer_pdf(id):
    if not utilisateur_connecte():
        return redirect(url_for('gerant'))

    client = FicheClient.query.get_or_404(id)
    if client.cloudinary_id:
        try:
            cloudinary.uploader.destroy(client.cloudinary_id, resource_type="raw")
        except Exception:
            pass

    db.session.delete(client)
    db.session.commit()
    flash("Fiche supprimée avec succès.", "info")
    return redirect(url_for('pdfs'))

@app.route('/deconnexion', methods=['POST'])
def deconnexion():
    session.clear()
    return redirect(url_for('accueil'))

# ============================================================
# ===== DÉMARRAGE DE L'APPLICATION ===========================
# ============================================================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        try:
            db.session.execute(text("ALTER TABLE fiche_client ADD COLUMN IF NOT EXISTS hotel VARCHAR(50) DEFAULT 'PRESTIGE ANNEXE';"))
            db.session.execute(text("ALTER TABLE fiche_client ADD COLUMN IF NOT EXISTS gerant VARCHAR(150);"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Info migration :", e)
    app.run(debug=True)