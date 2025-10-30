from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session # <-- Ensure 'session' is imported!
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import re
from PyPDF2 import PdfReader
import string
from sqlalchemy import func
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ✅ NLP/ML imports
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
app.secret_key = "secret123"

# ✅ Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/smarthire'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------- DATABASE MODELS --------------------
class User(db.Model):
    __tablename__ = 'User'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)

def is_hashed(password):
    # Detect if the password is already hashed (scrypt or pbkdf2)
    return password.startswith("scrypt:") or password.startswith("pbkdf2:")

def hash_plaintext_passwords():
    users = User.query.all()
    for user in users:
        if not is_hashed(user.password):
            user.password = generate_password_hash(user.password)
            print(f"Hashed password for user: {user.username}")
    db.session.commit()
    print("All plain-text passwords have been hashed successfully.")

# -----------------------------------------------------
class Job(db.Model):
    __tablename__ = 'Job'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(100), default="N/A")
    job_type = db.Column(db.String(50), default="Full-Time")
    salary = db.Column(db.String(50), default="Negotiable")
    status = db.Column(db.String(20), default='Pending')
    
    # 🌟 FIX: Consistent casing 'Employer.id' 
    employer_id = db.Column(db.Integer, db.ForeignKey('Employer.id'), nullable=False)
    employer = db.relationship('Employer', backref='jobs')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# --- Applicant Model (Removed incorrect Job linkage) ---
class Applicant(db.Model):
    __tablename__ = "applicant"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    target_job = db.Column(db.String(100), nullable=True)
    resume_filename = db.Column(db.String(255), nullable=True)
    skills = db.Column(db.String(255), nullable=True)
    experience = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f"<Applicant {self.fullname}>"

# --- Application Model (Essential for linking Applicant and Job, and fixing errors) ---
class Application(db.Model):
    __tablename__ = 'Application'
    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey('applicant.user_id'), nullable=False)
    
    # 🌟 FIX: Consistent casing 'Job.id'
    job_id = db.Column(db.Integer, db.ForeignKey('Job.id'), nullable=False)  
    job = db.relationship('Job', backref='applications')
    
    status = db.Column(db.String(50), default='Submitted')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Employer(db.Model):
    __tablename__ = 'employer' # Or 'Employer', match your database if it exists
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('User.id'), unique=True, nullable=False)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100), nullable=True) # Essential field for employers
    
    # Optional fields for completeness
    phone = db.Column(db.String(20), nullable=True)
    website = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f"<Employer {self.company}>"

class Resume(db.Model):
    __tablename__ = 'Resume' # Setting explicit name for consistency
    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey('applicant.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    owner_name = db.Column(db.String(150)) 
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    applicant = db.relationship('Applicant', backref='resumes')

class Screening(db.Model):
    __tablename__ = 'Screening' # Setting explicit name for consistency
    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey('Resume.id'), nullable=False) # 🌟 FIX: Changed from 'resume.id' to 'Resume.id' for consistency
    
    # 🌟 FIX: Consistent casing 'Job.id' (This fixes your current error)
    job_id = db.Column(db.Integer, db.ForeignKey('Job.id')) 
    
    applicant_name = db.Column(db.String(150))
    applicant_email = db.Column(db.String(150))
    applicant_phone = db.Column(db.String(50))
    job_description_text = db.Column(db.Text, nullable=False)
    matched_skills = db.Column(db.Text)
    match_score = db.Column(db.Float)
    screened_at = db.Column(db.DateTime, default=datetime.utcnow)
    resume = db.relationship('Resume', backref='screenings')
    job = db.relationship('Job', backref='screenings')

# -------------------- FILE FOLDERS --------------------
# Define the base directory of the current script (app.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# UPLOAD_FOLDER is now C:/xampp/htdocs/smarthire/myproject/static/uploads
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# SCREENING_FOLDER is C:/xampp/htdocs/smarthire/myproject/static/screenings
SCREENING_FOLDER = os.path.join(BASE_DIR, "static", "screenings")
os.makedirs(SCREENING_FOLDER, exist_ok=True)

