from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from PyPDF2 import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import spacy
import os

# ============================
# 🔧 Flask App Configuration
# ============================
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# ✅ DATABASE CONFIGURATION
# For local MySQL (use your own password)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:your_password@localhost/smarthire'
# For Render deployment, use DATABASE_URL if provided
if os.environ.get("DATABASE_URL"):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL").replace("postgres://", "postgresql://")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ============================
# 🧩 NLP MODEL LOADING
# ============================
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    from spacy.cli import download
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# ============================
# 🧱 DATABASE MODELS
# ============================
class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pending')
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

class Applicant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    resume_text = db.Column(db.Text)
    matched_score = db.Column(db.Float)

# ============================
# 🌐 ROUTES
# ============================

@app.route('/')
def home():
    jobs = Job.query.filter_by(status='Approved').all()
    return render_template('home.html', jobs=jobs)

# Employer: Submit job for approval
@app.route('/employer', methods=['GET', 'POST'])
def employer():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        job = Job(title=title, description=description)
        db.session.add(job)
        db.session.commit()
        flash('Job submitted for admin approval!', 'success')
        return redirect(url_for('employer'))
    return render_template('employer.html')

# Admin: Approve/Reject job posts
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    jobs = Job.query.all()
    if request.method == 'POST':
        job_id = request.form.get('job_id')
        action = request.form.get('action')
        job = Job.query.get(job_id)
        if job:
            job.status = 'Approved' if action == 'approve' else 'Rejected'
            db.session.commit()
            flash(f'Job {action}d successfully!', 'info')
        return redirect(url_for('admin'))
    return render_template('admin.html', jobs=jobs)

# Applicant: Apply to job with PDF resume
@app.route('/apply', methods=['GET', 'POST'])
def apply():
    jobs = Job.query.filter_by(status='Approved').all()
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        file = request.files['resume']
        job_id = request.form['job_id']

        # ✅ Extract text from PDF
        reader = PdfReader(file)
        resume_text = "".join([page.extract_text() for page in reader.pages])

        # ✅ Calculate similarity score
        job = Job.query.get(job_id)
        if job:
            vectorizer = TfidfVectorizer()
            tfidf = vectorizer.fit_transform([resume_text, job.description])
            score = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0] * 100
        else:
            score = 0

        applicant = Applicant(name=name, email=email, resume_text=resume_text, matched_score=score)
        db.session.add(applicant)
        db.session.commit()
        flash(f'Application submitted! Match Score: {round(score, 2)}%', 'success')
        return redirect(url_for('apply'))
    return render_template('apply.html', jobs=jobs)

# ============================
# 🚀 DEPLOYMENT ENTRY POINT
# ============================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))  # Render uses dynamic port
    app.run(host='0.0.0.0', port=port, debug=False)
