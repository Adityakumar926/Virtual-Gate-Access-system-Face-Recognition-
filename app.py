"""
Virtual Gate‑Access System
──────────────────────────
"""

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, Response
)
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import face_recognition, numpy as np, os, secrets, csv
from datetime import datetime, timedelta
from io import StringIO
import pytz

# ─── Config ─────────────────────────────────────────────────────────────
COOLDOWN_SECONDS = 60                         
IST = pytz.timezone("Asia/Kolkata")
USER_IMG_DIR = os.path.join("static", "user_images")

app = Flask(__name__)
app.secret_key = "your_secret_key"            
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"

app.config.update(
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_PORT = 587,
    MAIL_USE_TLS = True,
    MAIL_USERNAME = "adityakum.9430@gmail.com",
    MAIL_PASSWORD = "vnih ksau lbxf tuyx"
)

db = SQLAlchemy(app)
mail = Mail(app)
os.makedirs(USER_IMG_DIR, exist_ok=True)

# ─── Jinja filter UTC→IST ───────────────────────────────────────────────
@app.template_filter("to_ist_str")
def to_ist_str(dt_utc):
    if not dt_utc:
        return ""
    dt_utc = dt_utc.replace(tzinfo=pytz.utc)
    return dt_utc.astimezone(IST).strftime("%d‑%b‑%Y %I:%M:%S %p")

# ─── Models ──────────────────────────────────────────────────────────────
class AuthUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    pw_hash = db.Column(db.String(256), nullable=False)
    reset_token = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)

class FaceUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String,  nullable=False)
    roll = db.Column(db.String,  unique=True, nullable=False)
    encoding = db.Column(db.LargeBinary, nullable=False)

    def detections(self):
        return DetectionLog.query.filter_by(face_user_id=self.id).count()

    def last_detected(self):
        log = (DetectionLog.query.filter_by(face_user_id=self.id)
                                .order_by(DetectionLog.detected_at.desc())
                                .first())
        return log.detected_at if log else None

class DetectionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    face_user_id = db.Column(db.Integer, db.ForeignKey("face_user.id"))
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)

# ─── Decorators ──────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        return f(*a, **kw) if "uid" in session else redirect(url_for("login"))
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        return f(*a, **kw) if session.get("admin") else redirect(url_for("login"))
    return wrapper

