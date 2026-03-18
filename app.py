from flask_cors import CORS
from flask import Flask, jsonify
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from models import db, User


db = SQLAlchemy()

app = Flask(__name__)
CORS(app, support_credentials = True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hr.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


login_manager=LoginManager()
login_manager.init_app(app)
@login_manager.user_loader
def load_user(user_id):
   return db.session.get(User, int(user_id))

with app.app_context():
   db.create_all()

@app.route("/health", methods = ['GET'])
def check():
    return jsonify({'message': 'Successfull running the application'})

if __name__ == '__main__':
    app.run(debug=True)