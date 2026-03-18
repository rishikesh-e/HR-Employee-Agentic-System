from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin / employee


class LeaveType(db.Model):
    __tablename__ = "leave_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    default_days = db.Column(db.Integer, nullable=False)


class LeaveBalance(db.Model):
    __tablename__ = "leave_balances"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"))

    total_leaves = db.Column(db.Integer)
    used_leaves = db.Column(db.Integer, default=0)

    leave_type = db.relationship("LeaveType")


class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    leave_type_id = db.Column(db.Integer, db.ForeignKey('leave_types.id'))
    
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    
    days = db.Column(db.Integer)
    
    status = db.Column(db.String(20), default="PENDING")  # PENDING, APPROVED, REJECTED
    
    reason = db.Column(db.String(255))

class Holiday(db.Model):
    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)

    description = db.Column(db.String(255))