import os
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import LoginManager
from models import db, User, LeaveType

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hr.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)

from auth import auth_bp
from employee import employee_bp
from hr import hr_bp

app.register_blueprint(auth_bp)
app.register_blueprint(employee_bp)
app.register_blueprint(hr_bp)

@app.route("/")
def index():
    return render_template("index.html")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def seed_leave_types():
    if LeaveType.query.count() > 0:
        return

    types = [
        LeaveType(name="SICK", default_days=10),
        LeaveType(name="CASUAL", default_days=8),
        LeaveType(name="EARNED", default_days=15)
    ]

    db.session.add_all(types)
    db.session.commit()


def init_db():
    """Initialize the database and seed default data."""
    with app.app_context():
        db.create_all()
        seed_leave_types()


# Only auto-init when not being imported for testing
if not app.config.get("TESTING") and not os.getenv("TESTING"):
    init_db()


if __name__ == "__main__":
    app.run(debug=True)