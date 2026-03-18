import pytest
from datetime import date
from werkzeug.security import generate_password_hash

from app import app, db
from models import User, LeaveType, LeaveBalance, LeaveRequest, Holiday
from hr_agent import (
    tool_apply_leave,
    tool_get_leave_balances,
    tool_get_all_leave_requests,
    tool_get_my_leave_requests,
    tool_approve_or_reject_leave,
    tool_get_holidays,
    tool_add_holiday,
    _calculate_working_days,
)

def _seed_test_data():
    lt_sick = LeaveType(name="SICK", default_days=10)
    lt_casual = LeaveType(name="CASUAL", default_days=8)
    lt_earned = LeaveType(name="EARNED", default_days=15)
    db.session.add_all([lt_sick, lt_casual, lt_earned])
    db.session.commit()

    employee = User(
        name="Test Employee",
        email="employee@test.com",
        password=generate_password_hash("pass"),
        role="employee"
    )
    admin = User(
        name="Test Admin",
        email="admin@test.com",
        password=generate_password_hash("pass"),
        role="admin"
    )
    db.session.add_all([employee, admin])
    db.session.commit()

    for user in [employee, admin]:
        for lt in [lt_sick, lt_casual, lt_earned]:
            db.session.add(LeaveBalance(
                user_id=user.id,
                leave_type_id=lt.id,
                total_leaves=lt.default_days,
                used_leaves=0
            ))
    db.session.commit()

    db.session.add_all([
        Holiday(name="Test Holiday 1", date=date(2026, 3, 10), description="Test"),
        Holiday(name="Test Holiday 2", date=date(2026, 8, 15), description="Test"),
    ])
    db.session.commit()


@pytest.fixture(autouse=True)
def setup_db():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.engine.dispose()
        db.drop_all()
        db.create_all()
        _seed_test_data()
        yield
        db.session.remove()
        db.drop_all()


# ============================================================================
# WORKING DAYS CALCULATION
# ============================================================================

class TestWorkingDays:
    def test_weekdays_only(self):
        # Mon Mar 16 to Fri Mar 20 = 5 working days
        result = _calculate_working_days(date(2026, 3, 16), date(2026, 3, 20))
        assert result == 5

    def test_include_weekend(self):
        # Mon Mar 16 to Mon Mar 23 = 6 weekdays (skip Sat+Sun)
        result = _calculate_working_days(date(2026, 3, 16), date(2026, 3, 23))
        assert result == 6

    def test_exclude_holidays(self):
        # Mon Mar 9 to Fri Mar 13, but Mar 10 is a holiday → 4 days
        result = _calculate_working_days(date(2026, 3, 9), date(2026, 3, 13))
        assert result == 4

    def test_single_day(self):
        result = _calculate_working_days(date(2026, 3, 16), date(2026, 3, 16))
        assert result == 1

    def test_weekend_only(self):
        # Saturday
        result = _calculate_working_days(date(2026, 3, 14), date(2026, 3, 14))
        assert result == 0


# ============================================================================
# APPLY LEAVE
# ============================================================================

class TestApplyLeave:
    def test_valid_application(self):
        result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="SICK",
            start_date="2026-03-23",
            end_date="2026-03-27",
            reason="Medical checkup"
        )
        assert result.get("success") is True
        assert result["working_days"] == 5
        assert result["status"] == "PENDING"

    def test_invalid_leave_type(self):
        result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="INVALID",
            start_date="2026-03-23",
            end_date="2026-03-25",
            reason="Test"
        )
        assert "error" in result

    def test_invalid_date_format(self):
        result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="SICK",
            start_date="23-03-2026",
            end_date="25-03-2026",
            reason="Test"
        )
        assert "error" in result

    def test_start_after_end(self):
        result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="SICK",
            start_date="2026-03-27",
            end_date="2026-03-23",
            reason="Test"
        )
        assert "error" in result

    def test_insufficient_balance(self):
        result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="SICK",
            start_date="2026-04-01",
            end_date="2026-04-30",
            reason="Long leave"
        )
        assert "error" in result
        assert "Insufficient" in result["error"]


# ============================================================================
# LEAVE BALANCES
# ============================================================================

class TestLeaveBalances:
    def test_get_own_balances(self):
        result = tool_get_leave_balances(user_id=1, user_role="employee")
        assert "leave_balances" in result
        assert len(result["leave_balances"]) == 3

    def test_admin_views_employee_balance(self):
        result = tool_get_leave_balances(user_id=2, user_role="admin", employee_id=1)
        assert "leave_balances" in result
        assert result["employee_id"] == 1

    def test_employee_cannot_view_others(self):
        result = tool_get_leave_balances(user_id=1, user_role="employee", employee_id=2)
        assert "error" in result
        assert "Access denied" in result["error"]

    def test_nonexistent_employee(self):
        result = tool_get_leave_balances(user_id=2, user_role="admin", employee_id=999)
        assert "error" in result


# ============================================================================
# LEAVE REQUESTS
# ============================================================================