# ─── Public / Auth routes ────────────────────────────────────────────────
@app.route("/")
def landing():
    return redirect(url_for("index"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u, e, p = (request.form[k].strip() for k in ("username", "email", "password"))
        if AuthUser.query.filter((AuthUser.username == u) | (AuthUser.email == e)).first():
            flash("Username or e‑mail already taken.", "danger")
            return redirect(url_for("register"))
        db.session.add(AuthUser(
            username=u, email=e,
            pw_hash=generate_password_hash(p),
            is_admin=(AuthUser.query.count() == 0)  # first user => admin
        ))
        db.session.commit()
        flash("Registered! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        user = AuthUser.query.filter((AuthUser.username == u) | (AuthUser.email == u)).first()
        if not user or not check_password_hash(user.pw_hash, p):
            flash("Invalid credentials.", "danger")
            return redirect(url_for("login"))
        session.update({"uid": user.id, "uname": user.username, "admin": user.is_admin})
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─── Password reset via e‑mail ───────────────────────────────────────────
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        mail_addr = request.form["email"].strip()
        user = AuthUser.query.filter_by(email=mail_addr).first()
        if user:
            token = secrets.token_urlsafe(48)
            user.reset_token = token
            db.session.commit()
            link = url_for("reset_password", token=token, _external=True)
            body = f"Hi {user.username},\n\nReset your password:\n{link}\n\nIf you didn’t ask, ignore this mail."
            mail.send(Message("Password reset", sender=app.config["MAIL_USERNAME"],
                              recipients=[mail_addr], body=body))
        flash("If that e‑mail exists, a reset link has been sent.", "info")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = AuthUser.query.filter_by(reset_token=token).first()
    if not user:
        flash("Invalid or expired link.", "danger")
        return redirect(url_for("login"))
    if request.method == "POST":
        pw1 = request.form["password"]
        pw2 = request.form["confirm_password"]
        if pw1 != pw2:
            flash("Passwords don’t match.", "warning")
            return redirect(request.url)
        user.pw_hash = generate_password_hash(pw1)
        user.reset_token = None
        db.session.commit()
        flash("Password reset — log in.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html")

# ─── Admin dashboard + utilities ─────────────────────────────────────────
@app.route("/admin")
@admin_required
def admin():
    logs = (db.session.query(DetectionLog, FaceUser)
            .join(FaceUser, DetectionLog.face_user_id == FaceUser.id)
            .order_by(DetectionLog.detected_at.desc())
            .limit(500).all())
    return render_template(
        "Admin.html",
        users=AuthUser.query.all(),
        face_users=FaceUser.query.all(),
        logs=logs,
        searched=False
    )

@app.route("/search_user")
@admin_required
def search_user():
    q = request.args.get("q", "").strip().lower()
    results = []
    if q:
        results = FaceUser.query.filter(
            (FaceUser.roll.ilike(f"%{q}%")) | (FaceUser.name.ilike(f"%{q}%"))
        ).all()
    logs = (db.session.query(DetectionLog, FaceUser)
            .join(FaceUser, DetectionLog.face_user_id == FaceUser.id)
            .order_by(DetectionLog.detected_at.desc())
            .limit(500).all())
    return render_template(
        "Admin.html",
        users=AuthUser.query.all(),
        face_users=FaceUser.query.all(),
        logs=logs,
        searched=True,
        results=results
    )

@app.route("/clear_logs", methods=["POST"])
@admin_required
def clear_logs():
    db.session.query(DetectionLog).delete()
    db.session.commit()
    flash("All detection logs cleared.", "info")
    return redirect(url_for("admin"))

@app.route("/delete_user/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    if user_id == session["uid"]:
        flash("You can’t delete yourself.", "warning")
    else:
        u = AuthUser.query.get(user_id)
        if u:
            db.session.delete(u)
            db.session.commit()
            flash("User deleted.", "info")
    return redirect(url_for("admin"))

# CSV export of per‑user detection summary
@app.route("/export_logs")
@admin_required
def export_logs():
    rows = FaceUser.query.order_by(FaceUser.roll).all()

    def first_detected(person):
        log = (DetectionLog.query.filter_by(face_user_id=person.id)
                                 .order_by(DetectionLog.detected_at.asc())
                                 .first())
        return log.detected_at if log else None

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["roll", "name", "total_detections",
         "last_detected_IST", "first_detected_IST"]
    )
    for p in rows:
        writer.writerow([
            p.roll,
            p.name,
            p.detections(),
            to_ist_str(p.last_detected()) if p.last_detected() else "",
            to_ist_str(first_detected(p))  if first_detected(p)  else ""
        ])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            f"attachment;filename=gate_access_logs_{datetime.utcnow():%Y%m%d_%H%M%S}.csv"
        }
    )

# ─── Face‑database CRUD ─────────────────────────────────────────────────
@app.route("/add_face", methods=["GET", "POST"])
@admin_required
def add_face():
    if request.method == "POST":
        name = request.form["name"].strip()
        roll = request.form["roll"].strip()
        file = request.files["image"]
        path = os.path.join(USER_IMG_DIR, f"{roll}.jpg")
        file.save(path)

        enc = face_recognition.face_encodings(face_recognition.load_image_file(path))
        if not enc:
            os.remove(path)
            flash("No face detected!", "warning")
            return redirect(url_for("add_face"))
        try:
            db.session.add(FaceUser(name=name, roll=roll, encoding=enc[0].tobytes()))
            db.session.commit()
            flash("Face added ✔", "success")
        except Exception:
            os.remove(path)
            flash("Roll already exists.", "danger")
        return redirect(url_for("add_face"))
    return render_template("add_user.html", users=FaceUser.query.all())

@app.route("/delete_face/<roll>", methods=["POST"])
@admin_required
def delete_face(roll):
    rec = FaceUser.query.filter_by(roll=roll).first()
    if rec:
        db.session.delete(rec)
        db.session.commit()
    img = os.path.join(USER_IMG_DIR, f"{roll}.jpg")
    if os.path.exists(img):
        os.remove(img)
    flash("Deleted.", "info")
    return redirect(url_for("add_face"))

# ─── Main page & recognition API ────────────────────────────────────────
@app.route("/index")
@login_required
def index():
    return render_template("index.html")

@app.route("/recognize", methods=["POST"])
@login_required
def recognize():
    frame = face_recognition.load_image_file(request.files["frame"])
    locs = face_recognition.face_locations(frame)
    encs = face_recognition.face_encodings(frame, locs)

    now = datetime.utcnow()
    rows = FaceUser.query.all()
    known = [np.frombuffer(r.encoding, dtype=np.float64) for r in rows]

    faces = []
    for (t, r, b, l), enc in zip(locs, encs):
        matches = face_recognition.compare_faces(known, enc, tolerance=0.45)
        tag   = "Unknown"
        count = None
        if True in matches:
            idx = matches.index(True)
            person = rows[idx]
            tag = f"{person.name} ({person.roll})"
            last = (DetectionLog.query.filter_by(face_user_id=person.id)
                       .order_by(DetectionLog.detected_at.desc()).first())
            if last is None or now - last.detected_at > timedelta(seconds=COOLDOWN_SECONDS):
                db.session.add(DetectionLog(face_user_id=person.id, detected_at=now))
                db.session.commit()
            count = person.detections()
        faces.append({"name": tag,
                      "top": t, "right": r, "bottom": b, "left": l,
                      "count": count})
    return jsonify(faces)

# ─── Entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
