"""
HR Agentic System — Flask Blueprint

Provides the /agent/chat endpoint that accepts natural language queries
and routes them through the HRAgent.
"""

from flask import Blueprint, request, jsonify
from models import db, User
from hr_agent import HRAgent

hr_bp = Blueprint("hr", __name__, url_prefix="/agent")


@hr_bp.route("/chat", methods=["POST"])
def agent_chat():
    """
    Agentic HR chat endpoint.

    Accepts:
        {
            "query": "I want to apply for sick leave ...",
            "user_id": 1,
            "role": "employee"
        }

    Returns:
        {
            "success": true/false,
            "response": "...",
            "tool_calls_made": [...]
        }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    query = data.get("query")
    user_id = data.get("user_id")
    role = data.get("role")

    # --- Validation ---
    if not query:
        return jsonify({"error": "query is required"}), 400

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    if not role:
        return jsonify({"error": "role is required"}), 400

    if role not in ["admin", "employee"]:
        return jsonify({"error": "role must be 'admin' or 'employee'"}), 400

    # --- Verify user exists and role matches ---
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": f"User with ID {user_id} not found"}), 404

    if user.role != role:
        return jsonify({
            "error": f"Role mismatch. User {user_id} has role '{user.role}', not '{role}'"
        }), 403

    # --- Process query through the agent ---
    agent = HRAgent(user_id=user_id, user_role=role)
    result = agent.process_query(query)

    status_code = 200 if result.get("success") else 500
    return jsonify(result), status_code


@hr_bp.route("/voice-chat", methods=["POST"])
def agent_voice_chat():
    """
    Endpoint for voice-based HR queries.
    Expects multipart/form-data with 'audio', 'user_id', and 'role'.
    """
    import os
    import tempfile

    user_id = request.form.get("user_id")
    role = request.form.get("role")
    audio_file = request.files.get("audio")

    if not all([user_id, role, audio_file]):
        return jsonify({"error": "user_id, role, and audio file are required"}), 400

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user_id"}), 400

    # Verification
    user = db.session.get(User, user_id)
    if not user or user.role != role:
        return jsonify({"error": "Authentication failed or role mismatch"}), 403

    # Process audio
    agent = HRAgent(user_id=user_id, user_role=role)
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
        audio_file.save(temp_audio.name)
        temp_path = temp_audio.name

    try:
        # 1. Translate audio to English
        transcribed_text = agent.translate_audio(temp_path)
        
        # 2. Process query
        result = agent.process_query(transcribed_text)
        
        # Add the transcribed text to the response so frontend can show it
        result["transcribed_query"] = transcribed_text
        
        return jsonify(result), 200 if result.get("success") else 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
