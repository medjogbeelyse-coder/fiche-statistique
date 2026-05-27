from flask import Flask, render_template, request, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
import calendar
from datetime import datetime, timedelta
from fpdf import FPDF
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hotel_prestige_2026_key")

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///hotel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

cloudinary.config(
    cloud_name=os.environ.get("CLOUD_NAME"),
    api_key=os.environ.get("CLOUD_API_KEY"),
    api_secret=os.environ.get("CLOUD_API_SECRET"),
    secure=True
)

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

def format_date_fr(date_str):
    if not date_str: return "Non renseigné"
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        return dt.strftime('%d/%m/%Y')
    except: return str(date_str)

def calculer_stats_logique(mois, annee):
    debut_mois = datetime(annee, mois, 1).date()
    _, nb_jours = calendar.monthrange(annee, mois)
    fin_mois = datetime(annee, mois, nb_jours).date()
    seuil_20 = datetime(annee, mois, 20).date()
    seuil_21 = datetime(annee, mois, 21).date()

    fiches = FicheClient.query.filter(FicheClient.date_arrivee <= fin_mois, FicheClient.date_depart >= debut_mois).all()

    clients_debut = 0
    clients_fin = 0
    total_nuitees = 0
    stats_pays = {}

    for f in fiches:
        if f.date_arrivee <= seuil_20 and f.date_depart >= debut_mois:
            clients_debut += 1
        if f.date_depart >= seuil_21 and f.date_arrivee <= fin_mois:
            clients_fin += 1
        
        d_eff = max(f.date_arrivee, debut_mois)
        f_eff = min(f.date_depart, fin_mois + timedelta(days=1))
        total_nuitees += max((f_eff - d_eff).days, 0)
        
        pays = (f.nationalite or "NIGERIENNE").upper()
        stats_pays[pays] = stats_pays.get(pays, 0) + 1

    taux_occ = (total_nuitees * 100) / (9 * nb_jours) if nb_jours > 0 else 0
    
    return {
        "mois_num": mois, "annee": annee, "nb_jours": nb_jours,
        "clients_debut": clients_debut, "clients_fin": clients_fin,
        "total_nuitees": total_nuitees, "taux_occupation": round(taux_occ, 2),
        "chambres_occupees": 9,
        "chiffre_affaires": total_nuitees * 17500, "nationalites": stats_pays,
        "mois_nom": ["","Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"][mois]
    }

@app.route('/')
def accueil(): return render_template('accueil.html')

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
        nom_client = data.get('nom', '').upper()
        nom_gerant = f"{session.get('nom_gerant','')} {session.get('prenom_gerant','')}"
        pdf = FPDF('P', 'mm', 'A4')
        pdf.add_page()
        
        contenu = [
            ("Nom", nom_client), ("Prenom", data.get('prenom')),
            ("Nationalite", data.get('nationalite')), ("Né le", format_date_fr(data.get('date_naissance'))),
            ("Lieu Naiss.", data.get('lieu_naissance')), ("Situation", data.get('situation_familiale')),
            ("Profession", data.get('profession')), ("Telephone", data.get('telephone')),
            ("Domicile", data.get('domicile_habituel')), ("Provenance", data.get('provenance')),
            ("Destination", data.get('destination')), ("Transport", data.get('mode_transport')),
            ("Immat.", data.get('immatriculation')), ("Piece", data.get('type_piece')),
            ("N° Piece", data.get('num_piece')), ("Délivré le", format_date_fr(data.get('date_delivrance'))),
            ("Lieu Déliv.", data.get('lieu_delivrance')), ("Chambre", data.get('chambre_num')),
            ("Arrivee", format_date_fr(data.get('date_arrivee'))), ("Depart", format_date_fr(data.get('date_depart')))
        ]

        def dessiner_la_fiche(x_start):
            pdf.set_draw_color(0); pdf.rect(x_start, 8, 96, 275)
            pdf.set_xy(x_start, 12); pdf.set_font("Arial", 'B', 13)
            pdf.cell(96, 7, "HOTEL LE PRESTIGE MARADI", 0, 1, 'C')
            pdf.set_x(x_start); pdf.set_font("Arial", 'B', 12)
            pdf.cell(96, 7, "FICHE DE RENSEIGNEMENT", 0, 1, 'C')
            pdf.set_x(x_start); pdf.set_font("Arial", '', 8)
            pdf.cell(96, 4, "Contact : 96970571 / 94250556", 0, 1, 'C')
            y = 34
            for label, val in contenu:
                pdf.set_xy(x_start + 3, y); pdf.set_font("Arial", 'B', 12)
                pdf.cell(35, 8.8, f"{label} :", 0)
                pdf.set_font("Arial", '', 12)
                pdf.cell(55, 8.8, str(val)[:28], 0)
                y += 8.8
            pdf.set_xy(x_start + 3, y + 10); pdf.set_font("Arial", 'I', 11)
            pdf.cell(40, 5, "Le Gérant", 0); pdf.cell(48, 5, "Le Client", 0, 1, 'R')
            pdf.set_x(x_start + 3); pdf.set_font("Arial", 'B', 11)
            pdf.cell(90, 5, f"{nom_gerant}", 0, 1)

        dessiner_la_fiche(4); dessiner_la_fiche(108)
        pdf.set_draw_color(180); pdf.dashed_line(105, 5, 105, 290, 1, 1)
        
        temp_pdf = f"temp_{secure_filename(nom_client)}.pdf"
        pdf.output(temp_pdf)
        res = cloudinary.uploader.upload(temp_pdf, resource_type="raw")
        os.remove(temp_pdf)

        fiche = FicheClient(**{k: data.get(k) for k in data if k in FicheClient.__table__.columns})
        fiche.nom = nom_client
        fiche.date_arrivee = datetime.strptime(data.get('date_arrivee'), '%Y-%m-%d').date()
        fiche.date_depart = datetime.strptime(data.get('date_depart'), '%Y-%m-%d').date()
        fiche.pdf_url = res['secure_url']; fiche.cloudinary_id = res['public_id']
        db.session.add(fiche); db.session.commit()
        return render_template('fiche.html', success=True)
    return render_template('fiche.html')

