"""
HR Agentic System — Core Agent Module

This module implements the HRAgent class that uses Groq LLM with function-calling
to autonomously handle HR queries. The agent:
1. Receives a natural language query + user context (id, role)
2. Sends it to Groq LLM with tool definitions
3. Executes tool calls against the actual database
4. Returns the LLM's structured response based on real data
"""

import os
import json
import logging
from datetime import datetime, timedelta

from groq import Groq
from models import db, User, LeaveType, LeaveBalance, LeaveRequest, Holiday

logger = logging.getLogger(__name__)

# ============================================================================
# SYSTEM PROMPT — instructs the LLM on its role and constraints
# ============================================================================

SYSTEM_PROMPT = """You are an intelligent HR Assistant for the company's Leave Management System.

Your role is to help employees and admins manage leave requests, check balances, and handle holidays.

## STRICT RULES:
1. **NEVER fabricate or hallucinate data.** Only use information returned by tool calls.
2. **Always call the appropriate tool** to get data before answering.
3. **Respect the user's role:**
   - Employees can: apply for leave, check their own leave balances, view their own leave requests, view holidays.
   - Admins can: do everything employees can, PLUS approve/reject leave requests, view ALL leave requests, add holidays, and view any employee's leave balance.
4. **For leave applications**, extract: leave_type (SICK, CASUAL, or EARNED), start_date, end_date, and reason from the query.
5. **Format dates as YYYY-MM-DD** when calling tools.
6. **Today's date is {today}**. Use this as reference when users say "tomorrow", "next week", etc.
7. **Be concise and professional** in your responses.
8. When presenting leave balances or requests, format them in a clear, readable way.
9. If the user's query is ambiguous, ask for clarification instead of guessing.

## CRITICAL ANTI-HALLUCINATION INSTRUCTIONS:
- You ONLY have access to the specific HR tools provided. 
- You DO NOT have access to web search, brave_search, internet browsers, or general knowledge tools.
- If the user asks ANY question not directly related to leave management or holidays (e.g., general knowledge, opinions, trivia, weather), you MUST NOT attempt to call any tools. You must immediately state: "I am an internal HR assistant and can only help with leave requests, leave balances, and company holidays."
"""

# ============================================================================
# TOOL DEFINITIONS — JSON schema for Groq function-calling
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "apply_leave",
            "description": "Apply for a leave request on behalf of the current employee. Only employees can use this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "leave_type": {
                        "type": "string",
                        "enum": ["SICK", "CASUAL", "EARNED"],
                        "description": "Type of leave to apply for"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date of leave in YYYY-MM-DD format"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date of leave in YYYY-MM-DD format"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for applying for leave"
                    }
                },
                "required": ["leave_type", "start_date", "end_date", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_leave_balances",
            "description": "Get leave balances for the current user (employee sees own, admin can query any employee by providing employee_id).",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "The employee ID to check balances for. Admins can query any employee. Output 'self' to check your own balances."
                    }
                },
                "required": ["employee_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_leave_requests",
            "description": "Get all leave requests across the company. ONLY admins can use this tool. Can filter by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Filter leave requests by status (PENDING, APPROVED, REJECTED, or ALL)."
                    }
                },
                "required": ["status_filter"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_leave_requests",
            "description": "Get leave requests submitted by the current employee. Employees use this to see their own requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Filter leave requests by status (PENDING, APPROVED, REJECTED, or ALL)."
                    }
                },
                "required": ["status_filter"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "approve_or_reject_leave",
            "description": "Approve or reject a leave request. Only admins can use this. Approving deducts from employee's leave balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "leave_id": {
                        "type": "string",
                        "description": "The ID of the leave request to approve or reject"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["APPROVE", "REJECT"],
                        "description": "Whether to approve or reject the leave request"
                    }
                },
                "required": ["leave_id", "action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_holidays",
            "description": "Get the list of all company holidays.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_holiday",
            "description": "Add a new company holiday. Only admins can use this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the holiday (e.g., 'Diwali', 'Christmas')"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date of the holiday in YYYY-MM-DD format"
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description of the holiday"
                    }
                },
                "required": ["name", "date"]
            }
        }
    }
]

# ============================================================================
# TOOL IMPLEMENTATION FUNCTIONS — Direct DB access via SQLAlchemy
# ============================================================================