# Update Flask configuration (if not already done later in the code)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# -------------------- SKILL KEYWORDS --------------------
# app.py: Replace the list with this (Expanded list)
SKILL_KEYWORDS = [
    # Programming Languages
    "python", "java", "c++", "c#", "javascript", "typescript", "php", "ruby", "go",
    # Frameworks/Libraries
    "flask", "django", "spring boot", "react", "angular", "vue", "node.js", "express",
    # Data/ML/AI
    "machine learning", "deep learning", "data analysis", "data science", "sql", 
    "nlp", "pandas", "numpy", "tensorflow", "pytorch", "scikit-learn", "keras",
    # Cloud/DevOps/Databases
    "aws", "azure", "google cloud", "docker", "kubernetes", "jenkins", "git", "mysql", 
    "postgresql", "mongodb", "terraform", "ci/cd",
    # Tools/Concepts
    "agile", "scrum", "project management", "rest api", "testing", "jira"
]

# -------------------- AUTH --------------------

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def do_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    user = User.query.filter(func.lower(User.username) == username.lower()).first()

    if user and user.password == password:
        session["user_id"] = user.id
        session["role"] = user.role
        print(f"✅ Logged in as: {user.username} (role={user.role})")

        if user.role == "admin":
            return redirect(url_for("admin_dashboard"))
        elif user.role == "applicant":
            return redirect(url_for("applicant_dashboard"))
        elif user.role == "employer":
            return redirect(url_for("employer_dashboard"))
        else:
            flash("Unknown user role. Contact admin.", "error")
            return redirect(url_for("login"))

    # If we reach here, login failed
    flash("❌ Invalid username or password", "error")
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"] 
        password = request.form["password"]
        user_role = request.form.get("role", "applicant")  # default 'applicant'

        # Check if username exists
        existing_user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if existing_user:
            flash("Username already exists!", "error")
            return redirect(url_for("signup"))

        try:
            # 1️⃣ Create User (plain-text password)
            new_user = User(
                username=username,
                password=password,
                role=user_role
            )

            db.session.add(new_user)
            db.session.flush()  # to get new_user.id

            # 2️⃣ Create profile
            if user_role == "applicant":
                new_profile = Applicant(
                    user_id=new_user.id,
                    fullname=username,
                    email=email,
                    skills="N/A",
                    experience="0 years"
                )

            elif user_role == "employer":
                new_profile = Employer(
                    user_id=new_user.id,
                    fullname=username,
                    email=email,
                    company="N/A"
                )

            else:
                db.session.rollback()
                flash("Invalid role selected.", "error")
                return redirect(url_for("signup"))

            db.session.add(new_profile)
            db.session.commit()
            flash("Sign up successful! You can now log in.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error during signup: {e}", "error")
            return redirect(url_for("signup"))
    return render_template("signup.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        flash(f"Password reset link sent to {email}", "success")
    return render_template("forgot_password.html")

# -------------------- LOGOUT ROUTE --------------------
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

# -------------------- DASHBOARDS --------------------
from flask import session # Make sure this is imported
@app.route("/dashboard/employer")
def employer_dashboard():
    if 'user_id' not in session or session.get('role') != 'employer':
        flash("Unauthorized access. Please log in as an employer.", "error")
        return redirect(url_for("login"))

    employer = Employer.query.filter_by(user_id=session['user_id']).first()
    if not employer:
        flash("Employer profile not found.", "error")
        return redirect(url_for("login"))

    # Fetches ALL jobs from the database for viewing
    jobs_list = Job.query.order_by(Job.created_at.desc()).all()

    resumes_list = Resume.query.all()
    screenings_list = Screening.query.order_by(Screening.screened_at.desc()).all()

    stats = {
        "uploaded_resumes": len(resumes_list),
        "screened_resumes": len(screenings_list),
        "job_posts": len(jobs_list)
    }

    return render_template(
        "employer_dashboard.html",
        employer=employer,
        jobs=jobs_list,
        resumes=resumes_list,
        screenings=screenings_list,
        stats=stats,
        shortlisted=[],
        interviews=[]
    )

@app.route('/dashboard')
@app.route('/applicant-dashboard')
def applicant_dashboard():
    applicant_user_id = session.get('user_id')
    if not applicant_user_id:
        flash("Please log in to view your dashboard.", "warning")
        return redirect(url_for('login'))

    # 1. Fetch Applicant Profile
    # Assuming Applicant model is linked by user_id
    applicant = Applicant.query.filter_by(user_id=applicant_user_id).first()
    if not applicant:
        flash("Profile not found. Please complete your profile.", "error")
        return redirect(url_for('edit_profile')) 
        
    # 2. Fetch Applications (History and Stats)
    applications = Application.query.filter_by(applicant_id=applicant.user_id).order_by(Application.created_at.desc()).all()
    
    # 3. Calculate Stats
    # Note: 'matches' logic requires the TFIDF/Cosine Similarity logic you've set up
    # For now, we'll fetch a simple list of jobs (replace this with your ML matching logic)
    jobs = Job.query.order_by(Job.created_at.desc()).limit(10).all() # Fetch latest 10 jobs as a default

    # Prepare data for template
    applied_job_ids = {app.job_id for app in applications}
    num_interviews = Application.query.filter_by(applicant_id=applicant.user_id, status='Interview').count()
    
    # Placeholder for a real ML match count
    # You would use your TFIDF/Cosine Similarity here
    num_matches = 0 
    
    # Calculate Profile Completion (simple logic for the progress bar)
    # 1 point for name, 1 for target job, 1 for skills, 1 for resume
    profile_score = 0
    if applicant.fullname: profile_score += 1
    if applicant.target_job: profile_score += 1
    if applicant.skills: profile_score += 1
    if applicant.resume_filename: profile_score += 1
    profile_percent = int((profile_score / 4) * 100) # Max 4 fields for 100%

    return render_template('applicant_dashboard.html',
        applicant=applicant,
        jobs=jobs, # Recommended jobs
        applications=applications, # Job history
        applied_job_ids=applied_job_ids,
        interviews=range(num_interviews), # Used for length in template stats
        matches=range(num_matches), # Used for length in template stats
        profile_percent=profile_percent # Pass the profile completion value
    )

# ... (rest of your app.py)
@app.route("/dashboard/admin")
def admin_dashboard():
    # Retrieve all records from the database
    applicants_list = Applicant.query.all()
    employers_list = Employer.query.all()
    
    # New: Fetch all resume objects
    all_resumes = Resume.query.all() 

    approved_jobs = Job.query.filter_by(status='approved').all()
    pending_jobs = Job.query.filter_by(status='pending').all()

    # Combine approved + pending for the dashboard detailed records table
    all_jobs = approved_jobs + pending_jobs

    # Calculate count for the Resume stat card
    resume_count = len(all_resumes) 

    # 🚨 CRITICAL DEBUGGING CHECK 🚨
    print("-" * 50)
    print(f"DEBUG: Applicants found: {len(applicants_list)}")
    print(f"DEBUG: Employers found: {len(employers_list)}")
    print(f"DEBUG: Jobs found: {len(all_jobs)}")
    print(f"DEBUG: Resume count: {resume_count}")
    print("-" * 50)

    # Pass all necessary lists to the template
    return render_template('admin_dashboard.html',
                           applicants_list=applicants_list,
                           employers_list=employers_list,
                           approved_jobs=approved_jobs,
                           pending_jobs=pending_jobs,
                           all_jobs=all_jobs,
                           resume_count=resume_count,
                           all_resumes=all_resumes) # <--- MUST BE PASSED HERE

# -------------------- RESUMES --------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded resumes from UPLOAD_FOLDER"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# app.py (New/Updated Code)

@app.route('/upload-resume', methods=['POST'])
def upload_resume():
    # ⚠️ Security Check
    if 'user_id' not in session or session.get('role') != 'applicant':
        flash("Please log in to update your profile.", "warning")
        return redirect(url_for('login'))
        
    applicant_user_id = session.get('user_id')

    # Fetch applicant profile
    applicant = Applicant.query.filter_by(user_id=applicant_user_id).first()
    if not applicant:
        flash("Applicant profile not found. Contact Admin.", "error")
        return redirect(url_for('applicant_dashboard'))

    # 1. Update Profile Fields (Full Name and Target Job Title)
    applicant.fullname = request.form.get('fullname')
    applicant.target_job = request.form.get('jobtitle')
    
    # 2. Handle File Upload (Resume PDF)
    if 'resume' in request.files:
        file = request.files['resume']
        
        if file.filename != '' and allowed_file(file.filename):
            
            # Create a unique filename: user_id_secure_filename.pdf
            base_filename = secure_filename(file.filename)
            filename = f"{applicant_user_id}_{base_filename}"
            
            # Ensure the upload directory exists
            upload_dir = app.config['UPLOAD_FOLDER']
            if not os.path.exists(upload_dir):
                 os.makedirs(upload_dir)

            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)
            
            # Update the database record with the new filename
            applicant.resume_filename = filename

        elif file.filename != '' and not allowed_file(file.filename):
            flash("🚫 Only PDF files are allowed for resume upload.", "error")
            # Continue to save text fields even if file fails
    
    # 3. Save all changes (profile fields and resume filename)
    try:
        db.session.commit()
        flash("✅ Profile and Resume updated successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"🚫 Error saving profile: {e}", "error")

    # The dashboard calculates the profile percentage based on these saved fields
    return redirect(url_for('applicant_dashboard'))

@app.route("/download_resume/<filename>")
def download_resume(filename):
    """Download uploaded resumes from UPLOAD_FOLDER"""
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        flash("Resume file not found.", "error")
        return redirect(url_for("employer_dashboard"))

# FIX: /delete_resume/<int:resume_id>
@app.route("/delete_resume/<int:resume_id>", methods=["POST"])
def delete_resume(resume_id):
    # ✅ NEW LOGIC: Fetch and delete the Resume object
    resume = Resume.query.get(resume_id)
    if resume:
        # Delete the file from the filesystem first
        filepath = os.path.join(UPLOAD_FOLDER, resume.filename)
        if os.path.exists(filepath):
            os.remove(filepath)            

        # Delete the record from the database
        owner_name = resume.owner_name
        db.session.delete(resume)
        db.session.commit()
      
        flash(f"{owner_name}'s resume deleted successfully.", "success")
    else:
        flash("Resume not found.", "error")
    return redirect(url_for("employer_dashboard"))

# -------------------- JOB ROUTES --------------------
@app.route("/jobs/add_page", methods=["GET"])
def add_job_page():
    if session.get("role") != "employer":
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))
    return render_template("add_job.html")

