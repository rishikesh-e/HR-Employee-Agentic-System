from flask import Flask
from flask_login import LoginManager
from models import db, User
from auth import auth_bp
from flask_login import login_required
from decorators import role_required

app = Flask(__name__)

app.config['SECRET_KEY'] = 'supersecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hr.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

app.register_blueprint(auth_bp)

with app.app_context():
    db.create_all()

@app.route("/admin-only")
@login_required
@role_required("admin")
def admin_route():
    return {"message": "Welcome Admin"}

@app.route("/employee-only")
@login_required
@role_required("employee")
def employee_route():
    return {"message": "Welcome Employee"}

if __name__ == "__main__":
    app.run(debug=True)