def _calculate_working_days(start_date, end_date):
    """Calculate working days between two dates, excluding weekends and holidays."""
    holiday_dates = {h.date for h in Holiday.query.all()}
    total = 0
    current = start_date
    while current <= end_date:
        if current.weekday() not in [5, 6] and current not in holiday_dates:
            total += 1
        current += timedelta(days=1)
    return total


def tool_apply_leave(user_id: int, user_role: str, leave_type: str,
                     start_date: str, end_date: str, reason: str) -> dict:
    """Apply for leave — only employees (or admins applying for themselves)."""
    try:
        # Validate leave type
        lt_record = LeaveType.query.filter_by(name=leave_type.upper()).first()
        if not lt_record:
            return {"error": f"Invalid leave type '{leave_type}'. Valid types: SICK, CASUAL, EARNED"}

        # Parse dates
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}

        if s_date > e_date:
            return {"error": "start_date must be before or equal to end_date"}

        # Calculate working days
        total_days = _calculate_working_days(s_date, e_date)
        if total_days == 0:
            return {"error": "No working days in the selected date range (all weekends/holidays)"}

        # Check balance before applying
        balance = LeaveBalance.query.filter_by(
            user_id=user_id,
            leave_type_id=lt_record.id
        ).first()

        if not balance:
            return {"error": "Leave balance record not found for this user"}

        remaining = balance.total_leaves - balance.used_leaves
        if remaining < total_days:
            return {
                "error": f"Insufficient {leave_type} leave balance. "
                         f"Requested: {total_days} days, Available: {remaining} days"
            }

        leave_request = LeaveRequest(
            user_id=user_id,
            leave_type_id=lt_record.id,
            start_date=s_date,
            end_date=e_date,
            days=total_days,
            reason=reason,
            status="PENDING"
        )

        db.session.add(leave_request)
        db.session.commit()

        return {
            "success": True,
            "message": "Leave request submitted successfully",
            "leave_id": leave_request.id,
            "leave_type": lt_record.name,
            "start_date": start_date,
            "end_date": end_date,
            "working_days": total_days,
            "reason": reason,
            "status": "PENDING",
            "remaining_balance_after_approval": remaining - total_days
        }

    except Exception as e:
        logger.error(f"Error applying leave: {e}")
        return {"error": f"Failed to apply leave: {str(e)}"}


def tool_get_leave_balances(user_id: int, user_role: str,
                            employee_id: str = "self") -> dict:
    """Get leave balances. Employees see own; admins can query any user."""
    try:
        target_id = user_id

        if employee_id is not None and str(employee_id).lower() != "self":
            if user_role != "admin":
                return {"error": "Access denied. Only admins can view other employees' balances."}
            try:
                target_id = int(employee_id)
            except (ValueError, TypeError):
                return {"error": "Invalid employee ID"}


            target_user = db.session.get(User, target_id)
            if not target_user:
                return {"error": f"Employee with ID {target_id} not found"}

        balances = LeaveBalance.query.filter_by(user_id=target_id).all()

        target_user = db.session.get(User, target_id)
        result = {
            "employee_id": target_id,
            "employee_name": target_user.name if target_user else "Unknown",
            "leave_balances": []
        }

        for b in balances:
            result["leave_balances"].append({
                "leave_type": b.leave_type.name,
                "total_leaves": b.total_leaves,
                "used_leaves": b.used_leaves,
                "remaining_leaves": b.total_leaves - b.used_leaves
            })

        return result

    except Exception as e:
        logger.error(f"Error getting leave balances: {e}")
        return {"error": f"Failed to get leave balances: {str(e)}"}


def tool_get_all_leave_requests(user_id: int, user_role: str,
                                status_filter: str = None) -> dict:
    try:
        if user_role != "admin":
            return {"error": "Access denied. Only admins can view all leave requests."}

        query = LeaveRequest.query

        if status_filter and status_filter.upper() != "ALL":
            query = query.filter_by(status=status_filter.upper())

        leaves = query.all()

        result = []
        for l in leaves:
            user = db.session.get(User, l.user_id)
            leave_type = db.session.get(LeaveType, l.leave_type_id)

            result.append({
                "leave_id": l.id,
                "employee_id": l.user_id,
                "employee_name": user.name if user else "Unknown",
                "leave_type": leave_type.name if leave_type else "Unknown",
                "start_date": str(l.start_date),
                "end_date": str(l.end_date),
                "days": l.days,
                "reason": l.reason,
                "status": l.status
            })

        return {
            "count": len(result),
            "leave_requests": result
        }

    except Exception as e:
        logger.error(f"Error getting all leave requests: {e}")
        return {"error": f"Failed to get all leave requests: {str(e)}"}