class TestLeaveRequests:
    def test_employee_sees_own_requests(self):
        tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="CASUAL",
            start_date="2026-04-06",
            end_date="2026-04-07",
            reason="Personal"
        )
        result = tool_get_my_leave_requests(user_id=1, user_role="employee")
        assert result["count"] >= 1
        for req in result["leave_requests"]:
            # In get_my_leave_requests, employee_id isn't returned, we just check existence
            assert "leave_id" in req

    def test_admin_sees_all_requests(self):
        tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="SICK",
            start_date="2026-04-06",
            end_date="2026-04-07",
            reason="Test"
        )
        result = tool_get_all_leave_requests(user_id=2, user_role="admin")
        assert result["count"] >= 1

    def test_filter_by_status(self):
        tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="CASUAL",
            start_date="2026-05-04",
            end_date="2026-05-05",
            reason="Filter test"
        )
        result = tool_get_all_leave_requests(
            user_id=2, user_role="admin",
            status_filter="PENDING"
        )
        for req in result["leave_requests"]:
            assert req["status"] == "PENDING"


# ============================================================================
# APPROVE / REJECT LEAVE
# ============================================================================

class TestApproveReject:
    def test_admin_approves(self):
        apply_result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="SICK",
            start_date="2026-06-01",
            end_date="2026-06-03",
            reason="Sick"
        )
        leave_id = apply_result["leave_id"]

        result = tool_approve_or_reject_leave(
            user_id=2, user_role="admin",
            leave_id=leave_id, action="APPROVE"
        )
        assert result.get("success") is True
        assert result["status"] == "APPROVED"
        assert result["days_deducted"] == apply_result["working_days"]

    def test_admin_rejects(self):
        apply_result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="CASUAL",
            start_date="2026-06-08",
            end_date="2026-06-09",
            reason="Need off"
        )
        leave_id = apply_result["leave_id"]

        result = tool_approve_or_reject_leave(
            user_id=2, user_role="admin",
            leave_id=leave_id, action="REJECT"
        )
        assert result.get("success") is True
        assert result["status"] == "REJECTED"

    def test_employee_cannot_approve(self):
        apply_result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="EARNED",
            start_date="2026-07-06",
            end_date="2026-07-07",
            reason="Test"
        )
        leave_id = apply_result["leave_id"]

        result = tool_approve_or_reject_leave(
            user_id=1, user_role="employee",
            leave_id=leave_id, action="APPROVE"
        )
        assert "error" in result
        assert "Access denied" in result["error"]

    def test_nonexistent_leave(self):
        result = tool_approve_or_reject_leave(
            user_id=2, user_role="admin",
            leave_id=9999, action="APPROVE"
        )
        assert "error" in result

    def test_already_approved(self):
        apply_result = tool_apply_leave(
            user_id=1, user_role="employee",
            leave_type="SICK",
            start_date="2026-09-07",
            end_date="2026-09-08",
            reason="Test"
        )
        leave_id = apply_result["leave_id"]

        # Approve once
        tool_approve_or_reject_leave(
            user_id=2, user_role="admin",
            leave_id=leave_id, action="APPROVE"
        )

        # Try approving again
        result = tool_approve_or_reject_leave(
            user_id=2, user_role="admin",
            leave_id=leave_id, action="APPROVE"
        )
        assert "error" in result
        assert "already" in result["error"].lower()


# ============================================================================
# HOLIDAYS
# ============================================================================

class TestHolidays:
    def test_get_holidays(self):
        result = tool_get_holidays(user_id=1, user_role="employee")
        assert result["count"] == 2

    def test_admin_adds_holiday(self):
        result = tool_add_holiday(
            user_id=2, user_role="admin",
            name="New Year",
            date="2027-01-01",
            description="Happy New Year"
        )
        assert result.get("success") is True

        holidays = tool_get_holidays(user_id=1, user_role="employee")
        assert holidays["count"] == 3

    def test_employee_cannot_add_holiday(self):
        result = tool_add_holiday(
            user_id=1, user_role="employee",
            name="My Holiday",
            date="2026-12-31"
        )
        assert "error" in result
        assert "Access denied" in result["error"]

    def test_duplicate_holiday_date(self):
        result = tool_add_holiday(
            user_id=2, user_role="admin",
            name="Duplicate",
            date="2026-03-10"
        )
        assert "error" in result
        assert "already exists" in result["error"]


# ============================================================================
# AGENT CHAT ENDPOINT — validation only (no LLM call)
# ============================================================================

class TestAgentEndpoint:
    def test_missing_query(self):
        with app.test_client() as client:
            resp = client.post("/agent/chat", json={"user_id": 1, "role": "employee"})
            assert resp.status_code == 400

    def test_missing_user_id(self):
        with app.test_client() as client:
            resp = client.post("/agent/chat", json={"query": "test", "role": "employee"})
            assert resp.status_code == 400

    def test_invalid_role(self):
        with app.test_client() as client:
            resp = client.post("/agent/chat", json={
                "query": "test", "user_id": 1, "role": "superadmin"
            })
            assert resp.status_code == 400

    def test_nonexistent_user(self):
        with app.test_client() as client:
            resp = client.post("/agent/chat", json={
                "query": "test", "user_id": 999, "role": "employee"
            })
            assert resp.status_code == 404

    def test_role_mismatch(self):
        with app.test_client() as client:
            resp = client.post("/agent/chat", json={
                "query": "test", "user_id": 1, "role": "admin"
            })
            assert resp.status_code == 403
