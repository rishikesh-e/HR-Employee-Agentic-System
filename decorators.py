from flask_login import current_user
from flask import jsonify
from functools import wraps

def role_required(role):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Unauthorized"}), 401

            if current_user.role != role:
                return jsonify({"error": "Forbidden"}), 403

            return fn(*args, **kwargs)
        return decorated
    return wrapper