def tool_get_my_leave_requests(user_id: int, user_role: str,
                               status_filter: str = None) -> dict:
    try:
        query = LeaveRequest.query.filter_by(user_id=user_id)

        if status_filter and status_filter.upper() != "ALL":
            query = query.filter_by(status=status_filter.upper())

        leaves = query.all()

        result = []
        for l in leaves:
            leave_type = db.session.get(LeaveType, l.leave_type_id)
            
            result.append({
                "leave_id": l.id,
                "leave_type": leave_type.name if leave_type else "Unknown",
                "start_date": str(l.start_date),
                "end_date": str(l.end_date),
                "days": l.days,
                "reason": l.reason,
                "status": l.status
            })

        return {
            "count": len(result),
            "leave_requests": result
        }

    except Exception as e:
        logger.error(f"Error getting my leave requests: {e}")
        return {"error": f"Failed to get my leave requests: {str(e)}"}


def tool_approve_or_reject_leave(user_id: int, user_role: str,
                                  leave_id: str, action: str) -> dict:
    """Approve or reject a leave request — admin only."""
    try:
        # Role check
        if user_role != "admin":
            return {"error": "Access denied. Only admins can approve or reject leave requests."}

        try:
            leave_id_int = int(leave_id)
        except (ValueError, TypeError):
            return {"error": "Invalid leave ID format"}

        leave = db.session.get(LeaveRequest, leave_id_int)
        if not leave:
            return {"error": f"Leave request with ID {leave_id} not found"}

        if leave.status != "PENDING":
            return {"error": f"Leave request is already {leave.status}. Only PENDING requests can be processed."}

        lt_record = db.session.get(LeaveType, leave.leave_type_id)
        leave_name = lt_record.name if lt_record else "Unknown"

        employee = db.session.get(User, leave.user_id)
        employee_name = employee.name if employee else "Unknown"

        if action.upper() == "REJECT":
            leave.status = "REJECTED"
            db.session.commit()
            return {
                "success": True,
                "message": f"Leave request #{leave_id} has been rejected",
                "leave_id": leave.id,
                "employee_name": employee_name,
                "leave_type": leave_name,
                "days": leave.days,
                "status": "REJECTED"
            }

        # Approve — check balance first
        balance = LeaveBalance.query.filter_by(
            user_id=leave.user_id,
            leave_type_id=leave.leave_type_id
        ).first()

        if not balance:
            return {"error": "Leave balance record not found for this employee"}

        remaining = balance.total_leaves - balance.used_leaves
        if remaining < leave.days:
            leave.status = "REJECTED"
            db.session.commit()
            return {
                "error": f"Insufficient balance. Requested: {leave.days} days, "
                         f"Available: {remaining} days. Request auto-rejected."
            }

        # Deduct balance and approve
        balance.used_leaves += leave.days
        leave.status = "APPROVED"
        db.session.commit()

        return {
            "success": True,
            "message": f"Leave request #{leave_id} has been approved",
            "leave_id": leave.id,
            "employee_name": employee_name,
            "leave_type": leave_name,
            "days_deducted": leave.days,
            "remaining_balance": balance.total_leaves - balance.used_leaves,
            "status": "APPROVED"
        }

    except Exception as e:
        logger.error(f"Error processing leave request: {e}")
        return {"error": f"Failed to process leave request: {str(e)}"}


def tool_get_holidays(user_id: int, user_role: str) -> dict:
    """Get all company holidays."""
    try:
        holidays = Holiday.query.order_by(Holiday.date).all()

        result = []
        for h in holidays:
            result.append({
                "id": h.id,
                "name": h.name,
                "date": str(h.date),
                "description": h.description
            })

        return {
            "count": len(result),
            "holidays": result
        }

    except Exception as e:
        logger.error(f"Error getting holidays: {e}")
        return {"error": f"Failed to get holidays: {str(e)}"}


