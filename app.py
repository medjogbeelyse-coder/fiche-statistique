# -*- coding: utf-8 -*-
"""
HOTEL LE PRESTIGE - MARADI
VERSION FINALE : Statistiques basées sur le CUMUL DES NUITS PAR CLIENT.
"""

import os
import io
import hmac
import calendar
import logging
import unicodedata
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, make_response, abort, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from sqlalchemy.exc import OperationalError
from fpdf import FPDF
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# ===== CONFIGURATION ========================================
# ============================================================

NB_CHAMBRES = int(os.environ.get("NB_CHAMBRES", "9"))
PRIX_NUITEE = int(os.environ.get("PRIX_NUITEE", "17500"))

MOIS_NOMS = ["", "Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin", 
             "Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre"]

def _exiger_env(cle):
    valeur = os.environ.get(cle)
    if not valeur:
        raise RuntimeError(f"Variable d'environnement manquante : {cle}")
    return valeur

app = Flask(__name__)
app.secret_key = _exiger_env("SECRET_KEY")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///hotel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300}

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
logging.basicConfig(level=logging.INFO)

cloudinary.config(
    cloud_name=os.environ.get("CLOUD_NAME"),
    api_key=os.environ.get("CLOUD_API_KEY"),
    api_secret=os.environ.get("CLOUD_API_SECRET"),
    secure=True,
)

ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

# ============================================================
# ===== MODELE ===============================================
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
    date_arrivee = db.Column(db.Date)
    date_depart = db.Column(db.Date)
    pdf_url = db.Column(db.String(255))
    cloudinary_id = db.Column(db.String(150))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

CHAMPS_AUTORISES = (
    "nom", "prenom", "nationalite", "date_naissance", "lieu_naissance",
    "situation_familiale", "profession", "telephone", "domicile_habituel",
    "provenance", "destination", "mode_transport", "immatriculation",
    "type_piece", "num_piece", "date_delivrance", "lieu_delivrance",
    "chambre_num",
)

# ============================================================
# ===== HELPERS ET CLASSIFICATION ============================
# ============================================================

def format_date_fr(date_str):
    if not date_str: return "Non renseigne"
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        return dt.strftime('%d/%m/%Y')
    except: return str(date_str)

def latin1(texte):
    return str(texte if texte else "").encode("latin-1", errors="replace").decode("latin-1")

def verifier_mot_de_passe(saisi):
    if not saisi: return False
    if ADMIN_PASSWORD_HASH: return check_password_hash(ADMIN_PASSWORD_HASH, saisi)
    if ADMIN_PASSWORD: return hmac.compare_digest(saisi, ADMIN_PASSWORD)
    return False

def utilisateur_connecte():
    return session.get('logged_in') is True

def _nettoyer_cloudinary(public_id):
    if public_id:
        try: cloudinary.uploader.destroy(public_id, resource_type="raw")
        except: pass

# --- CLASSIFICATION NATIONALE ÉTENDUE ---
PAYS_AFRIQUE_OUEST = {"BENIN", "BENINOISE", "BURKINA", "BURKINABAISE", "BURKINABE", "COTE D'IVOIRE", "IVOIRIENNE", "GAMBIE", "GAMBIENNE", "GHANA", "GHANEENNE", "GUINEE", "GUINEENNE", "LIBERIA", "LIBERIENNE", "MALI", "MALIENNE", "MAURITANIE", "MAURITANIENNE", "NIGERIA", "NIGERIANE", "SENEGAL", "SENEGALAISE", "TOGO", "TOGOLAISE"}
PAYS_AUTRES_AFRIQUE = {"CAMEROUN", "CAMEROUNAISE", "TCHAD", "TCHADIENNE", "MAROC", "MAROCAINE", "ALGERIE", "ALGERIENNE", "TUNISIE", "TUNISIENNE", "EGYPTE", "EGYPTIENNE", "GABON", "GABONAISE", "CONGO", "CONGOLAISE"}
PAYS_ASIE = {"CHINE", "CHINOISE", "INDE", "INDIENNE", "JAPON", "JAPONAISE", "LIBAN", "LIBANAISE", "TURQUIE", "TURQUE"}
PAYS_EUROPE = {"FRANCE", "FRANCAISE", "BELGIQUE", "BELGE", "ALLEMAGNE", "ALLEMANDE", "ITALIE", "ITALIENNE", "ESPAGNE", "ESPAGNOLE", "ROYAUME-UNI", "BRITANNIQUE"}
PAYS_AMERIQUE = {"USA", "AMERICAINE", "ETATS-UNIS", "CANADA", "CANADIENNE", "BRESIL", "BRESILIENNE"}

