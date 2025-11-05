import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from PyPDF2 import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ============================
# 🔧 Flask App Configuration
# ============================
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# ✅ DATABASE CONFIGURATION
# Local MySQL (adjust password as needed)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:your_password@localhost/smarthire'

# Render deployment: use DATABASE_URL if available
if os.environ.get("DATABASE_URL"):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL").replace("postgres://", "postgresql://")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ============================
# 🧱 DATABASE MODELS
# DEPLOYMENT_ATTEMPT_1105
class Job(db.Model):
if result and result.password:
    # Safely convert the password to a string and URL-encode it
    encoded_password = quote_plus(str(result.password))
else:
    # Handle the critical case where the password data is missing (H10 crash cause)
    # This prints a clear message to the Heroku logs and forces the app to quit.
    print("\n\n!! CRITICAL STARTUP ERROR !!")
    print("Failed to fetch required database password. 'result' or 'result.password' is None.")
    print("Action Required: Check your database migrations, seeds, or environment variables.")
    print("!! ----------------------- !!\n")
    import sys
    sys.exit(1)
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

        # ✅ Calculate similarity score using TF-IDF
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
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
    # Deployment Marker 1106