def tool_add_holiday(user_id: int, user_role: str,
                     name: str, date: str, description: str = None) -> dict:
    try:
        if user_role != "admin":
            return {"error": "Access denied. Only admins can add holidays."}

        try:
            h_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}

        # Check for duplicate date
        existing = Holiday.query.filter_by(date=h_date).first()
        if existing:
            return {"error": f"A holiday already exists on {date}: {existing.name}"}

        holiday = Holiday(
            name=name,
            date=h_date,
            description=description or ""
        )

        db.session.add(holiday)
        db.session.commit()

        return {
            "success": True,
            "message": f"Holiday '{name}' added successfully",
            "holiday_id": holiday.id,
            "name": name,
            "date": date,
            "description": description or ""
        }

    except Exception as e:
        logger.error(f"Error adding holiday: {e}")
        return {"error": f"Failed to add holiday: {str(e)}"}


TOOL_DISPATCH = {
    "apply_leave": tool_apply_leave,
    "get_leave_balances": tool_get_leave_balances,
    "get_all_leave_requests": tool_get_all_leave_requests,
    "get_my_leave_requests": tool_get_my_leave_requests,
    "approve_or_reject_leave": tool_approve_or_reject_leave,
    "get_holidays": tool_get_holidays,
    "add_holiday": tool_add_holiday,
}


class HRAgent:
    def __init__(self, user_id: int, user_role: str):
        self.user_id = user_id
        self.user_role = user_role
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.max_iterations = 5  # prevent infinite loops

    def translate_audio(self, audio_file_path: str) -> str:
        """Translate/Transcribe audio file to English text using Groq Whisper."""
        try:
            with open(audio_file_path, "rb") as file:
                translation = self.client.audio.translations.create(
                    file=(os.path.basename(audio_file_path), file.read()),
                    model="whisper-large-v3",
                    response_format="json"
                )
                return translation.text
        except Exception as e:
            logger.error(f"Audio translation error: {e}")
            raise Exception(f"Failed to transcribe audio: {str(e)}")

    def process_query(self, query: str) -> dict:
        today = datetime.now().strftime("%Y-%m-%d (%A)")
        system_msg = SYSTEM_PROMPT.format(today=today)

        # Add user context to the system prompt
        user = User.query.get(self.user_id)
        user_name = user.name if user else "Unknown"
        system_msg += f"\n\nCurrent user: {user_name} (ID: {self.user_id}, Role: {self.user_role})"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": query}
        ]

        tool_calls_made = []

        try:
            for iteration in range(self.max_iterations):
                logger.info(f"Agent iteration {iteration + 1}")

                # Call Groq LLM
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.0,
                    max_tokens=1024,
                    parallel_tool_calls=False
                )

                msg = response.choices[0].message

                # If no tool calls, the LLM is done — return its response
                if not msg.tool_calls:
                    return {
                        "success": True,
                        "response": msg.content,
                        "tool_calls_made": tool_calls_made
                    }

                # Process tool calls
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                })

                for tool_call in msg.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                        if not isinstance(func_args, dict):
                            func_args = {}
                    except (json.JSONDecodeError, TypeError):
                        func_args = {}

                    logger.info(f"Tool call: {func_name}({func_args})")

                    # Execute the tool
                    result = self._execute_tool(func_name, func_args)

                    tool_calls_made.append({
                        "tool": func_name,
                        "arguments": func_args,
                        "result": result
                    })

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })

            # If we exhausted iterations
            return {
                "success": False,
                "response": "I apologize, but I wasn't able to complete your request. Please try rephrasing your query.",
                "tool_calls_made": tool_calls_made
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Agent error: {error_msg}")
            
            # Catch known Groq issue where Llama 3 hallucinates "brave_search" or other search tools 
            # for general queries instead of just answering from context
            if "tool call validation failed" in error_msg or "attempted to call tool" in error_msg:
                return {
                    "success": True,  # Return 200 to frontend so the chat displays gracefully
                    "response": "I am an internal HR assistant and do not have access to external search. Please let me know how I can help you with your HR needs!",
                    "tool_calls_made": tool_calls_made
                }

            return {
                "success": False,
                "response": f"An error occurred while processing your request: {error_msg}",
                "tool_calls_made": tool_calls_made
            }

    def _execute_tool(self, func_name: str, func_args: dict) -> dict:
        """Execute a tool function with role enforcement."""
        tool_func = TOOL_DISPATCH.get(func_name)

        if not tool_func:
            return {"error": f"Unknown tool: {func_name}"}

        # Inject user_id and role into every tool call
        return tool_func(
            user_id=self.user_id,
            user_role=self.user_role,
            **func_args
        )