def classer_nationalite(nat):
    if not nat: return "AUTRES PAYS"
    n = "".join(c for c in unicodedata.normalize("NFKD", str(nat)) if not unicodedata.combining(c)).upper().strip()
    if n in {"NIGER", "NIGERIEN", "NIGERIENNE"}: return "NATIONAUX (NIGER)"
    if any(p in n for p in PAYS_AFRIQUE_OUEST): return "AFRIQUE DE L'OUEST"
    if any(p in n for p in PAYS_AUTRES_AFRIQUE): return "AUTRES PAYS D'AFRIQUE"
    if any(p in n for p in PAYS_ASIE): return "ASIE"
    if any(p in n for p in PAYS_EUROPE): return "EUROPE"
    if any(p in n for p in PAYS_AMERIQUE): return "AMERIQUE"
    return "AUTRES PAYS"

# ============================================================
# ===== CALCUL DES STATISTIQUES (NUITÉES PAR CLIENT) =========
# ============================================================

def calculer_stats_logique(mois, annee):
    debut_mois = datetime(annee, mois, 1).date()
    _, nb_jours = calendar.monthrange(annee, mois)
    fin_mois = datetime(annee, mois, nb_jours).date()
    
    fiches = FicheClient.query.filter(FicheClient.date_arrivee <= fin_mois, FicheClient.date_depart >= debut_mois).all()
    
    c_debut, c_fin = 0, 0
    total_nuitees_cumulees = 0 # SOMME DE TOUTES LES NUITS DE CHAQUE CLIENT
    stats_p = {"NATIONAUX (NIGER)": 0, "AFRIQUE DE L'OUEST": 0, "AUTRES PAYS D'AFRIQUE": 0, "ASIE": 0, "EUROPE": 0, "AMERIQUE": 0, "AUTRES PAYS": 0}

    for f in fiches:
        if not f.date_arrivee or not f.date_depart: continue
        
        # Décompte clients début/fin de mois
        if f.date_arrivee <= debut_mois + timedelta(days=19): c_debut += 1
        if f.date_depart >= debut_mois + timedelta(days=21): c_fin += 1
        
        # Calcul des nuitées réelles de CE client dans CE mois
        d_eff = max(f.date_arrivee, debut_mois)
        f_eff = min(f.date_depart, fin_mois + timedelta(days=1))
        nb_nuits = (f_eff - d_eff).days
        if nb_nuits > 0:
            total_nuitees_cumulees += nb_nuits
        
        # Classement
        cat = classer_nationalite(f.nationalite)
        stats_p[cat] = stats_p.get(cat, 0) + 1

    # Taux d'occupation (basé sur la capacité totale de l'hôtel)
    capacite_totale = NB_CHAMBRES * nb_jours
    taux = (total_nuitees_cumulees * 100) / capacite_totale if capacite_totale > 0 else 0
    
    return {
        "mois_nom": MOIS_NOMS[mois], "mois_num": mois, "annee": annee,
        "clients_debut": c_debut, "clients_fin": c_fin,
        "total_nuitees": total_nuitees_cumulees, # Voici le chiffre que vous vouliez
        "taux_occupation": round(taux, 2), 
        "chiffre_affaires": total_nuitees_cumulees * PRIX_NUITEE,
        "nationalites": stats_p, 
        "chambres_offertes": NB_CHAMBRES, 
        "chambres_occupees": NB_CHAMBRES,
        "nb_jours": nb_jours
    }

