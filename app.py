from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
import locale
import calendar
from datetime import datetime, timedelta
from fpdf import FPDF
import cloudinary
import cloudinary.uploader
from sqlalchemy import extract, or_
from dotenv import load_dotenv

# ================= CONFIGURATION =================
try:
    locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
except:
    try:
        locale.setlocale(locale.LC_TIME, "fra_FRA")
    except:
        pass 

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hotel_prestige_2026_key")

# Configuration de la Base de Données
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuration Cloudinary
cloudinary.config(
    cloud_name=os.environ.get("CLOUD_NAME"),
    api_key=os.environ.get("CLOUD_API_KEY"),
    api_secret=os.environ.get("CLOUD_API_SECRET"),
    secure=True
)

# ================= MODÈLE DE DONNÉES =================
class FicheClient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100))
    nationalite = db.Column(db.String(50))
    provenance = db.Column(db.String(100))
    date_arrivee = db.Column(db.Date)
    date_depart = db.Column(db.Date)
    pdf_url = db.Column(db.String(255))
    cloudinary_id = db.Column(db.String(150))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def format_date_fr(date_str):
    if not date_str: return "Non renseigné"
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%d/%m/%Y')
    except:
        return date_str

# ================= ROUTES =================

@app.route('/')
def accueil(): 
    return render_template('accueil.html')

@app.route('/gerant', methods=['GET', 'POST'])
def gerant():
    if request.method == 'POST':
        if request.form.get('mot_de_passe') == os.environ.get("ADMIN_PASSWORD"):
            session['logged_in'] = True
            session['nom_gerant'] = request.form.get('nom')
            session['prenom_gerant'] = request.form.get('prenom')
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    return render_template('dashboard.html')

@app.route('/fiche', methods=['GET', 'POST'])
def fiche():
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    if request.method == 'POST':
        data = request.form.to_dict()
        champs_requis = ['nom', 'prenom', 'date_arrivee', 'date_depart', 'nationalite']
        for c in champs_requis:
            if not data.get(c):
                return render_template('fiche.html', erreur=f"Le champ {c} est obligatoire.")

        nom_client = data.get('nom', '').upper()
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "HOTEL LE PRESTIGE MARADI", ln=True, align='L')
        pdf.ln(5)
        pdf.set_font("Arial", '', 11)
        
        infos = [
            f"Nom : {nom_client}", 
            f"Prenom : {data.get('prenom')}",
            f"Provenance : {data.get('provenance', 'N/A')}",
            f"Arrivee : {format_date_fr(data.get('date_arrivee'))}", 
            f"Depart : {format_date_fr(data.get('date_depart'))}"
        ]
        for info in infos:
            pdf.cell(0, 8, info.encode('latin-1', 'replace').decode('latin-1'), ln=True)

        temp_pdf = f"temp_{secure_filename(nom_client)}.pdf"
        pdf.output(temp_pdf)
        upload_res = cloudinary.uploader.upload(temp_pdf, resource_type="raw")
        os.remove(temp_pdf)

        d_arr = datetime.strptime(data.get('date_arrivee'), '%Y-%m-%d').date()
        d_dep = datetime.strptime(data.get('date_depart'), '%Y-%m-%d').date()

        nouvelle_fiche = FicheClient(
            nom=nom_client, prenom=data.get('prenom'), nationalite=data.get('nationalite'),
            provenance=data.get('provenance'), date_arrivee=d_arr, date_depart=d_dep,
            pdf_url=upload_res['secure_url'], cloudinary_id=upload_res['public_id']
        )
        db.session.add(nouvelle_fiche)
        db.session.commit()
        return render_template('fiche.html', success=True)
    return render_template('fiche.html')

@app.route('/stats')
def stats():
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    
    now = datetime.now()
    mois = int(request.args.get('mois', now.month))
    annee = int(request.args.get('annee', now.year))
    
    debut_mois = datetime(annee, mois, 1).date()
    _, nb_jours = calendar.monthrange(annee, mois)
    fin_mois = datetime(annee, mois, nb_jours).date()
    limite_comptable = fin_mois + timedelta(days=1)

    fiches = FicheClient.query.filter(
        FicheClient.date_arrivee <= fin_mois, 
        FicheClient.date_depart >= debut_mois
    ).all()
    
    total_nuitees = 0
    clients_debut = 0
    clients_fin = 0
    nationalites = {}
    
    date_20 = datetime(annee, mois, min(20, nb_jours)).date()
    date_21 = datetime(annee, mois, min(21, nb_jours)).date()
    
    for f in fiches:
        d_eff = max(f.date_arrivee, debut_mois)
        f_eff = min(f.date_depart, limite_comptable)
        n_nuits = (f_eff - d_eff).days
        total_nuitees += max(n_nuits, 0)
        
        if f.date_arrivee <= date_20 and f.date_depart >= debut_mois:
            clients_debut += 1
        if f.date_depart >= date_21 and f.date_arrivee <= fin_mois:
            clients_fin += 1
        
        if f.nationalite:
            nationalites[f.nationalite] = nationalites.get(f.nationalite, 0) + 1

    months_fr = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    
    stats_data = {
        "total_nuitees": total_nuitees,
        "chambres_occupees": 9,
        "clients_debut": clients_debut,
        "clients_fin": clients_fin,
        "chiffre_affaires": total_nuitees * 17500,
        "taux_occupation": round((total_nuitees * 100) / (9 * nb_jours), 2) if nb_jours else 0,
        "nationalites": nationalites,
        "mois_num": mois,
        "mois_nom": months_fr[mois],
        "annee": annee
    }
    
    return render_template("stats.html", stats=stats_data, datetime_now=now.strftime("%d/%m/%Y %H:%M"), calendar=calendar)

@app.route('/pdfs')
def pdfs():
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    clients = FicheClient.query.order_by(FicheClient.date_creation.desc()).all()
    return render_template('pdfs.html', clients=clients)

@app.route('/supprimer_pdf/<int:id>')
def supprimer_pdf(id):
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    fiche = FicheClient.query.get_or_404(id)
    if fiche.cloudinary_id:
        try: cloudinary.uploader.destroy(fiche.cloudinary_id, resource_type="raw")
        except: pass
    db.session.delete(fiche)
    db.session.commit()
    return redirect(url_for('pdfs'))

if __name__ == "__main__":
    app.run(debug=True)