from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session # <-- Ensure 'session' is imported!
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail, Message
import re
from PyPDF2 import PdfReader
import string
import random
from sqlalchemy import func
from flask import request, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import send_from_directory
from sqlalchemy import join
from sqlalchemy.orm import joinedload
import spacy

# ✅ NLP/ML imports
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'secret123')

# app.py (Near the top, after db setup)

# -------------------- DATABASE SETUP (SQLite) --------------------
# Use SQLite from .env file, fallback to default SQLite path
database_url = os.getenv('DATABASE_URL', 'sqlite:///instance/smarthire.db')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# -------------------- FOLDER DEFINITIONS (CLEANUP) --------------------
# Define Python Variables for the folder paths once
UPLOAD_FOLDER = 'resumes'         # Used for general applicant uploads (if applicable)
SCREENING_FOLDER = 'screened_resumes' # Used for employer screening uploads (must be created)
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------- FLASK CONFIGURATION --------------------
# Apply the defined variables to the Flask config dictionary once
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SCREENING_FOLDER'] = SCREENING_FOLDER

# -------------------- EMAIL CONFIGURATION --------------------
# Email configuration (Update these with your email credentials)
# For Gmail: Use App Password (not regular password)
# Enable 2-factor authentication and generate App Password
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'caragutierrez.may14@gmail.com'  # ⚠️ UPDATE THIS with your email address
app.config['MAIL_PASSWORD'] = 'hojmgyrwsajbmhre'      # ⚠️ UPDATE THIS with your Gmail App Password
app.config['MAIL_DEFAULT_SENDER'] = 'caragutierrez.may14@gmail.com'  # ⚠️ UPDATE THIS with your email address

mail = Mail(app)

# -------------------- OTP HELPER FUNCTIONS --------------------
def generate_otp():
    """Generate a 6-digit OTP"""
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])

def send_otp_email(email, otp):
    """Send OTP to user's email"""
    try:
        msg = Message(
            subject='SmartHire - Email Verification OTP',
            recipients=[email],
            body=f'''
Hello!

Thank you for signing up with SmartHire!

Your verification code is: {otp}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.

Best regards,
SmartHire Team
            ''',
            html=f'''
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #08106E;">SmartHire - Email Verification</h2>
                <p>Hello!</p>
                <p>Thank you for signing up with SmartHire!</p>
                <div style="background-color: #f0f0f0; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">
                    <h1 style="color: #08106E; font-size: 32px; letter-spacing: 5px; margin: 0;">{otp}</h1>
                </div>
                <p>This code will expire in <strong>10 minutes</strong>.</p>
                <p>If you didn't request this code, please ignore this email.</p>
                <p style="margin-top: 30px;">Best regards,<br>SmartHire Team</p>
            </div>
            '''
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

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
    employer_id = db.Column(db.Integer, db.ForeignKey('employer.id'), nullable=False)
    employer = db.relationship('Employer', backref='jobs')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# --- Applicant Model (Removed incorrect Job linkage) ---
class Applicant(db.Model):
    __tablename__ = "applicant"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    fullname = db.Column(db.String(100), nullable=False)
    target_job = db.Column(db.String(255))
    email = db.Column(db.String(255))
    contact_number = db.Column(db.String(50))
    skills = db.Column(db.Text)
    experience = db.Column(db.Integer)
    # 1. ADD INDENTATION HERE
    resume_filename = db.Column(db.String(255))
    photo_filename = db.Column(db.String(255))
    # 2. ENSURE INDENTATION IS CONSISTENT HERE
    
    @property
    def photo_url(self):
        """Generate URL for profile photo"""
        from flask import url_for
        if self.photo_filename:
            return url_for('uploaded_file', filename=self.photo_filename)
        return url_for('static', filename='images/man2x2.jpg')
    
    @property
    def profile_image_url(self):
        """Alias for photo_url for compatibility"""
        return self.photo_url
    
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
    __tablename__ = 'resume'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False) 
    owner_name = db.Column(db.String(255), nullable=False)
    applicant_id = db.Column(db.Integer, db.ForeignKey('applicant.user_id'), nullable=True)  # Connect to Applicant
    uploaded_at = db.Column(db.DateTime, default=func.now())
    
    # Relationship to Applicant
    applicant = db.relationship('Applicant', foreign_keys=[applicant_id], backref='resumes')
    
    def __repr__(self):
        return f"<Resume id={self.id} owner='{self.owner_name}' applicant_id={self.applicant_id}>"