# ============================================================
# ===== GÉNÉRATION PDF : 2 VOLETS (POLICE & GÉRANT) ==========
# ============================================================

def _generer_pdf_fiche(data, nom_client, nom_gerant):
    pdf = FPDF('P', 'mm', 'A4'); pdf.add_page()
    contenu = [
        ("Nom", nom_client), ("Prenom", data.get('prenom')),
        ("Nationalite", data.get('nationalite')), ("Date Naiss.", format_date_fr(data.get('date_naissance'))),
        ("Lieu Naiss.", data.get('lieu_naissance')), ("Situation", data.get('situation_familiale')),
        ("Profession", data.get('profession')), ("Telephone", data.get('telephone')),
        ("Domicile", data.get('domicile_habituel')), ("Provenance", data.get('provenance')),
        ("Destination", data.get('destination')), ("Transport", data.get('mode_transport')),
        ("Immat.", data.get('immatriculation')), ("Type Piece", data.get('type_piece')),
        ("Num Piece", data.get('num_piece')), ("Delivre le", format_date_fr(data.get('date_delivrance'))),
        ("Lieu Deliv.", data.get('lieu_delivrance')), ("Chambre No", data.get('chambre_num')),
        ("Arrivee", format_date_fr(data.get('date_arrivee'))), ("Depart", format_date_fr(data.get('date_depart'))),
    ]

    def dessiner_la_fiche(x_start):
        pdf.set_draw_color(0); pdf.rect(x_start, 8, 96, 280)
        pdf.set_xy(x_start, 12); pdf.set_font("Helvetica", 'B', 13)
        pdf.cell(96, 7, latin1("HOTEL LE PRESTIGE MARADI"), 0, 1, 'C')
        pdf.set_x(x_start); pdf.set_font("Helvetica", 'B', 11)
        pdf.cell(96, 7, latin1("FICHE DE RENSEIGNEMENT"), 0, 1, 'C')
        y = 36
        for label, val in contenu:
            pdf.set_xy(x_start + 3, y); pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(35, 9.5, latin1(f"{label} :"), 0)
            pdf.set_font("Helvetica", '', 10); pdf.cell(55, 9.5, latin1(str(val if val else ""))[:28], 0)
            y += 9.5
        y_sig = y + 8
        pdf.set_xy(x_start + 3, y_sig); pdf.set_font("Helvetica", 'BI', 10)
        pdf.cell(45, 5, latin1("Le Gerant"), 0); pdf.cell(45, 5, latin1("Le Client"), 0, 1, 'R')
        pdf.set_xy(x_start + 3, y_sig + 6); pdf.set_font("Helvetica", 'B', 10); pdf.cell(45, 5, latin1(nom_gerant), 0)
        pdf.set_x(x_start + 55); pdf.cell(38, 5, latin1(".........................."), 0, 1, 'R')

    dessiner_la_fiche(4); dessiner_la_fiche(108)
    pdf.set_draw_color(180); pdf.dashed_line(105, 5, 105, 292, 1, 1)
    return pdf

def pdf_response(pdf, nom_fichier):
    output = pdf.output(dest='S')
    pdf_bytes = output.encode('latin-1') if isinstance(output, str) else output
    resp = make_response(bytes(pdf_bytes))
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'inline; filename="{nom_fichier}"'
    return resp

# ============================================================
# ===== ROUTES ===============================================
# ============================================================

@app.route('/')
def accueil(): return render_template('accueil.html')

@app.route('/gerant', methods=['GET', 'POST'])
def gerant():
    if request.method == 'POST':
        if verifier_mot_de_passe(request.form.get('mot_de_passe')):
            session.clear(); session['logged_in'] = True
            session['nom_gerant'] = request.form.get('nom', ''); session['prenom_gerant'] = request.form.get('prenom', '')
            return redirect(url_for('dashboard'))
        return render_template('login.html', erreur="Identifiants incorrects.")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not utilisateur_connecte(): return redirect(url_for('gerant'))
    return render_template('dashboard.html')

