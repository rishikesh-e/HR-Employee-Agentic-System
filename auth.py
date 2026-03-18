from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required

from models import db, User, LeaveType, LeaveBalance

auth_bp = Blueprint("auth", __name__)

def assign_default_leaves(user):
    leave_types = LeaveType.query.all()

    for lt in leave_types:
        db.session.add(LeaveBalance(
            user_id=user.id,
            leave_type_id=lt.id,
            total_leaves=lt.default_days,
            used_leaves=0
        ))

    db.session.commit()

@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.json or request.form

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "employee")

    if not name or not email or not password:
        return jsonify({"error": "Missing fields"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists"}), 400

    user = User(
        name=name,
        email=email,
        password=generate_password_hash(password),
        role=role
    )

    db.session.add(user)
    db.session.commit()

    assign_default_leaves(user)

    return jsonify({"message": "User created successfully"}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json or request.form

    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid credentials"}), 401

    login_user(user)

    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user.id,
            "role": user.role
        }
    })

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out"})