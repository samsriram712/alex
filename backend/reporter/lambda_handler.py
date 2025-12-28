"""
Report Writer Agent Lambda Handler
"""
print("========== IMPORT DIAGNOSTIC START ==========")

import os, sys

# Force src to be importable
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Alias src as database for legacy imports
import src
sys.modules["database"] = src
sys.modules["database.src"] = src

print("database in sys.modules?", "database" in sys.modules)

# sys.path.insert(0, os.getcwd())
print("PYTHONPATH:", os.environ.get("PYTHONPATH"))
print("SYS.PATH:")
for p in sys.path:
    print(" ", p)
print("CWD:", os.getcwd())

# print("\nListing /var/task:")
# print(os.listdir("/var/task"))

# if os.path.exists("/var/task/src"):
    # print("\n/src contents:")
    # print(os.listdir("/var/task/src"))
# else:
    # print("\n/src NOT FOUND")

import json
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from agents import Agent, Runner, trace
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from litellm.exceptions import RateLimitError, ServiceUnavailableError
from judge import evaluate

from producers.reporter_bridge import emit_reporter_facts

class AgentTemporaryError(Exception):
    """Temporary error that should trigger retry"""
    pass

GUARD_AGAINST_SCORE = 0.3  # Guard against score being too low

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

print("========== ABOUT TO IMPORT DATABASE ==========")

# Import database package
from src.models import Database

print("========== DATABASE IMPORT SUCCEEDED ==========")

from templates import REPORTER_INSTRUCTIONS

print("========== REPORTER_INSTRUCTIONS IMPORT SUCCEEDED ==========")

from agent import create_agent, ReporterContext

print("========== AGENT IMPORT SUCCEEDED ==========")

from observability import observe

print("========== ALL IMPORTS SUCCEEDED ==========")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

print("========== LOGGER INITIALISED ==========")

# @retry(
    # retry=retry_if_exception_type((RateLimitError, AgentTemporaryError, TimeoutError, asyncio.TimeoutError)),
    # stop=stop_after_attempt(5),
    # wait=wait_exponential(multiplier=1, min=4, max=60),
    # before_sleep=lambda retry_state: logger.info(
        # f"Reporter: Temporary error, retrying in {retry_state.next_action.sleep} seconds..."
    # ),
# )

# async def persist_portfolio_actions(
    # user_id: str,
    # job_id: str,
    # portfolio_response: dict
# ):
    # from common.action_deriver import derive_portfolio_actions
    # from common.alert_store import AlertStore
    # from common.todo_store import TodoStore

    # alerts, todos = derive_portfolio_actions(
        # user_id=user_id,
        # job_id=job_id,
        # portfolio_report=portfolio_response
    # )

    # AlertStore().insert_bulk(alerts)
    # TodoStore().insert_bulk(todos)

@retry(
    # OUTER retry: Bedrock capacity issues (slow + patient)
    retry=retry_if_exception_type((
        ServiceUnavailableError,
        RateLimitError,
    )),
    stop=stop_after_attempt(4),
    wait=wait_exponential(
        multiplier=2,   # slower than Researcher
        min=10,
        max=120,
    ),
    before_sleep=lambda retry_state: logger.warning(
        f"Reporter: Bedrock capacity issue, retrying in "
        f"{retry_state.next_action.sleep}s "
        f"(attempt {retry_state.attempt_number})"
    ),
)
@retry(
    # INNER retry: timeouts (fast + limited)
    retry=retry_if_exception_type((
        TimeoutError,
        asyncio.TimeoutError,
    )),
    stop=stop_after_attempt(2),
    wait=wait_exponential(
        multiplier=1,
        min=2,
        max=30,
    ),
    before_sleep=lambda retry_state: logger.warning(
        f"Reporter: Timeout, retrying in "
        f"{retry_state.next_action.sleep}s "
        f"(attempt {retry_state.attempt_number})"
    ),
)

