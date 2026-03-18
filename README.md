# 🤖 HR Agentic AI System

An intelligent HR Leave Management System powered by **Groq LLM** that autonomously handles HR queries using natural language. The agent understands employee requests, decides which operations to perform, and returns responses based on actual database data.

## ✨ Features

- **Natural Language Interface** — Ask questions in plain English
- **Autonomous Decision Making** — The agent picks the right API/tool to call
- **Role-Based Access Control** — Employees and Admins have different permissions
- **Smart Date Handling** — Excludes weekends and company holidays from leave calculations
- **No Hallucination** — All responses come from actual database queries
- **Function Calling** — Uses Groq LLM's tool-use capability for structured interactions

## 🏗️ Architecture

```
User Query (Natural Language)
        │
        ▼
  POST /agent/chat  ─────►  HRAgent.process_query()
                                    │
                            ┌───────┴───────┐
                            │   Groq LLM    │
                            │ (tool-calling) │
                            └───────┬───────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              apply_leave    get_balances    approve_leave  ...
                    │               │               │
                    └───────────────┼───────────────┘
                                    │
                            ┌───────┴───────┐
                            │   SQLAlchemy   │
                            │   (SQLite DB)  │
                            └───────────────┘
```

## 📋 Prerequisites

- Python 3.10+
- [Groq API Key](https://console.groq.com/keys)

## 🚀 Setup

```bash
# 1. Clone and enter the project
cd HR-AGENTIC-AI-SYSTEM

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install flask flask-sqlalchemy flask-login flask-bcrypt flask-cors
pip install groq python-dotenv

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# 5. Run the application
python app.py
```

## 🗂️ Project Structure

```
HR-AGENTIC-AI-SYSTEM/
├── app.py              # Flask app entry point
├── models.py           # SQLAlchemy data models
├── auth.py             # Authentication (signup/login/logout)
├── employee.py         # REST API endpoints for leave management
├── decorators.py       # Role-based access decorators
├── hr.py               # Agentic blueprint (/agent/chat endpoint)
├── hr_agent.py         # 🤖 Core agent (HRAgent + tool functions)
├── demo.py             # Demo script with example queries
├── test_agent.py       # Integration tests
├── .env.example        # Environment variable template
└── README.md           # This file
```

## 🔧 Data Models

| Model | Description |
|-------|-------------|
| `User` | Employees and admins with role-based access |
| `LeaveType` | Leave categories: SICK (10 days), CASUAL (8), EARNED (15) |
| `LeaveBalance` | Per-user leave balance tracking |
| `LeaveRequest` | Leave applications with status (PENDING/APPROVED/REJECTED) |
| `Holiday` | Company holidays excluded from working day calculations |

## 🤖 Agent Tools

| Tool | Who Can Use | Description |
|------|------------|-------------|
| `apply_leave` | Employee, Admin | Apply for leave |
| `get_leave_balances` | Employee (own), Admin (any) | Check leave balances |
| `get_my_leave_requests` | Employee | View own leave requests |
| `get_all_leave_requests`| Admin only | View all leave requests |
| `approve_or_reject_leave` | Admin only | Approve/reject pending requests |
| `get_holidays` | Everyone | List company holidays |
| `add_holiday` | Admin only | Add a new holiday |

## 💬 Usage

### Agentic Chat Endpoint

```bash
# Employee: Check balance
curl -X POST http://localhost:5000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is my leave balance?",
    "user_id": 1,
    "role": "employee"
  }'

# Employee: Apply for leave
curl -X POST http://localhost:5000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "I need sick leave from March 23 to March 27 for a medical appointment",
    "user_id": 1,
    "role": "employee"
  }'

# Admin: View pending requests
curl -X POST http://localhost:5000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me all pending leave requests",
    "user_id": 2,
    "role": "admin"
  }'

# Admin: Approve leave
curl -X POST http://localhost:5000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Approve leave request #1",
    "user_id": 2,
    "role": "admin"
  }'
```

### Response Format

```json
{
  "success": true,
  "response": "Your sick leave request has been submitted...",
  "tool_calls_made": [
    {
      "tool": "apply_leave",
      "arguments": { "leave_type": "SICK", "start_date": "2026-03-23", ... },
      "result": { "success": true, "working_days": 5, ... }
    }
  ]
}
```

### Run the Demo

```bash
source venv/bin/activate
python demo.py
```

## 🧪 Testing

```bash
source venv/bin/activate
pytest test_agent.py -v
```

## 📝 REST API Endpoints

These traditional endpoints are also available (require Flask session auth):

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/signup` | — | Create new user |
| POST | `/login` | — | Login |
| POST | `/logout` | User | Logout |
| POST | `/apply-leave` | User | Apply for leave |
| GET | `/leave-balances` | User | Get own leave balances |
| GET | `/leave-requests` | Admin | View all leave requests |
| POST | `/approve-leave/<id>` | Admin | Approve/reject leave |
| GET | `/holidays` | User | List holidays |
| POST | `/agent/chat` | — | 🤖 Agentic chat endpoint |
