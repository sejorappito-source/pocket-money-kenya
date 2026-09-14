#!/usr/bin/env python3
"""
Pocket Money Manager for Kenyan Teachers
- Free & Open Source
- Automatic matching of M-Pesa SMS (via phone forwarder) to students via parent phone numbers
- Supports multiple parents per student
- Highlights unallocated money
"""

import os
import re
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify
)
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production-kenya-teachers-2026")

# SQLite in /tmp works on Render free tier (note: data is wiped on redeploy)
_default_db = os.path.join("/tmp", "pocket_money.db")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{_default_db}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# -----------------------------
# Models
# -----------------------------
class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    class_name = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parents = db.relationship(
        "Parent",
        secondary="student_parents",
        back_populates="students",
        lazy="joined",
    )
    transactions = db.relationship("Transaction", back_populates="student", lazy="dynamic")


class Parent(db.Model):
    __tablename__ = "parents"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    students = db.relationship(
        "Student",
        secondary="student_parents",
        back_populates="parents",
        lazy="joined",
    )


class StudentParent(db.Model):
    __tablename__ = "student_parents"
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("parents.id"), primary_key=True)


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    mpesa_code = db.Column(db.String(20), unique=True, index=True)
    amount = db.Column(db.Float, nullable=False)
    sender_phone = db.Column(db.String(20), index=True)
    sender_name = db.Column(db.String(120))
    raw_sms = db.Column(db.Text)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="unallocated", index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    notes = db.Column(db.Text)

    student = db.relationship("Student", back_populates="transactions")


# -----------------------------
# Helpers
# -----------------------------
def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    phone = re.sub(r"[^\d+]", "", phone)
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if phone.startswith("7") and len(phone) == 9:
        phone = "254" + phone
    if phone.startswith("254") and len(phone) == 12:
        return phone
    return phone