@app.route("/jobs/submit", methods=["POST"])
def submit_job():
    if session.get("role") != "employer":
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))
        
    employer_user_id = session.get("user_id")
    employer = Employer.query.filter_by(user_id=employer_user_id).first()
    
    if not employer:
        flash("Employer profile not found. Please complete your profile first.", "error")
        return redirect(url_for("employer_dashboard"))
        
    # Collect form data
    title = request.form.get("title")
    # 🎯 FIX: Retrieve the company name directly from the form data
    company_name = request.form.get("company") 
    location = request.form.get("location")
    job_type = request.form.get("job_type")
    salary = request.form.get("salary")
    description = request.form.get("description")

    # Validation: Ensure required fields are not empty
    if not title or not company_name or not description:
        flash("Title, Company, and Description are required fields.", "error")
        return redirect(url_for("add_job_page"))

    # Save job
    new_job = Job(
        title=title,
        # 🎯 FIX: Use the collected company_name variable
        company=company_name, 
        location=location,
        job_type=job_type,
        salary=salary,
        description=description,
        status="Pending",
        employer_id=employer.id
    )

    db.session.add(new_job)
    db.session.commit()
    flash(f"✅ Job '{title}' added successfully!", "success")
    return redirect(url_for("employer_dashboard"))

# FIX: /jobs/edit/<int:job_id>
@app.route("/jobs/edit/<int:job_id>", methods=["GET", "POST"])
def edit_job(job_id):
    # 1. Authentication Check (Recommended, if not done elsewhere)
    if session.get("role") != "employer":
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))

    # 2. Fetch the Job Object
    job = Job.query.get(job_id) 
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("employer_dashboard"))

    if request.method == "POST":
        # 3. Handle POST Request (Form Submission/Update)
        job.title = request.form.get("title")
        job.company = request.form.get("company")
        job.location = request.form.get("location")
        job.job_type = request.form.get("job_type")
        job.salary = request.form.get("salary")
        job.description = request.form.get("description")
        
        db.session.commit()
        
        flash(f"✅ Job '{job.title}' updated successfully!", "success")
        return redirect(url_for("employer_dashboard"))

    # 4. Handle GET Request (Display Form)
    # 🎯 FIX: Render the template and pass the 'job' object.
    return render_template("add_job.html", job=job)

