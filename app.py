from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import spacy
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"

# ============================
# DATABASE CONFIGURATION
# ============================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smarthire.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ============================
# NLP MODEL SETUP
# ============================
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Automatically download the model if not found
    from spacy.cli import download
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# ============================
# DATABASE MODELS
# ============================
class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="Pending")

# ============================
# ROUTES
# ============================
@app.route('/')
def home():
    jobs = Job.query.filter_by(status="Approved").all()
    return render_template('index.html', jobs=jobs)

@app.route('/employer', methods=['GET', 'POST'])
def employer():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        job = Job(title=title, description=description)
        db.session.add(job)
        db.session.commit()
        flash("Job submitted for approval!", "info")
        return redirect(url_for('employer'))
    return render_template('employer.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        job_id = request.form['job_id']
        action = request.form['action']
        job = Job.query.get(job_id)
        if job:
            job.status = "Approved" if action == "approve" else "Rejected"
            db.session.commit()
            flash(f"Job {action}d successfully!", "success")
    jobs = Job.query.all()
    return render_template('admin.html', jobs=jobs)

# ============================
# START APPLICATION
# ============================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=10000)