def parse_mpesa_sms(sms: str):
    if not sms:
        return None

    sms = sms.strip()

    code_match = re.search(r"^([A-Z0-9]{10})\s+Confirmed", sms, re.I)
    if not code_match:
        code_match = re.search(r"\b([A-Z0-9]{10})\b", sms)
    code = code_match.group(1).upper() if code_match else None

    amount_match = re.search(r"(?:received|Ksh|KES)\s*K?sh?\.?\s*([\d,]+\.?\d*)", sms, re.I)
    if not amount_match:
        amount_match = re.search(r"Ksh\s*([\d,]+\.?\d*)", sms, re.I)
    if not amount_match:
        return None
    amount_str = amount_match.group(1).replace(",", "")
    try:
        amount = float(amount_str)
    except ValueError:
        return None

    sender_match = re.search(
        r"from\s+([A-Z\s\.\'-]+?)\s+(\+?0?7[\d\*]{8,9}|\d{9,12}|\d{3}\*{3}\d{3})",
        sms,
        re.I,
    )
    sender_name = None
    sender_phone = None
    if sender_match:
        sender_name = sender_match.group(1).strip().title()
        sender_phone = sender_match.group(2).strip()

    if not sender_phone:
        phone_match = re.search(r"(0?7[\d\*]{8,9})", sms)
        if phone_match:
            sender_phone = phone_match.group(1)

    return {
        "mpesa_code": code,
        "amount": amount,
        "sender_name": sender_name,
        "sender_phone": sender_phone,
        "raw_sms": sms,
    }


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# -----------------------------
# Auth
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        expected = os.environ.get("APP_PASSWORD", "teacher123")
        if password == expected:
            session["logged_in"] = True
            flash("Logged in successfully", "success")
            return redirect(url_for("dashboard"))
        flash("Wrong password", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------
# Dashboard & Transactions
# -----------------------------
@app.route("/")
@login_required
def dashboard():
    unallocated = (
        Transaction.query.filter_by(status="unallocated")
        .order_by(Transaction.received_at.desc())
        .limit(50)
        .all()
    )
    recent = (
        Transaction.query.order_by(Transaction.received_at.desc()).limit(20).all()
    )
    stats = {
        "total_students": Student.query.count(),
        "total_parents": Parent.query.count(),
        "unallocated_count": Transaction.query.filter_by(status="unallocated").count(),
        "allocated_today": Transaction.query.filter(
            Transaction.status == "allocated",
            Transaction.received_at >= datetime.utcnow().replace(hour=0, minute=0, second=0),
        ).count(),
    }
    return render_template(
        "dashboard.html",
        unallocated=unallocated,
        recent=recent,
        stats=stats,
    )


@app.route("/transactions")
@login_required
def transactions():
    status = request.args.get("status", "all")
    q = Transaction.query
    if status == "unallocated":
        q = q.filter_by(status="unallocated")
    elif status == "allocated":
        q = q.filter(Transaction.status.in_(["allocated", "manual"]))
    txns = q.order_by(Transaction.received_at.desc()).limit(200).all()
    students = Student.query.order_by(Student.full_name).all()
    return render_template("transactions.html", transactions=txns, students=students, status=status)


@app.route("/transactions/<int:txn_id>/allocate", methods=["POST"])
@login_required
def allocate_transaction(txn_id):
    txn = Transaction.query.get_or_404(txn_id)
    student_id = request.form.get("student_id")
    if student_id:
        txn.student_id = int(student_id)
        txn.status = "manual"
        db.session.commit()
        flash(f"Allocated Ksh {txn.amount:,.0f} to student", "success")
    return redirect(url_for("transactions", status="unallocated"))


# -----------------------------
# Students
# -----------------------------
@app.route("/students")
@login_required
def students():
    all_students = Student.query.order_by(Student.full_name).all()
    return render_template("students.html", students=all_students)


@app.route("/students/add", methods=["GET", "POST"])
@login_required
def add_student():
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip().upper()
        full_name = request.form.get("full_name", "").strip()
        class_name = request.form.get("class_name", "").strip()
        notes = request.form.get("notes", "").strip()
        if not student_id or not full_name:
            flash("Student ID and Full Name are required", "danger")
            return redirect(url_for("add_student"))
        if Student.query.filter_by(student_id=student_id).first():
            flash("Student ID already exists", "danger")
            return redirect(url_for("add_student"))
        s = Student(student_id=student_id, full_name=full_name, class_name=class_name, notes=notes)
        db.session.add(s)
        db.session.commit()
        flash(f"Student {full_name} added", "success")
        return redirect(url_for("students"))
    return render_template("student_form.html", student=None)


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def edit_student(sid):
    student = Student.query.get_or_404(sid)
    if request.method == "POST":
        student.student_id = request.form.get("student_id", "").strip().upper()
        student.full_name = request.form.get("full_name", "").strip()
        student.class_name = request.form.get("class_name", "").strip()
        student.notes = request.form.get("notes", "").strip()
        db.session.commit()
        flash("Student updated", "success")
        return redirect(url_for("students"))
    return render_template("student_form.html", student=student)


@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required
def delete_student(sid):
    student = Student.query.get_or_404(sid)
    db.session.delete(student)
    db.session.commit()
    flash("Student deleted", "success")
    return redirect(url_for("students"))


# -----------------------------
# Parents
# -----------------------------
@app.route("/parents")
@login_required
def parents():
    all_parents = Parent.query.order_by(Parent.full_name).all()
    return render_template("parents.html", parents=all_parents)


@app.route("/parents/add", methods=["GET", "POST"])
@login_required
def add_parent():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone_raw = request.form.get("phone", "").strip()
        notes = request.form.get("notes", "").strip()
        student_ids = request.form.getlist("student_ids")

        phone = normalize_phone(phone_raw)
        if not full_name or not phone:
            flash("Name and phone are required", "danger")
            return redirect(url_for("add_parent"))

        if Parent.query.filter_by(phone=phone).first():
            flash("This phone number is already registered", "danger")
            return redirect(url_for("add_parent"))

        p = Parent(full_name=full_name, phone=phone, notes=notes)
        db.session.add(p)
        db.session.flush()

        for sid in student_ids:
            s = Student.query.get(int(sid))
            if s:
                p.students.append(s)
        db.session.commit()
        flash(f"Parent {full_name} added and linked", "success")
        return redirect(url_for("parents"))

    students = Student.query.order_by(Student.full_name).all()
    return render_template("parent_form.html", parent=None, students=students)


@app.route("/parents/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def edit_parent(pid):
    parent = Parent.query.get_or_404(pid)
    if request.method == "POST":
        parent.full_name = request.form.get("full_name", "").strip()
        phone_raw = request.form.get("phone", "").strip()
        parent.phone = normalize_phone(phone_raw)
        parent.notes = request.form.get("notes", "").strip()

        selected = set(int(x) for x in request.form.getlist("student_ids"))
        current = {s.id for s in parent.students}
        for s in list(parent.students):
            if s.id not in selected:
                parent.students.remove(s)
        for sid in selected - current:
            s = Student.query.get(sid)
            if s:
                parent.students.append(s)

        db.session.commit()
        flash("Parent updated", "success")
        return redirect(url_for("parents"))

    students = Student.query.order_by(Student.full_name).all()
    return render_template("parent_form.html", parent=parent, students=students)


@app.route("/parents/<int:pid>/delete", methods=["POST"])
@login_required
def delete_parent(pid):
    parent = Parent.query.get_or_404(pid)
    db.session.delete(parent)
    db.session.commit()
    flash("Parent deleted", "success")
    return redirect(url_for("parents"))


# -----------------------------
# Webhook – SMS from Android forwarder
# -----------------------------
@app.route("/webhook/sms", methods=["POST"])
def webhook_sms():
    data = {}
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict() or {}

    sms_text = (
        data.get("message")
        or data.get("text")
        or data.get("sms")
        or data.get("body")
        or data.get("content")
        or request.get_data(as_text=True)
    )

    if not sms_text or len(sms_text) < 20:
        return jsonify({"ok": False, "error": "No valid SMS body"}), 400

    if "you have received" not in sms_text.lower() and "confirmed" not in sms_text.lower():
        return jsonify({"ok": True, "ignored": "Not a received M-Pesa SMS"}), 200

    parsed = parse_mpesa_sms(sms_text)
    if not parsed or not parsed.get("amount"):
        return jsonify({"ok": False, "error": "Could not parse M-Pesa SMS"}), 400

    if parsed.get("mpesa_code"):
        existing = Transaction.query.filter_by(mpesa_code=parsed["mpesa_code"]).first()
        if existing:
            return jsonify({"ok": True, "message": "Already processed", "id": existing.id}), 200

    raw_phone = parsed.get("sender_phone") or ""
    norm_phone = normalize_phone(raw_phone)

    parent = Parent.query.filter_by(phone=norm_phone).first()

    if not parent and "*" in raw_phone:
        prefix = raw_phone[:4].replace("0", "254") if raw_phone.startswith("0") else raw_phone[:5]
        suffix = raw_phone[-3:]
        candidates = Parent.query.filter(Parent.phone.like(f"{prefix}%{suffix}")).all()
        if len(candidates) == 1:
            parent = candidates[0]

    student = None
    status = "unallocated"

    if parent and parent.students:
        if len(parent.students) == 1:
            student = parent.students[0]
            status = "allocated"
        else:
            status = "unallocated"

    txn = Transaction(
        mpesa_code=parsed.get("mpesa_code"),
        amount=parsed["amount"],
        sender_phone=raw_phone or norm_phone,
        sender_name=parsed.get("sender_name"),
        raw_sms=sms_text,
        status=status,
        student_id=student.id if student else None,
        received_at=datetime.utcnow(),
    )
    db.session.add(txn)
    db.session.commit()

    return jsonify({
        "ok": True,
        "id": txn.id,
        "status": status,
        "amount": txn.amount,
        "student": student.full_name if student else None,
    }), 200


# -----------------------------
# Create tables on startup (required for Gunicorn / Render)
# -----------------------------
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