@app.route('/stats')
def stats():
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    mois = int(request.args.get('mois', datetime.now().month))
    annee = int(request.args.get('annee', datetime.now().year))
    return render_template("stats.html", stats=calculer_stats_logique(mois, annee), calendar=calendar)

@app.route('/imprimer_rapport/<int:mois>/<int:annee>')
def imprimer_rapport(mois, annee):
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    s = calculer_stats_logique(mois, annee)
    pdf = FPDF('P', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 15, "HOTEL LE PRESTIGE - MARADI", 0, 1, 'C')
    pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, f"RAPPORT MENSUEL : {s['mois_nom'].upper()} {s['annee']}", 0, 1, 'C')
    pdf.ln(10)
    
    def section(titre, lignes):
        pdf.set_fill_color(230); pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f" {titre}", 1, 1, 'L', True); pdf.set_font("Arial", '', 11)
        for l, v in lignes:
            pdf.cell(110, 10, f" {l}", 1); pdf.cell(80, 10, f" {v}", 1, 1)
        pdf.ln(5)

    section("1. RESSOURCES HUMAINES & CAPACITE", [("Chambres Offertes", "09"), ("Chambres Occupées", "09")])
    section("2. FREQUENTATION & EXPLOITATION", [
        ("Clients (01 au 20)", s['clients_debut']), ("Clients (21 au fin)", s['clients_fin']),
        ("Total Nuitées", s['total_nuitees']), ("Chiffre d'Affaires", f"{s['chiffre_affaires']} FCFA"),
        ("Taux d'Occupation", f"{s['taux_occupation']} %")
    ])
    
    pdf.set_fill_color(230); pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, " 3. NATIONALITES", 1, 1, 'L', True)
    for p, c in s['nationalites'].items():
        pdf.cell(110, 10, f" {p}", 1); pdf.cell(80, 10, f" {c}", 1, 1)

    pdf.set_y(-20); pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 10, f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 0, 'C')
    
    resp = make_response(pdf.output(dest='S'))
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=Rapport_{s["mois_nom"]}.pdf'
    return resp

@app.route('/pdfs')
def pdfs():
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    return render_template('pdfs.html', clients=FicheClient.query.order_by(FicheClient.date_creation.desc()).all())

@app.route('/supprimer_pdf/<int:id>')
def supprimer_pdf(id):
    if not session.get('logged_in'): return redirect(url_for('gerant'))
    f = FicheClient.query.get_or_404(id)
    if f.cloudinary_id: cloudinary.uploader.destroy(f.cloudinary_id, resource_type="raw")
    db.session.delete(f); db.session.commit()
    return redirect(url_for('pdfs'))

if __name__ == "__main__":
    with app.app_context(): db.create_all()
    app.run(debug=True)