async def run_reporter_agent(
    job_id: str,
    user_id:str,
    portfolio_data: Dict[str, Any],
    user_data: Dict[str, Any],
    db=None,
    observability=None,
) -> Dict[str, Any]:
    """Run the reporter agent to generate analysis."""

    # Create agent with tools and context
    model, tools, task, context = create_agent(job_id, portfolio_data, user_data, db)

    # Run agent with context
    with trace("Reporter Agent"):
        agent = Agent[ReporterContext](  # Specify the context type
            name="Report Writer", instructions=REPORTER_INSTRUCTIONS, model=model, tools=tools
        )

        try:
            result = await Runner.run(
                agent,
                input=task,
                context=context,  # Pass the context
                max_turns=20,
            )

            response = result.final_output
        except ServiceUnavailableError as e:
            logger.warning(f"Reporter Bedrock capacity error: {e}")
            raise  # handled by outer retry

        except RateLimitError as e:
            logger.warning(f"Reporter Bedrock rate limit: {e}")
            raise  # handled by outer retry

        except (TimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Reporter timeout (will use timeout retry): {e}")
            raise  # handled by inner retry

        except Exception:
            raise  # fail fast for all other errors


        

        if observability:
            try:
                with observability.start_as_current_span(name="judge") as span:
                    evaluation = await evaluate(REPORTER_INSTRUCTIONS, task, response)
                    score = evaluation.score / 100
                    comment = evaluation.feedback

                    # Record telemetry safely
                    try:
                        span.score(name="Judge", value=score, data_type="NUMERIC", comment=comment)
                        observation = f"Score: {score} - Feedback: {comment}"
                        observability.create_event(name="Judge Event", status_message=observation)
                        
                    except AttributeError as otel_error:
                        logger.warning(f"Telemetry scoring failed: {otel_error}")

                    # Business guard logic (keep this!)
                    if score < GUARD_AGAINST_SCORE:
                        logger.error(f"Reporter score is too low: {score}")
                        response = "I'm sorry, I'm not able to generate a report for you. Please try again later."

            except Exception as e:
                logger.warning(f"Observability or evaluation failed: {e}")


        # Save the report to database
        report_payload = {
            "content": response,
            "generated_at": datetime.utcnow().isoformat(),
            "agent": "reporter",
        }

        success = db.jobs.update_report(job_id, report_payload)

        if not success:
            logger.error(f"Failed to save report for job {job_id}")

        # try:
            # await persist_portfolio_actions(
            # user_id=user_id,
            # job_id=job_id,
            # portfolio_response=response
            # )
        # except Exception as e:
            # logger.exception("Failed to persist portfolio actions")

        await emit_reporter_facts(
            user_id=user_id,
            job_id=job_id,
            portfolio_report=response
        )

        return {
            "success": success,
            "message": "Report generated and stored"
            if success
            else "Report generated but failed to save",
            "final_output": result.final_output,
        }


def lambda_handler(event, context):
    """
    Lambda handler expecting job_id, portfolio_data, and user_data in event.

    Expected event:
    {
        "job_id": "uuid",
        "portfolio_data": {...},
        "user_data": {...}
    }
    """
    # Wrap entire handler with observability context
    with observe() as observability:
        try:
            logger.info(f"Reporter Lambda invoked with event: {json.dumps(event)[:500]}")

            # Parse event
            if isinstance(event, str):
                event = json.loads(event)

            job_id = event.get("job_id")
            if not job_id:
                return {"statusCode": 400, "body": json.dumps({"error": "job_id is required"})}

            # Initialize database
            db = Database()

            db.jobs.set_agent_status(job_id, "reporter", "running")

            portfolio_data = event.get("portfolio_data")
            if not portfolio_data:
                # Try to load from database
                try:
                    job = db.jobs.find_by_id(job_id)
                    if job:
                        user_id = job["clerk_user_id"]

                        if observability:
                            observability.create_event(
                                name="Reporter Started!", status_message="OK"
                            )
                        user = db.users.find_by_clerk_id(user_id)
                        accounts = db.accounts.find_by_user(user_id)

                        portfolio_data = {"user_id": user_id, "job_id": job_id, "accounts": []}

                        for account in accounts:
                            positions = db.positions.find_by_account(account["id"])
                            account_data = {
                                "id": account["id"],
                                "name": account["account_name"],
                                "type": account.get("account_type", "investment"),
                                "cash_balance": float(account.get("cash_balance", 0)),
                                "positions": [],
                            }

                            for position in positions:
                                instrument = db.instruments.find_by_symbol(position["symbol"])
                                if instrument:
                                    account_data["positions"].append(
                                        {
                                            "symbol": position["symbol"],
                                            "quantity": float(position["quantity"]),
                                            "instrument": instrument,
                                        }
                                    )

                            portfolio_data["accounts"].append(account_data)
                    else:
                        return {
                            "statusCode": 404,
                            "body": json.dumps({"error": f"Job {job_id} not found"}),
                        }
                except Exception as e:
                    logger.error(f"Could not load portfolio from database: {e}")
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"error": "No portfolio data provided"}),
                    }

            user_data = event.get("user_data", {})
            if not user_data:
                # Try to load from database
                try:
                    job = db.jobs.find_by_id(job_id)
                    if job and job.get("clerk_user_id"):
                        status = f"Job ID: {job_id} Clerk User ID: {job['clerk_user_id']}"
                        if observability:
                            observability.create_event(
                                name="Reporter about to run", status_message=status
                            )
                        user = db.users.find_by_clerk_id(job["clerk_user_id"])
                        if user:
                            user_data = {
                                "years_until_retirement": user.get("years_until_retirement", 30),
                                "target_retirement_income": float(
                                    user.get("target_retirement_income", 80000)
                                ),
                            }
                        else:
                            user_data = {
                                "years_until_retirement": 30,
                                "target_retirement_income": 80000,
                            }
                except Exception as e:
                    logger.warning(f"Could not load user data: {e}. Using defaults.")
                    user_data = {"years_until_retirement": 30, "target_retirement_income": 80000}

            # Run the agent
            result = asyncio.run(
                run_reporter_agent(job_id, user_id, portfolio_data, user_data, db, observability)
            )

            logger.info(f"Reporter completed for job {job_id}")

            db.jobs.set_agent_status(job_id, "reporter", "completed")
            db.jobs.set_agent_completed_at(job_id, "reporter")

            if db.jobs.are_all_agents_completed(job_id):
                db.jobs.update_status(job_id, "completed")

            return {"statusCode": 200, "body": json.dumps(result)}

        except Exception as e:
            logger.error(f"Error in reporter: {e}", exc_info=True)
            try:
                if job_id:
                    db.jobs.set_agent_status(job_id, "reporter", "failed")
                    db.jobs.update_status(job_id, "failed", error_message=str(e))
            except Exception:
                pass
            return {"statusCode": 500, "body": json.dumps({"success": False, "error": str(e)})}


# For local testing
if __name__ == "__main__":
    test_event = {
        "job_id": "550e8400-e29b-41d4-a716-446655440002",
        "portfolio_data": {
            "accounts": [
                {
                    "name": "401(k)",
                    "cash_balance": 5000,
                    "positions": [
                        {
                            "symbol": "SPY",
                            "quantity": 100,
                            "instrument": {
                                "name": "SPDR S&P 500 ETF",
                                "current_price": 450,
                                "asset_class": "equity",
                            },
                        }
                    ],
                }
            ]
        },
        "user_data": {"years_until_retirement": 25, "target_retirement_income": 75000},
    }

    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