class Screening(db.Model):
    __tablename__ = 'screening'
    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey('resume.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('Job.id'))
    employer_id = db.Column(db.Integer, db.ForeignKey('employer.id'), nullable=True)  # Track which employer did the screening
    
    # Applicant Information (extracted from resume)
    applicant_name = db.Column(db.String(150))
    applicant_email = db.Column(db.String(150))
    applicant_phone = db.Column(db.String(50))
    
    # Job Matching Details
    job_description_text = db.Column(db.Text, nullable=False)  # The job description used for matching
    matched_skills = db.Column(db.Text)  # Comma-separated list of matched skills
    match_score = db.Column(db.Float)  # AI match score (0-100)
    
    # Resume Text Summary (first 500 chars for quick reference)
    resume_text_summary = db.Column(db.Text, nullable=True)
    
    # Timestamps
    screened_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    resume = db.relationship('Resume', backref='screenings')
    job = db.relationship('Job', backref='screenings')
    employer = db.relationship('Employer', backref='screenings')
    
    def __repr__(self):
        return f"<Screening id={self.id} applicant='{self.applicant_name}' score={self.match_score}%>"

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

PROFESSIONS = [
    "engineer", "developer", "manager", "analyst", "designer",
    "consultant", "technician", "administrator", "specialist",
    "scientist", "coordinator", "assistant", "officer", "intern",
    "accountant", "auditor", "bookeeper", "architect"
    # Add other common titles here
]
# -------------------- AUTH --------------------

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def do_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Please enter both username and password", "error")
        return redirect(url_for("login"))

    user = User.query.filter(func.lower(User.username) == username.lower()).first()

    if user:
        # Check if password is hashed or plain text (for backward compatibility)
        password_valid = False
        if is_hashed(user.password):
            # Password is hashed, use check_password_hash
            password_valid = check_password_hash(user.password, password)
        else:
            # Password is plain text (backward compatibility)
            password_valid = (user.password == password)
            # If login successful with plain text, hash it for future use
            if password_valid:
                user.password = generate_password_hash(password)
                db.session.commit()
        
        if password_valid:
            session["user_id"] = user.id
            session["role"] = user.role
            print(f"[SUCCESS] Logged in as: {user.username} (role={user.role})")

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
    flash("Invalid username or password", "error")
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"] 
        password = request.form["password"]
        contact = request.form.get("contact", "")
        user_role = request.form.get("role", "applicant")  # default 'applicant'

        # Check if username exists
        existing_user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if existing_user:
            flash("Username already exists!", "error")
            return redirect(url_for("signup"))

        # Check if email already exists
        if user_role == "applicant":
            existing_email = Applicant.query.filter(func.lower(Applicant.email) == email.lower()).first()
        elif user_role == "employer":
            existing_email = Employer.query.filter(func.lower(Employer.email) == email.lower()).first()
        else:
            existing_email = None

        if existing_email:
            flash("Email already registered!", "error")
            return redirect(url_for("signup"))

        # Generate OTP
        otp = generate_otp()
        
        # Store signup data and OTP in session
        session['signup_data'] = {
            'username': username,
            'email': email,
            'password': password,
            'contact': contact,
            'role': user_role,
            'otp': otp,
            'otp_expiry': (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        }

        # Send OTP email
        if send_otp_email(email, otp):
            flash("Verification code sent to your email! Please check your inbox.", "success")
            return redirect(url_for("verify_otp"))
        else:
            flash("Failed to send verification email. Please try again.", "error")
            return redirect(url_for("signup"))
    
    return render_template("signup.html")

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    # Check if signup data exists in session
    if 'signup_data' not in session:
        flash("Please complete the signup form first.", "error")
        return redirect(url_for("signup"))

    signup_data = session.get('signup_data')
    
    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()
        stored_otp = signup_data.get('otp')
        otp_expiry = datetime.fromisoformat(signup_data.get('otp_expiry'))

        # Check if OTP expired
        if datetime.utcnow() > otp_expiry:
            session.pop('signup_data', None)
            flash("OTP has expired. Please sign up again.", "error")
            return redirect(url_for("signup"))

        # Verify OTP
        if entered_otp == stored_otp:
            try:
                # Create User account
                username = signup_data['username']
                email = signup_data['email']
                password = signup_data['password']
                contact = signup_data['contact']
                user_role = signup_data['role']

                hashed_password = generate_password_hash(password)
                new_user = User(
                    username=username,
                    password=hashed_password,
                    role=user_role
                )

                db.session.add(new_user)
                db.session.flush()  # to get new_user.id

                # Create profile
                if user_role == "applicant":
                    new_profile = Applicant(
                        user_id=new_user.id,
                        fullname=username,
                        email=email,
                        contact_number=contact,
                        skills="N/A",
                        experience="0 years"
                    )
                elif user_role == "employer":
                    new_profile = Employer(
                        user_id=new_user.id,
                        fullname=username,
                        email=email,
                        phone=contact,
                        company="N/A"
                    )
                else:
                    db.session.rollback()
                    flash("Invalid role selected.", "error")
                    session.pop('signup_data', None)
                    return redirect(url_for("signup"))

                db.session.add(new_profile)
                db.session.commit()

                # Clear signup data from session
                session.pop('signup_data', None)

                flash("Email verified successfully! You can now log in.", "success")
                return redirect(url_for("login"))

            except Exception as e:
                db.session.rollback()
                flash(f"Error during signup: {e}", "error")
                return redirect(url_for("verify_otp"))
        else:
            flash("Invalid verification code. Please try again.", "error")
            return redirect(url_for("verify_otp"))

    # Show OTP verification page
    email = signup_data.get('email', '')
    return render_template("verify_otp.html", email=email)

@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    """Resend OTP to user's email"""
    if 'signup_data' not in session:
        flash("Please complete the signup form first.", "error")
        return redirect(url_for("signup"))

    signup_data = session.get('signup_data')
    email = signup_data.get('email')
    
    # Generate new OTP
    otp = generate_otp()
    signup_data['otp'] = otp
    signup_data['otp_expiry'] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    session['signup_data'] = signup_data

    # Send new OTP
    if send_otp_email(email, otp):
        flash("New verification code sent to your email!", "success")
    else:
        flash("Failed to send verification email. Please try again.", "error")
    
    return redirect(url_for("verify_otp"))

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
@app.route("/dashboard/employer")
def employer_dashboard():
    if 'user_id' not in session or session.get('role') != 'employer':
        flash("Unauthorized access. Please log in as an employer.", "error")
        return redirect(url_for("login"))

    employer = Employer.query.filter_by(user_id=session['user_id']).first()
    if not employer:
        flash("Employer profile not found.", "error")
        return redirect(url_for("login"))

    # Fetches jobs posted by this employer
    jobs_list = Job.query.filter_by(employer_id=employer.id).order_by(Job.created_at.desc()).all()

    resumes_list = Resume.query.all()
    # Load job and employer relationships for screenings - filter by current employer
    screenings_list = Screening.query.options(
        joinedload(Screening.job),
        joinedload(Screening.employer)
    ).filter_by(employer_id=employer.id).order_by(Screening.screened_at.desc()).all()

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
    applicant = Applicant.query.filter_by(user_id=applicant_user_id).first()
    if not applicant:
        flash("Profile not found. Please complete your profile.", "error")
        return redirect(url_for('edit_profile'))
        
    # 2. Fetch Applications (History and Stats)
    # 🌟 THIS IS THE LINE TO REPLACE FOR EFFICIENCY 🌟
    # applications = Application.query.filter_by(applicant_id=applicant.user_id).order_by(Application.created_at.desc()).all()
    
    # 🎯 EFFICIENT REPLACEMENT: Joins the Job table in one query
    applications = Application.query.options(joinedload(Application.job)).\
        filter_by(applicant_id=applicant.user_id).\
        order_by(Application.created_at.desc()).\
        all()
    
    # 3. Calculate Stats
    # Note: 'matches' logic requires the TFIDF/Cosine Similarity logic you've set up
    jobs = Job.query.filter_by(status='Approved').order_by(Job.created_at.desc()).limit(10).all()

    # Prepare data for template
    applied_job_ids = {app.job_id for app in applications}
    num_interviews = Application.query.filter_by(applicant_id=applicant.user_id, status='Interview').count()
    
    # Placeholder for a real ML match count
    num_matches = 0 
    
    # Calculate Profile Completion (simple logic for the progress bar)
    profile_score = 0
    if applicant.fullname: profile_score += 1
    if applicant.target_job: profile_score += 1
    if applicant.skills: profile_score += 1
    if applicant.resume_filename: profile_score += 1
    profile_percent = int((profile_score / 4) * 100) # Max 4 fields for 100%

    return render_template('applicant_dashboard.html',
        applicant=applicant,
        jobs=jobs,
        applications=applications, # Now efficiently loaded
        applied_job_ids=applied_job_ids,
        interviews=range(num_interviews),
        matches=range(num_matches),
        profile_percent=profile_percent
    )

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

@app.route('/upload-resume', methods=['POST'])
def upload_resume():
    # ⚠️ Security Check and Applicant Fetch (KEEP)
    if 'user_id' not in session or session.get('role') != 'applicant':
        flash("Please log in to update your profile.", "warning")
        return redirect(url_for('login'))
        
    applicant_user_id = session.get('user_id')
    applicant = Applicant.query.filter_by(user_id=applicant_user_id).first()

    # Get form data (KEEP)
    new_fullname = request.form.get('fullname', '').strip()
    new_target_job = request.form.get('jobtitle', '').strip()

    # 1. Update Profile Fields (KEEP)
    if new_fullname:
        applicant.fullname = new_fullname
        
    if new_target_job:
        applicant.target_job = new_target_job
    
    # 2. Handle File Upload (Resume PDF)
    if 'resume' in request.files:
        file = request.files['resume']
        
        if file.filename != '' and allowed_file(file.filename):
            
            # 2a. Save file to server (KEEP)
            base_filename = secure_filename(file.filename)
            # Use the applicant's ID for a unique name (as in your current code)
            filename = f"{applicant_user_id}_{base_filename}" 
            
            upload_dir = app.config['UPLOAD_FOLDER']
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)
            
            # 2b. Update the main Applicant profile record (KEEP)
            applicant.resume_filename = filename

            # 2c. 🌟 SAVE TO RESUME TABLE - Connected to Applicant 🌟
            try:
                # Check if resume already exists for this applicant (update instead of duplicate)
                existing_resume = Resume.query.filter_by(applicant_id=applicant.user_id).first()
                
                if existing_resume:
                    # Update existing resume record
                    existing_resume.filename = filename
                    existing_resume.owner_name = applicant.fullname
                    existing_resume.uploaded_at = datetime.utcnow()
                    print(f"[OK] Updated existing resume record: ID={existing_resume.id}, Applicant ID={applicant.user_id}")
                else:
                    # Create new resume record - Connected to Applicant
                    new_resume = Resume(
                        owner_name=applicant.fullname,  # Applicant's name
                        filename=filename,  # Resume file name
                        applicant_id=applicant.user_id,  # 🌟 Connect to Applicant via user_id
                        uploaded_at=datetime.utcnow()  # Upload timestamp
                    )
                    db.session.add(new_resume)
                    print(f"[OK] Created new resume record: Applicant ID={applicant.user_id}, Filename={filename}")
                
            except Exception as e:
                # Log an error but allow profile update to continue if possible
                print(f"[ERROR] Error saving to 'resume' table: {e}")
                flash("Resume could not be saved to database, but file was uploaded.", "warning")


        elif file.filename != '' and not allowed_file(file.filename):
            flash("Only PDF files are allowed for resume upload.", "error")
            # Continue to save text fields even if file fails
    
    # 3. Save all changes (profile fields and new resume record) (KEEP)
    try:
        # This commits the Applicant profile changes AND the new Resume record
        db.session.commit()
        flash("Profile and Resume updated successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error saving profile: {e}", "error")

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
    flash(f"Job '{title}' added successfully!", "success")
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
        
        flash(f"Job '{job.title}' updated successfully!", "success")
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
    flash(f"Job '{job.title}' approved successfully!", "success")
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

    # 💾 Create and save the new application to Application table
    try:
        new_application = Application(
            applicant_id=applicant_user_id,  # Connected to Applicant
            job_id=job_id,  # Connected to Job
            status='Submitted',  # Default status for a new application
            created_at=datetime.utcnow()  # Application timestamp
        )
        db.session.add(new_application)
        db.session.commit()
        
        print(f"[OK] Application saved to database: ID={new_application.id}, Applicant ID={applicant_user_id}, Job ID={job_id}")
        # Flash message for toast/alert
        flash(f"Application for '{job.title}' submitted successfully! Saved to Job History.", "success")
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Error saving application: {e}")
        flash(f"Error submitting application: {e}", "error")

    # Redirect back to the dashboard to show the updated history/applied status
    return redirect(url_for('applicant_dashboard'))

# -------------------- RESUME SCREENING --------------------
@app.route('/screen-existing-resume', methods=['POST'])
def screen_existing_resume():
    """
    Screen an existing resume from the Resume table against a job.
    All screening details will be saved to the Screening table.
    """
    # 1. Authentication Check (Must be an employer)
    if 'user_id' not in session or session.get('role') != 'employer':
        flash("Unauthorized access. Please log in as an employer.", "error")
        return redirect(url_for("login"))
    
    try:
        # 2. Get form data
        resume_id = request.form.get('resume_id')
        job_id_str = request.form.get('job_id')
        
        # Validation
        if not resume_id or not job_id_str:
            flash("Please select both a resume and a job.", "error")
            return redirect(url_for("employer_dashboard"))
        
        resume_id = int(resume_id)
        job_id = int(job_id_str) if job_id_str.isdigit() else None
        
        if not job_id:
            flash("Invalid job selected.", "error")
            return redirect(url_for("employer_dashboard"))
        
        # 3. Get employer
        employer = Employer.query.filter_by(user_id=session['user_id']).first()
        if not employer:
            flash("Employer profile not found.", "error")
            return redirect(url_for("employer_dashboard"))
        
        # 4. Get Resume from Resume table
        resume = Resume.query.get(resume_id)
        if not resume:
            flash("Resume not found in database.", "error")
            return redirect(url_for("employer_dashboard"))
        
        # 5. Get Job
        job = Job.query.get(job_id)
        if not job:
            flash("Job not found.", "error")
            return redirect(url_for("employer_dashboard"))
        
        # Security: Verify the job belongs to the current employer
        if job.employer_id != employer.id:
            flash("Unauthorized: You can only screen resumes against your own job posts.", "error")
            return redirect(url_for("employer_dashboard"))
        
        # 6. Build job description text
        job_description_text = f"{job.title}\n\n{job.description}"
        if job.location:
            job_description_text += f"\n\nLocation: {job.location}"
        if job.job_type:
            job_description_text += f"\n\nJob Type: {job.job_type}"
        
        # 7. Get resume file path and extract text
        # Check if resume is in UPLOAD_FOLDER (applicant uploads) or SCREENING_FOLDER
        resume_filepath = None
        if resume.filename.startswith('screen_'):
            resume_filepath = os.path.join(SCREENING_FOLDER, resume.filename)
        else:
            resume_filepath = os.path.join(app.config['UPLOAD_FOLDER'], resume.filename)
        
        if not os.path.exists(resume_filepath):
            flash(f"Resume file not found: {resume.filename}", "error")
            return redirect(url_for("employer_dashboard"))
        
        # 8. Extract resume text
        resume_text = extract_text_from_pdf(resume_filepath)
        email, phone = extract_contact_info(resume_text)
        applicant_name = extract_applicant_name(resume_text)
        
        # Use resume owner name if extraction fails
        if applicant_name == "Unknown Applicant" and resume.owner_name:
            applicant_name = resume.owner_name
        
        # 9. Calculate match scores
        matched_skills, match_score = calculate_ai_match_score(resume_text, job_description_text)
        matched_professions = extract_professions(resume_text)
        final_matched_skills = list(set(matched_skills + matched_professions))
        
        # 10. Create resume summary
        resume_summary = resume_text[:500] + "..." if len(resume_text) > 500 else resume_text
        
        # 11. SAVE TO SCREENING TABLE - All details saved to database
        new_screening = Screening(
            resume_id=resume.id,  # Connected to Resume table
            job_id=job_id,  # Connected to Job
            employer_id=employer.id,  # Track which employer did the screening
            
            # Applicant Information (extracted from resume)
            applicant_name=applicant_name,
            applicant_email=email,
            applicant_phone=phone,
            
            # Job Matching Details
            job_description_text=job_description_text,  # Full job description used for matching
            matched_skills=", ".join(final_matched_skills),  # All matched skills
            match_score=match_score,  # AI match score percentage
            
            # Resume Summary for quick reference
            resume_text_summary=resume_summary,
            
            # Timestamp is automatically set by default=datetime.utcnow
        )
        db.session.add(new_screening)
        db.session.commit()
        
        print(f"[OK] Screening saved to Screening table: ID={new_screening.id}, Resume ID={resume.id}, Job ID={job_id}, Score={match_score}%")
        flash(f"Resume screened successfully! Match Score: {match_score}% (Saved to Screening table)", "success")
        
        # 12. Prepare data for results page
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
        
        return render_template(
            "ai_resume_result.html",
            applicant_name=applicant_name,
            email=email,
            phone=phone,
            score=match_score,
            matched_skills=final_matched_skills,
            skills_count=len(SKILL_KEYWORDS) + len(PROFESSIONS),
            highlighted_resume=highlighted_resume,
            resume_filename=resume.filename,
            matched_jobs=matched_jobs
        )
        
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Error screening existing resume: {e}")
        flash(f"Error screening resume: {e}", "error")
        return redirect(url_for("employer_dashboard"))
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("WARNING: SpaCy model 'en_core_web_sm' not found. Screening will likely fail.")
    pass # Allow the app to run, but log the warning

@app.route('/screenings/<filename>')
def screened_file(filename):
    """Serve screened resumes from SCREENING_FOLDER"""
    try:
        # SCREENING_FOLDER must be defined globally (e.g., SCREENING_FOLDER = 'screened_resumes')
        return send_from_directory(app.config['SCREENING_FOLDER'], filename)
    except FileNotFoundError:
        return "File not found.", 404

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

@app.route("/upload_screening", methods=["POST"])
def upload_screening():
    # 1. Authentication Check (Must be an employer)
    if 'user_id' not in session or session.get('role') != 'employer':
        flash("Unauthorized access. Please log in as an employer.", "error")
        return redirect(url_for("login"))

    # REMOVED: DUMMY_APPLICANT_ID = 1

    try:
        # 2. Get form data and file
        file = request.files.get('resume_file')
        job_description_text = request.form.get('job_description', '').strip()
        job_id_str = request.form.get('job_id') # Optional: If the user selects a job

        # Basic Validation
        if not file or file.filename == '':
            flash("No resume file selected!", "error")
            return redirect(url_for("employer_dashboard"))
        
        # Determine the Job ID for the Screening record
        job_id = int(job_id_str) if job_id_str and job_id_str.isdigit() else None
        
        # Get employer to validate job ownership
        employer = Employer.query.filter_by(user_id=session['user_id']).first()
        if not employer:
            flash("Employer profile not found.", "error")
            return redirect(url_for("employer_dashboard"))
        
        # 🌟 NEW: If job_id is provided, automatically use that job's description
        selected_job = None
        if job_id:
            selected_job = Job.query.get(job_id)
            if selected_job:
                # Security: Verify the job belongs to the current employer
                if selected_job.employer_id != employer.id:
                    flash("Unauthorized: You can only screen resumes against your own job posts.", "error")
                    return redirect(url_for("employer_dashboard"))
                
                # Use the job's description, title, and other details for matching
                # Combine title, description, and requirements for better matching
                job_description_text = f"{selected_job.title}\n\n{selected_job.description}"
                if selected_job.location:
                    job_description_text += f"\n\nLocation: {selected_job.location}"
                if selected_job.job_type:
                    job_description_text += f"\n\nJob Type: {selected_job.job_type}"
        
        # Final validation: job description is required (either from form or from selected job)
        if not job_description_text:
            flash("Job Description is required for screening. Please select a job or paste a job description.", "error")
            return redirect(url_for("employer_dashboard"))
        
        # 3. SAVE THE UPLOADED FILE
        filename = secure_filename(f"screen_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        filepath = os.path.join(SCREENING_FOLDER, filename)
        
        os.makedirs(SCREENING_FOLDER, exist_ok=True)
        file.save(filepath)

        # 4. PERFORM SCREENING LOGIC - EXTRACT DATA
        resume_text = extract_text_from_pdf(filepath)
        email, phone = extract_contact_info(resume_text)
        applicant_name = extract_applicant_name(resume_text)
        
        # -----------------------------------------------------------------
        # NOTE: For screening, we don't create Applicant records automatically
        # The screening is done on external resumes uploaded by employers
        # -----------------------------------------------------------------
        
        # 4b. Calculate Scores
        matched_skills, match_score = calculate_ai_match_score(resume_text, job_description_text)
        matched_professions = extract_professions(resume_text)
        final_matched_skills = list(set(matched_skills + matched_professions))
        
        # 5. CREATE A TEMPORARY RESUME RECORD (Now linked to a REAL Applicant ID)
        new_resume = Resume(
            filename=filename, 
            owner_name=applicant_name
        )
        db.session.add(new_resume)
        db.session.flush() # Get the new_resume.id before commit

        # 6. SAVE SCREENING RECORD - All details saved to database
        # Create resume text summary (first 500 characters for quick reference)
        resume_summary = resume_text[:500] + "..." if len(resume_text) > 500 else resume_text
        
        new_screening = Screening(
            resume_id=new_resume.id,  
            job_id=job_id,
            employer_id=employer.id,  # Track which employer did the screening
            
            # Applicant Information (extracted from resume)
            applicant_name=applicant_name,
            applicant_email=email,
            applicant_phone=phone,
            
            # Job Matching Details
            job_description_text=job_description_text,  # Full job description used for matching
            matched_skills=", ".join(final_matched_skills),  # All matched skills
            match_score=match_score,  # AI match score percentage
            
            # Resume Summary for quick reference
            resume_text_summary=resume_summary,
            
            # Timestamp is automatically set by default=datetime.utcnow
        )
        db.session.add(new_screening)
        db.session.commit() # Commit Resume and Screening records to database
        
        print(f"[OK] Screening saved to database: ID={new_screening.id}, Applicant={applicant_name}, Score={match_score}%, Job ID={job_id}")

        # 7. Prepare data for the results page
        flash(f"Screening successful! Match Score: {match_score}%", "success")


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
            applicant_name=applicant_name,  
            email=email,
            phone=phone,
            score=match_score,
            matched_skills=final_matched_skills,
            skills_count=len(SKILL_KEYWORDS) + len(PROFESSIONS),
            highlighted_resume=highlighted_resume,
            resume_filename=filename,
            matched_jobs=matched_jobs
        )

    except Exception as e: 
        db.session.rollback()
        print(f"FATAL SCREENING ERROR: {e}")
        # Optional: Delete the file if it was saved before the error
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        flash(f"A critical server error occurred during screening: {e}", "error")
        return redirect(url_for("employer_dashboard"))
# Make sure your helper function also uses clean, standard indentation
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

@app.route('/resume_screening_submit', methods=['POST'])
def resume_screening_submit():
    # This route handles saving the screening result to the database after
    # the matching logic (NLP/ML) has completed.
    
    # Authentication check
    if 'user_id' not in session or session.get('role') != 'employer':
        flash("Unauthorized access. Please log in as an employer.", "error")
        return redirect(url_for("login"))
    
    employer = Employer.query.filter_by(user_id=session['user_id']).first()
    if not employer:
        flash("Employer profile not found.", "error")
        return redirect(url_for("login"))
    
    try:
        # Get form data
        applicant_data = {
            'name': request.form.get('applicant_name', 'Unknown'),
            'email': request.form.get('applicant_email', 'N/A'),
            'phone': request.form.get('applicant_phone', 'N/A'),
            'score': float(request.form.get('match_score', 0.0)),
            'skills': request.form.get('matched_skills', 'No skills found'),
            'job_id': request.form.get('job_id'),
            'resume_id': request.form.get('resume_id'),
            'job_description': request.form.get('job_description', ''),
        }

        # Get resume_id and job_id (required fields)
        resume_id = applicant_data['resume_id']
        job_id = applicant_data['job_id'] if applicant_data['job_id'] else None
        
        # If resume_id is not provided, we need to find or create one
        if not resume_id:
            # Try to find existing resume by owner name
            resume = Resume.query.filter_by(owner_name=applicant_data['name']).first()
            if not resume:
                flash("Resume ID is required for screening.", "error")
                return redirect(url_for('employer_dashboard'))
            resume_id = resume.id
        else:
            resume_id = int(resume_id)

        # Create a new Screening object with correct field names
        new_screening = Screening(
            resume_id=resume_id,
            job_id=int(job_id) if job_id else None,
            employer_id=employer.id,  # Track which employer did the screening
            applicant_name=applicant_data['name'],
            applicant_email=applicant_data['email'],
            applicant_phone=applicant_data['phone'],
            job_description_text=applicant_data['job_description'] or 'N/A',
            matched_skills=applicant_data['skills'],
            match_score=applicant_data['score'],
            resume_text_summary=None  # Can be set if available
        )
        
        # Add to session and commit to the database
        db.session.add(new_screening)
        db.session.commit()
        
        flash(f"Screening results for {applicant_data['name']} saved successfully!", 'success')
        
        # Redirect the user to the dashboard to see the new record
        return redirect(url_for('employer_dashboard'))

    except Exception as e:
        db.session.rollback() 
        flash(f"Error saving screening record: {str(e)}", 'error')
        # Redirect back to the screening page or dashboard
        return redirect(url_for('employer_dashboard'))
# -------------------- DOWNLOAD AND DELETE ROUTES --------------------

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
        db.session.delete(screening_record)
        db.session.commit()
        flash("Screening record deleted!", "success")
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
        flash(f"Applicant '{applicant.fullname}' profile updated!", "success")
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
        flash(f"Employer '{employer.fullname}' profile updated!", "success")
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
        applicant.fullname = request.form.get('name') or request.form.get('fullname') or applicant.fullname
        applicant.email = request.form.get('email') or applicant.email
        applicant.skills = request.form.get('skills') or applicant.skills
        applicant.experience = request.form.get('experience') or applicant.experience
        
        # Handle photo upload
        if 'photo' in request.files:
            photo_file = request.files['photo']
            if photo_file and photo_file.filename != '':
                # Check if it's an image file
                allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                file_ext = photo_file.filename.rsplit('.', 1)[1].lower() if '.' in photo_file.filename else ''
                
                if file_ext in allowed_image_extensions:
                    # Generate unique filename
                    filename = secure_filename(photo_file.filename)
                    unique_filename = f"{applicant_id}_photo_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
                    
                    # Save file
                    upload_dir = app.config['UPLOAD_FOLDER']
                    if not os.path.exists(upload_dir):
                        os.makedirs(upload_dir)
                    
                    filepath = os.path.join(upload_dir, unique_filename)
                    photo_file.save(filepath)
                    
                    # Update applicant record
                    applicant.photo_filename = unique_filename
                else:
                    flash("Invalid image format. Please upload PNG, JPG, JPEG, GIF, or WEBP.", "error")
        
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('applicant_dashboard'))
    return render_template('applicant_profile.html', applicant=applicant)

@app.route('/update_user_record/<string:record_type>/<int:record_id>', methods=['POST'])
def update_user_record(record_type, record_id):
    try:
        data = request.get_json()
        
        # Determine which model to use (Applicant or Employer)
        if record_type == 'Applicant':
            RecordModel = Applicant
        elif record_type == 'Employer':
            RecordModel = Employer
        else:
            return jsonify({'success': False, 'error': 'Invalid record type'}), 400

        # Fetch the record from the database
        record = RecordModel.query.get(record_id)
        if not record:
            return jsonify({'success': False, 'error': 'Record not found'}), 404

        # Update the record object with the new data
        # Note: The keys in 'data' must match your model's column names (e.g., 'experience')
        for key, value in data.items():
            if hasattr(record, key):
                setattr(record, key, value)

        # Commit (save) changes permanently to the database
        db.session.commit()
        
        return jsonify({'success': True}), 200

    except Exception as e:
        # Important: Roll back if an error occurs
        db.session.rollback() 
        return jsonify({'success': False, 'error': str(e)}), 500
# -------------------- RUN APP --------------------
if __name__ == "__main__":
    with app.app_context():
        # hash_plaintext_passwords()   <-- remove/comment this
        db.create_all()
    app.run(debug=True)