@app.route('/fiche', methods=['GET', 'POST'])
def fiche():
    if not utilisateur_connecte(): return redirect(url_for('gerant'))
    if request.method != 'POST': return render_template('fiche.html')
    try:
        data = request.form.to_dict()
        d_arr = datetime.strptime(data.get('date_arrivee', ''), '%Y-%m-%d').date()
        d_dep = datetime.strptime(data.get('date_depart', ''), '%Y-%m-%d').date()
        nom_c = data.get('nom', '').strip().upper()
        nom_g = f"{session.get('nom_gerant', '')} {session.get('prenom_gerant', '')}".strip()
        
        pdf = _generer_pdf_fiche(data, nom_c, nom_g)
        pdf_b = bytes(pdf.output(dest='S').encode('latin-1')) if isinstance(pdf.output(dest='S'), str) else bytes(pdf.output(dest='S'))
        res = cloudinary.uploader.upload(io.BytesIO(pdf_b), resource_type="raw", public_id=f"f_{nom_c}_{datetime.utcnow().timestamp()}.pdf")
        
        f = FicheClient(**{k: data.get(k) for k in CHAMPS_AUTORISES})
        f.nom, f.date_arrivee, f.date_depart, f.pdf_url, f.cloudinary_id = nom_c, d_arr, d_dep, res['secure_url'], res['public_id']
        
        try:
            db.session.add(f); db.session.commit()
        except OperationalError:
            db.session.rollback(); db.engine.dispose()
            db.session.add(f); db.session.commit()

        flash(f"Succès : {nom_c} enregistré.", "success")
        return redirect(url_for('dashboard'))
    except Exception as e:
        db.session.rollback(); return render_template('fiche.html', erreur=f"Erreur DB ou SSL.")

@app.route('/stats')
def stats():
    if not utilisateur_connecte(): return redirect(url_for('gerant'))
    now = datetime.now()
    m = int(request.args.get('mois', now.month)); a = int(request.args.get('annee', now.year))
    return render_template("stats.html", stats=calculer_stats_logique(m, a), calendar=calendar)

@app.route('/imprimer_rapport/<int:mois>/<int:annee>')
def imprimer_rapport(mois, annee):
    if not utilisateur_connecte(): return redirect(url_for('gerant'))
    s = calculer_stats_logique(mois, annee)
    pdf = FPDF('P', 'mm', 'A4'); pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16); pdf.cell(0, 15, latin1("RAPPORT MENSUEL - HOTEL LE PRESTIGE"), 0, 1, 'C')
    pdf.cell(0, 10, latin1(f"Mois : {s['mois_nom']} {annee}"), 0, 1, 'C')
    pdf.ln(10)
    pdf.cell(100, 10, latin1("Total Nuitées (Somme clients) :"), 1); pdf.cell(40, 10, str(s['total_nuitees']), 1, 1)
    pdf.cell(100, 10, latin1("Chiffre d'Affaires :"), 1); pdf.cell(40, 10, f"{s['chiffre_affaires']} FCFA", 1, 1)
    return pdf_response(pdf, f"Rapport_{mois}_{annee}.pdf")

@app.route('/pdfs')
def pdfs():
    if not utilisateur_connecte(): return redirect(url_for('gerant'))
    clients = FicheClient.query.order_by(FicheClient.date_creation.desc()).all()
    return render_template('pdfs.html', clients=clients)

@app.route('/supprimer_pdf/<int:id>', methods=['POST'])
def supprimer_pdf(id):
    if not utilisateur_connecte(): return redirect(url_for('gerant'))
    f = FicheClient.query.get_or_404(id); _nettoyer_cloudinary(f.cloudinary_id)
    db.session.delete(f); db.session.commit(); return redirect(url_for('pdfs'))

@app.route('/deconnexion', methods=['POST'])
def deconnexion(): session.clear(); return redirect(url_for('accueil'))

if __name__ == "__main__":
    with app.app_context(): db.create_all()
    app.run(debug=True)