@app.route("/jobs/delete/<int:job_id>", methods=["POST"])
def delete_job(job_id):
    # ✅ NEW LOGIC: Query and delete the Job object
    job = Job.query.get(job_id)
    if job:
        db.session.delete(job)
        db.session.commit() # Commit the deletion
        flash(f"Job {job_id} deleted successfully.", "success")
    else:
        flash(f"Job not found.", "error")
       
    return redirect(url_for("employer_dashboard"))

@app.route("/jobs/approve/<int:job_id>", methods=["POST"])
def approve_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.status = "Approved"
    db.session.commit()
    flash(f"✅ Job '{job.title}' approved successfully!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route('/archive_job/<int:job_id>', methods=['POST'])
def archive_job(job_id):
    job = Job.query.get_or_404(job_id)  # Adjust 'Job' to your model name
    db.session.delete(job)  # Or mark as archived if you have a column
    db.session.commit()
    flash(f"Job ID {job_id} archived successfully!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/apply-job/<int:job_id>', methods=['POST'])
def apply_job(job_id):
    # ⚠️ Security Check: Ensure the user is logged in and is an applicant
    if 'user_id' not in session or session.get('role') != 'applicant':
        flash("Please log in to apply for a job.", "error")
        return redirect(url_for('login'))
        
    applicant_user_id = session.get('user_id')

    # Check if job exists
    job = Job.query.get(job_id)
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for('applicant_dashboard'))

    # Check if applicant has already applied (prevents duplicate submissions)
    existing_application = Application.query.filter_by(
        applicant_id=applicant_user_id, 
        job_id=job_id
    ).first()

    if existing_application:
        flash(f"You have already applied for '{job.title}'. Status: {existing_application.status}", "warning")
        return redirect(url_for('applicant_dashboard'))

    # 💾 Create and save the new application
    try:
        new_application = Application(
            applicant_id=applicant_user_id,
            job_id=job_id,
            status='Submitted', # Default status for a new application
            created_at=datetime.utcnow()
        )
        db.session.add(new_application)
        db.session.commit()
        
        # Flash message for toast/alert
        flash(f"✅ Application for '{job.title}' submitted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"🚫 Error submitting application: {e}", "error")

    # Redirect back to the dashboard to show the updated history/applied status
    return redirect(url_for('applicant_dashboard'))

# -------------------- RESUME SCREENING --------------------
import spacy

# Load spaCy English model for optional NLP detection of professions
nlp = spacy.load("en_core_web_sm")

# List of common professions/job titles to detect
PROFESSIONS = [
    "engineer", "developer", "manager", "analyst", "designer",
    "consultant", "technician", "administrator", "specialist",
    "scientist", "coordinator", "assistant", "officer", "intern"
]

# app.py: Replace the function with this
def extract_text_from_pdf(filepath):
    """Extract text from PDF file, ensuring robustness."""
    try:
        reader = PdfReader(filepath)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        
        # Basic check: if extraction is weak, use a placeholder message.
        if len(text.strip()) < 100:
            print(f"Warning: Extracted text from {filepath} is too short ({len(text.strip())} chars).")
        
        return text.strip()
    except Exception as e:
        print(f"FATAL PDF READ ERROR for {filepath}: {e}")
        # Return a simple placeholder string to avoid crashing the NLP steps
        return "Extraction Failed: File could not be read."

def calculate_ai_match_score(resume_text, job_description):
    """Calculate matched skills and TF-IDF similarity score"""
    translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
    resume_clean = resume_text.lower().translate(translator)
    job_clean = job_description.lower().translate(translator)

    # Match predefined skills
    matched = [skill for skill in SKILL_KEYWORDS if re.search(r'\b' + re.escape(skill.lower()) + r'\b', resume_clean)]
    try:
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform([resume_clean, job_clean])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        score = round(similarity * 100, 2)
    except Exception as e:
        print("TF-IDF similarity error:", e)
        score = 0.0
    return matched, score

def extract_contact_info(text):
    """Extract email and phone number from resume"""
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    email = emails[0] if emails else "Not detected"
    phones = re.findall(r"(?:\+?\d{1,3}[\s\-\.])?(?:\(?\d{2,4}\)?[\s\-\.])?\d{3,4}[\s\-\.]?\d{3,4}", text)
    phone = phones[0] if phones else "Not detected"
    return email, phone

def extract_professions(resume_text):

    """Detect professions/job titles from resume"""
    resume_text_lower = resume_text.lower()
    matched = set()
    # Method 1: simple keyword matching
    for prof in PROFESSIONS:
        if prof in resume_text_lower:
            matched.add(prof)

    # Method 2: optional NLP entity recognition for future enhancement
    doc = nlp(resume_text_lower)
    for ent in doc.ents:
        if ent.label_ in ["ORG", "WORK_OF_ART", "PRODUCT"]:
            for prof in PROFESSIONS:
                if prof in ent.text.lower():
                    matched.add(prof)

    return list(matched)

def extract_applicant_name(resume_text):
    """Attempt to extract applicant name from the very top of the resume using Regex."""
    
    # Restrict search to the first 500 characters, as the name is always at the top.
    top_text = resume_text.strip()[:500] 
    
    # Regex Pattern: Looks for 2-4 capitalized words, separated by spaces.
    # Pattern: [First Name] [Optional Middle Initial/Name] [Last Name]
    # This pattern is designed to accurately capture names like "Carlo B. Aspili" while excluding addresses.
    name_pattern = r'\b[A-Z][a-z]+\b(?: \.?[A-Z][a-z]*\.?)* \b[A-Z][a-z]+\b'
    
    # Find all possible name matches in the text
    matches = re.findall(name_pattern, top_text)
    
    if matches:
        # Select the longest match, as it is most likely the full name (First, Middle, Last).
        best_match = max(matches, key=len)
        return best_match.strip()
            
    # Fallback: If the regex fails, check the first line for a simple name format.
    first_line = top_text.split('\n')[0].strip()
    
    # Ensures the first line has 2 or more words and all major words are capitalized.
    if len(first_line.split()) >= 2 and all(word[0].isupper() for word in first_line.split() if len(word) > 1):
        return first_line

    return "Unknown Applicant" # Default value if extraction fails

# app.py: New logic for /upload_screening
# app.py: CORRECTED upload_screening route
# app.py: CORRECTED upload_screening route
# app.py: CORRECTED upload_screening route

@app.route("/upload_screening", methods=["POST"])
def upload_screening():
    # 1. Authentication Check (Must be an employer)
    if 'user_id' not in session or session.get('role') != 'employer':
        flash("Unauthorized access. Please log in as an employer.", "error")
        return redirect(url_for("login"))

    # Set dummy details for the resume record since this is a manual employer screening upload
    # NOTE: You MUST ensure an Applicant with ID=1 exists for the FK constraint.
    DUMMY_APPLICANT_ID = 1

    try:
        # 2. Get form data and file
        file = request.files.get('resume_file')
        job_description_text = request.form.get('job_description')
        job_id_str = request.form.get('job_id') # Optional: If the user selects a job

        # Basic Validation
        if not file or file.filename == '':
            flash("No resume file selected!", "error")
            return redirect(url_for("employer_dashboard"))
        
        if not job_description_text:
            flash("Job Description text is required for screening.", "error")
            return redirect(url_for("employer_dashboard"))

        # Determine the Job ID for the Screening record
        job_id = int(job_id_str) if job_id_str and job_id_str.isdigit() else None
        
        # 3. SAVE THE UPLOADED FILE
        filename = secure_filename(f"screen_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        # Use the SCREENING_FOLDER for files uploaded for screening
        filepath = os.path.join(SCREENING_FOLDER, filename)
        
        # Ensure the screening folder exists and save the file
        os.makedirs(SCREENING_FOLDER, exist_ok=True)
        file.save(filepath)

        # 4. PERFORM SCREENING LOGIC - EXTRACT DATA
        resume_text = extract_text_from_pdf(filepath)
        email, phone = extract_contact_info(resume_text)
        applicant_name = extract_applicant_name(resume_text)

        matched_skills, match_score = calculate_ai_match_score(resume_text, job_description_text)
        matched_professions = extract_professions(resume_text)
        final_matched_skills = list(set(matched_skills + matched_professions))
        
        # 5. CREATE A TEMPORARY RESUME RECORD
        # This is created to satisfy the Foreign Key constraint (resume_id) in the Screening table
        new_resume = Resume(
            applicant_id=DUMMY_APPLICANT_ID,  
            filename=filename, # The file is saved in SCREENING_FOLDER but recorded in Resume table
            owner_name=applicant_name
        )
        db.session.add(new_resume)
        db.session.flush() # Get the new_resume.id before commit

        # 6. SAVE SCREENING RECORD (The main goal)
        new_screening = Screening(
            resume_id=new_resume.id,  
            job_id=job_id, # Can be None if no job was selected
            
            applicant_name=applicant_name,
            applicant_email=email,
            applicant_phone=phone,
            
            job_description_text=job_description_text,
            matched_skills=", ".join(final_matched_skills),
            match_score=match_score
        )
        db.session.add(new_screening)
        db.session.commit()

        # 7. Prepare data for the results page
        flash(f"✅ Screening successful! Match Score: {match_score}%", "success")

        highlighted_resume = resume_text
        for skill in sorted(set(final_matched_skills), key=len, reverse=True):
            try:
                highlighted_resume = re.sub(
                    rf"\b({re.escape(skill)})\b",
                    r"<mark style='background:#FFD54F;padding:0.05rem 0.15rem;border-radius:0.15rem;'>\1</mark>",
                    highlighted_resume,
                    flags=re.IGNORECASE
                )
            except re.error:
                continue

        all_jobs = Job.query.all()
        matched_jobs = [j for j in all_jobs if any(skill.lower() in f"{j.title} {j.company} {j.description}".lower() for skill in final_matched_skills)]

        # Redirect to results page (or render it directly)
        return render_template(
            "ai_resume_result.html",
            email=email,
            phone=phone,
            score=match_score,
            matched_skills=final_matched_skills,
            skills_count=len(SKILL_KEYWORDS) + len(PROFESSIONS),
            highlighted_resume=highlighted_resume,
            matched_jobs=matched_jobs
        )

    except Exception as e:
        db.session.rollback()
        print(f"FATAL SCREENING ERROR: {e}")
        # Optional: Delete the file if it was saved before the error
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        flash(f"❌ A critical server error occurred during screening: {e}", "error")
        return redirect(url_for("employer_dashboard"))

def extract_applicant_name(resume_text):
    """Attempt to extract applicant name from the first few lines."""
    # Split text into lines, take the first few lines
    first_lines = resume_text.strip().split('\n')[:4]
    
    # Simple heuristic: look for a line with at least two capitalized words
    for line in first_lines:
        words = line.strip().split()
        capitalized_words = [w for w in words if w[0].isupper() and len(w) > 1]
        
        # If two or more capitalized words are found, treat the line as the name
        if len(capitalized_words) >= 2:
            return " ".join(capitalized_words)
            
    return "Unknown Applicant" # Default if extraction fails

@app.route("/download_screening/<filename>")
def download_screening(filename):
    try:
        return send_from_directory(SCREENING_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        flash("Screening file not found.", "error")
        return redirect(url_for("employer_dashboard"))

# FIX: /delete_screening/<int:screening_id>
@app.route("/delete_screening/<int:screening_id>", methods=["POST"])
def delete_screening(screening_id):
    # ✅ NEW LOGIC: Query and delete the Screening object
    screening_record = Screening.query.get(screening_id)

    if screening_record:
        # Note: You were trying to delete a PDF, but the screening record
        # doesn't store a separate file. Just delete the database record.
        db.session.delete(screening_record)
        db.session.commit()
        flash("✅ Screening record deleted!", "success")
    else:
        flash("Screening record not found.", "error")
    return redirect(url_for("employer_dashboard"))

# -------------------- APPLICANT PROFILE --------------------
@app.route("/applicant/profile", methods=["GET", "POST"])
def applicant_profile():
    if 'user_id' not in session or session.get("role") != 'applicant':
        flash("Please log in as an applicant.", "error")
        return redirect(url_for("login"))

    applicant = Applicant.query.filter_by(user_id=session['user_id']).first()
    if not applicant:
        flash("Applicant profile not found.", "error")
        return redirect(url_for("applicant_dashboard"))

    if request.method == "POST":
        applicant.fullname = request.form.get("fullname")
        applicant.email = request.form.get("email")
        applicant.skills = request.form.get("skills")
        applicant.experience = request.form.get("experience")
        db.session.commit()
    flash('Profile updated successfully!')
    return redirect(url_for('applicant_dashboard'))
    return render_template("applicant_profile.html", applicant=applicant)

# -------------------- USER MANAGEMENT EDIT PAGES (REVISED) --------------------
@app.route("/edit_applicant/<int:applicant_id>", methods=["GET", "POST"])
def edit_applicant(applicant_id):
    applicant = Applicant.query.get_or_404(applicant_id)

    if request.method == "POST":
        applicant.fullname = request.form.get("fullname")
        applicant.email = request.form.get("email")
        applicant.skills = request.form.get("skills")
        applicant.experience = request.form.get("experience")
        db.session.commit()
        flash(f"✅ Applicant '{applicant.fullname}' profile updated!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("edit_applicant.html", applicant=applicant)

@app.route("/edit_employer/<int:employer_id>", methods=["GET", "POST"])
def edit_employer(employer_id):
    employer = Employer.query.get_or_404(employer_id)

    if request.method == "POST":
        employer.fullname = request.form.get("fullname")
        employer.email = request.form.get("email")
        employer.company = request.form.get("company")
        db.session.commit()
        flash(f"✅ Employer '{employer.fullname}' profile updated!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_employer.html", employer=employer)

@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    applicant_id = session.get('user_id')
    if not applicant_id:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    applicant = Applicant.query.filter_by(user_id=applicant_id).first()
    if not applicant:
        flash("Applicant profile not found.", "error")
        return redirect(url_for('applicant_dashboard'))

    if request.method == 'POST':
        applicant.fullname = request.form.get('fullname')
        applicant.skills = request.form.get('skills')
        applicant.experience = request.form.get('experience')
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('applicant_dashboard'))
    return render_template('applicant_profile.html', applicant=applicant)

# -------------------- RUN APP --------------------
if __name__ == "__main__":
    with app.app_context():
        # hash_plaintext_passwords()   <-- remove/comment this
        db.create_all()
    app.run(debug=True)