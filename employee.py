from datetime import timedelta, datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models import db, User, LeaveType, LeaveBalance, Holiday, LeaveRequest
from decorators import role_required


employee_bp = Blueprint("employee", __name__)


def calculate_working_days(start_date, end_date, holidays):
    total = 0
    current = start_date

    holiday_dates = {h.date for h in holidays}

    while current <= end_date:
        if current.weekday() not in [5, 6] and current not in holiday_dates:
            total += 1
        current += timedelta(days=1)

    return total


@employee_bp.route("/apply-leave", methods=["POST"])
@login_required
def apply_leave():
    data = request.get_json()

    # 1. Get the leave type name from JSON (e.g., "SICK")
    leave_type_name = data.get("leave_type")
    if not leave_type_name:
        return jsonify({"error": "leave_type name is required"}), 400

    # 2. Find the LeaveType record from the database
    leave_type_record = LeaveType.query.filter_by(name=leave_type_name.upper()).first()
    if not leave_type_record:
        return jsonify({"error": f"Leave type '{leave_type_name}' not found"}), 404

    # 3. Parse Dates
    try:
        start_date = datetime.strptime(data.get("start_date"), "%Y-%m-%d").date()
        end_date = datetime.strptime(data.get("end_date"), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    if start_date > end_date:
        return jsonify({"error": "start_date must be before end_date"}), 400

    # 4. Calculate working days (excluding weekends + holidays)
    holidays = Holiday.query.all()
    total_days = calculate_working_days(start_date, end_date, holidays)

    if total_days == 0:
        return jsonify({"error": "No working days in the selected date range"}), 400

    # 5. Create the leave request
    leave_request = LeaveRequest(
        user_id=current_user.id,
        leave_type_id=leave_type_record.id,
        start_date=start_date,
        end_date=end_date,
        days=total_days,
        reason=data.get("reason"),
        status="PENDING"
    )

    db.session.add(leave_request)
    db.session.commit()

    return jsonify({
        "message": "Leave request submitted successfully.",
        "leave_type": leave_type_record.name,
        "leave_type_id": leave_type_record.id,
        "days_applied": total_days
    }), 201


@employee_bp.route("/leave-balances", methods=["GET"])
@login_required
def get_leave_balances():
    balances = LeaveBalance.query.filter_by(user_id=current_user.id).all()

    result = []
    for b in balances:
        result.append({
            "leave_type": b.leave_type.name,
            "total": b.total_leaves,
            "used": b.used_leaves,
            "remaining": b.total_leaves - b.used_leaves
        })

    return jsonify({
        "user_id": current_user.id,
        "leave_balances": result
    })


@employee_bp.route("/approve-leave/<int:leave_id>", methods=["POST"])
@login_required
@role_required("admin")
def approve_leave(leave_id):
    data = request.get_json() or {}
    action = data.get("action", "approve").upper()

    if action not in ["APPROVE", "REJECT"]:
        return jsonify({"error": "action must be 'approve' or 'reject'"}), 400

    # 1. Fetch the leave request
    leave = LeaveRequest.query.get(leave_id)
    if not leave:
        return jsonify({"error": "Leave request not found"}), 404

    if leave.status != "PENDING":
        return jsonify({"error": f"Leave request already {leave.status}"}), 400

    # 2. Get the leave type name
    lt_record = LeaveType.query.get(leave.leave_type_id)
    leave_name = lt_record.name if lt_record else "Unknown"

    if action == "REJECT":
        leave.status = "REJECTED"
        db.session.commit()
        return jsonify({
            "message": "Leave request rejected",
            "leave_id": leave.id,
            "leave_type": leave_name,
            "status": "REJECTED"
        })

    # 3. For approval, check balance
    balance = LeaveBalance.query.filter_by(
        user_id=leave.user_id,
        leave_type_id=leave.leave_type_id
    ).first()

    if not balance:
        return jsonify({"error": "Leave balance record not found"}), 404

    remaining = balance.total_leaves - balance.used_leaves
    if remaining < leave.days:
        leave.status = "REJECTED"
        db.session.commit()
        return jsonify({"error": "Insufficient leave balance. Request rejected.", "remaining": remaining}), 400

    # 4. Approve and deduct balance
    balance.used_leaves += leave.days
    leave.status = "APPROVED"
    db.session.commit()

    return jsonify({
        "message": "Leave approved successfully",
        "leave_id": leave.id,
        "leave_type": leave_name,
        "days_deducted": leave.days,
        "remaining_balance": balance.total_leaves - balance.used_leaves
    })


@employee_bp.route("/leave-requests", methods=["GET"])
@login_required
@role_required("admin")
def get_leave_requests():
    status_filter = request.args.get("status")

    query = LeaveRequest.query
    if status_filter:
        query = query.filter_by(status=status_filter.upper())

    leaves = query.all()

    result = []
    for l in leaves:
        user = User.query.get(l.user_id)
        leave_type = LeaveType.query.get(l.leave_type_id)

        result.append({
            "leave_id": l.id,
            "employee": {
                "id": user.id,
                "name": user.name,
                "email": user.email
            },
            "leave_type": leave_type.name if leave_type else None,
            "start_date": str(l.start_date),
            "end_date": str(l.end_date),
            "days": l.days,
            "reason": l.reason,
            "status": l.status
        })

    return jsonify({
        "count": len(result),
        "leave_requests": result
    })


@employee_bp.route("/holidays", methods=["GET"])
@login_required
def get_holidays():
    holidays = Holiday.query.order_by(Holiday.date).all()

    result = []
    for h in holidays:
        result.append({
            "id": h.id,
            "name": h.name,
            "date": str(h.date),
            "description": h.description
        })

    return jsonify({
        "count": len(result),
        "holidays": result
    })