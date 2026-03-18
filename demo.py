import os
import json
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from app import app
from models import db, User, LeaveType, LeaveBalance, Holiday, LeaveRequest
from werkzeug.security import generate_password_hash
from hr_agent import HRAgent


def seed_database():
    if User.query.filter_by(email="john@company.com").first():
        print("Database already seeded. Skipping...\n")
        return

    print("=" * 60)
    print("SEEDING DATABASE")
    print("=" * 60)

    employee = User(
        name="John Doe",
        email="john@company.com",
        password=generate_password_hash("password123"),
        role="employee"
    )
    admin = User(
        name="HR Admin",
        email="admin@company.com",
        password=generate_password_hash("admin123"),
        role="admin"
    )

    db.session.add_all([employee, admin])
    db.session.commit()
    print(f"  ✓ Created employee: {employee.name} (ID: {employee.id})")
    print(f"  ✓ Created admin:    {admin.name} (ID: {admin.id})")

    leave_types = LeaveType.query.all()
    for user in [employee, admin]:
        for lt in leave_types:
            db.session.add(LeaveBalance(
                user_id=user.id,
                leave_type_id=lt.id,
                total_leaves=lt.default_days,
                used_leaves=0
            ))
    db.session.commit()
    print("  ✓ Assigned default leave balances to all users")

    holidays = [
        Holiday(name="Republic Day", date=date(2026, 1, 26), description="National holiday"),
        Holiday(name="Holi", date=date(2026, 3, 10), description="Festival of Colors"),
        Holiday(name="Good Friday", date=date(2026, 4, 3), description="Christian holiday"),
        Holiday(name="Independence Day", date=date(2026, 8, 15), description="National holiday"),
        Holiday(name="Gandhi Jayanti", date=date(2026, 10, 2), description="National holiday"),
        Holiday(name="Diwali", date=date(2026, 11, 8), description="Festival of Lights"),
        Holiday(name="Christmas", date=date(2026, 12, 25), description="Christian holiday"),
    ]
    db.session.add_all(holidays)
    db.session.commit()
    print(f"  ✓ Added {len(holidays)} holidays for 2026")
    print()


def run_agent_query(user_id: int, role: str, query: str):
    """Run a query through the HR Agent and display results."""
    print(f"{'─' * 60}")
    print(f"  User: ID={user_id}, Role={role}")
    print(f"  Query: \"{query}\"")
    print(f"{'─' * 60}")

    agent = HRAgent(user_id=user_id, user_role=role)
    result = agent.process_query(query)

    print(f"\n  ✅ Success: {result['success']}")
    print(f"\n  🤖 Agent Response:")
    print(f"  {result['response']}")

    if result['tool_calls_made']:
        print(f"\n  🔧 Tool Calls Made ({len(result['tool_calls_made'])}):")
        for i, tc in enumerate(result['tool_calls_made'], 1):
            print(f"     {i}. {tc['tool']}({json.dumps(tc['arguments'], indent=2)})")
            print(f"        → Result: {json.dumps(tc['result'], indent=2)[:200]}...")
    print()


def main():
    if not os.getenv("GROQ_API_KEY"):
        print("❌ ERROR: GROQ_API_KEY not found in environment.")
        print("   Create a .env file with: GROQ_API_KEY=your_key_here")
        print("   Get a key from: https://console.groq.com/keys")
        return

    with app.app_context():
        seed_database()

        print("=" * 60)
        print("DEMO: EMPLOYEE QUERIES")
        print("=" * 60)

        # Employee — Check leave balance
        print("\n📋 Example 1: Employee checks leave balance")
        run_agent_query(
            user_id=1,
            role="employee",
            query="What is my current leave balance?"
        )

        # Employee — Apply for leave
        print("\n📋 Example 2: Employee applies for sick leave")
        run_agent_query(
            user_id=1,
            role="employee",
            query="I need to apply for sick leave from March 23 to March 27, 2026. I have a medical appointment."
        )

        # Employee — Check leave requests
        print("\n📋 Example 3: Employee checks leave requests")
        run_agent_query(
            user_id=1,
            role="employee",
            query="Show me my leave requests"
        )

        print("\n" + "=" * 60)
        print("DEMO: ADMIN QUERIES")
        print("=" * 60)

        # Admin — View all pending requests
        print("\n📋 Example 4: Admin views pending requests")
        run_agent_query(
            user_id=2,
            role="admin",
            query="Show me all pending leave requests"
        )

        # Admin — Approve leave
        print("\n📋 Example 5: Admin approves leave request #1")
        run_agent_query(
            user_id=2,
            role="admin",
            query="Please approve the leave request with ID 1"
        )

        # Admin — View holidays
        print("\n📋 Example 6: Admin checks company holidays")
        run_agent_query(
            user_id=2,
            role="admin",
            query="What are the upcoming company holidays?"
        )

        print("\n" + "=" * 60)
        print("DEMO COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()
