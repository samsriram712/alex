"""
Retirement Specialist Agent Lambda Handler
"""

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
import json
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from agents import Agent, Runner, trace
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from litellm.exceptions import RateLimitError

from producers.retirement_bridge import emit_retirement_facts


class AgentTemporaryError(Exception):
    """Temporary error that should trigger retry"""
    pass

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

# Import database package
from src import Database

from templates import RETIREMENT_INSTRUCTIONS
from agent import create_agent
from observability import observe

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_user_preferences(job_id: str) -> Dict[str, Any]:
    """Load user preferences from database."""
    try:
        db = Database()
        
        # Get the job to find the user
        job = db.jobs.find_by_id(job_id)
        if job and job.get('clerk_user_id'):
            # Get user preferences
            user = db.users.find_by_clerk_id(job['clerk_user_id'])
            if user:
                return {
                    'years_until_retirement': user.get('years_until_retirement', 30),
                    'target_retirement_income': float(user.get('target_retirement_income', 80000)),
                    'current_age': 40  # Default for now
                }
    except Exception as e:
        logger.warning(f"Could not load user data: {e}. Using defaults.")
    
    return {
        'years_until_retirement': 30,
        'target_retirement_income': 80000.0,
        'current_age': 40
    }

@retry(
    retry=retry_if_exception_type((RateLimitError, AgentTemporaryError, TimeoutError, asyncio.TimeoutError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    before_sleep=lambda retry_state: logger.info(f"Retirement: Temporary error, retrying in {retry_state.next_action.sleep} seconds...")
)

# async def persist_retirement_actions(
    # user_id: str,
    # job_id: str,
    # retirement_response: dict
# ):
    # from common.action_deriver import derive_retirement_actions
    # from common.alert_store import AlertStore
    # from common.todo_store import TodoStore

    # alerts, todos = derive_retirement_actions(
        # user_id=user_id,
        # job_id=job_id,
        # retirement_report=retirement_response
    # )

    # AlertStore().insert_bulk(alerts)
    # TodoStore().insert_bulk(todos)

async def run_retirement_agent(job_id: str, user_id: str, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run the retirement specialist agent."""
    
    # Get user preferences
    user_preferences = get_user_preferences(job_id)
    
    # Initialize database
    db = Database()
    
    # Create agent (simplified - no tools or context)
    model, tools, task = create_agent(job_id, portfolio_data, user_preferences, db)
    
    # Run agent (simplified - no context)
    with trace("Retirement Agent"):
        agent = Agent(
            name="Retirement Specialist",
            instructions=RETIREMENT_INSTRUCTIONS,
            model=model,
            tools=tools  # Empty list now
        )
        
        try:
            result = await Runner.run(
                agent,
                input=task,
                max_turns=20
            )
        except (TimeoutError, asyncio.TimeoutError) as e:
            logger.warning(f"Retirement agent timeout: {e}")
            raise AgentTemporaryError(f"Timeout during agent execution: {e}")
        except Exception as e:
            error_str = str(e).lower()
            if "timeout" in error_str or "throttled" in error_str:
                logger.warning(f"Retirement temporary error: {e}")
                raise AgentTemporaryError(f"Temporary error: {e}")
            raise  # Re-raise non-retryable errors
        
        # Save the analysis to database
        retirement_payload = {
            'analysis': result.final_output,
            'generated_at': datetime.utcnow().isoformat(),
            'agent': 'retirement'
        }
        
        success = db.jobs.update_retirement(job_id, retirement_payload)
        
        if not success:
            logger.error(f"Failed to save retirement analysis for job {job_id}")

        # try:
            # wait persist_retirement_actions(
            # user_id=user_id,
            # job_id=job_id,
            # retirement_response=result.final_output
            # )
        # except Exception as e:
            # logger.exception("Failed to persist retirement actions")

        await emit_retirement_facts(
            user_id=user_id,
            job_id=job_id,
            retirement_report=result.final_output
        )

        
        return {
            'success': success,
            'message': 'Retirement analysis completed' if success else 'Analysis completed but failed to save',
            'final_output': result.final_output
        }

def lambda_handler(event, context):
    """
    Lambda handler expecting job_id in event.

    Expected event:
    {
        "job_id": "uuid",
        "portfolio_data": {...}  # Optional, will load from DB if not provided
    }
    """
    # Wrap entire handler with observability context
    with observe() as observability:
        try:
            logger.info(f"Retirement Lambda invoked with event: {json.dumps(event)[:500]}")

            # Parse event
            if isinstance(event, str):
                event = json.loads(event)

            logger.info(f"[TRACE] portfolio_data exists in event: {'portfolio_data' in event}")
            logger.info(f"[TRACE] portfolio_data type: {type(event.get('portfolio_data'))}")
            logger.info(f"[TRACE] portfolio_data value: {str(event.get('portfolio_data'))[:300]}")


            job_id = event.get('job_id')
            if not job_id:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'job_id is required'})
                }

            portfolio_data = event.get('portfolio_data')
            if not portfolio_data or not portfolio_data.get("accounts"):
                # Try to load from database
                logger.info("[TRACE] ENTERING DB LOAD BLOCK")
                logger.info(f"Retirement Loading portfolio data for job {job_id}")
                try:
                    import sys
                    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                    from src import Database

                    db = Database()
                    job = db.jobs.find_by_id(job_id)
                    logger.info(f"[TRACE] job found: {bool(job)}")
                    if job:
                        logger.info(f"[TRACE] clerk_user_id: {job.get('clerk_user_id')}")

                    if job:
                        if observability:
                            observability.create_event(
                                name="Retirement Started!", status_message="OK"
                            )
                        
                        # portfolio_data = job.get('request_payload', {}).get('portfolio_data', {})
                        user_id = job['clerk_user_id']
                        user = db.users.find_by_clerk_id(user_id)
                        logger.info(f"[TRACE] user found: {bool(user)}")
                        accounts = db.accounts.find_by_user(user_id)
                        logger.info(f"[TRACE] accounts count: {len(accounts)}")

                        portfolio_data = {
                            'user_id': user_id,
                            'job_id': job_id,
                            'years_until_retirement': user.get('years_until_retirement', 30) if user else 30,
                            'accounts': []
                        }

                        for account in accounts:
                            account_data = {
                                'id': account['id'],
                                'name': account['account_name'],
                                'type': account.get('account_type', 'investment'),
                                'cash_balance': float(account.get('cash_balance', 0)),
                                'positions': []
                            }

                            positions = db.positions.find_by_account(account['id'])
                            logger.info(f"[TRACE] positions loaded for account {account['id']}: {len(positions)}")
                            for position in positions:
                                instrument = db.instruments.find_by_symbol(position['symbol'])
                                if instrument:
                                    account_data['positions'].append({
                                        'symbol': position['symbol'],
                                        'quantity': float(position['quantity']),
                                        'instrument': instrument
                                    })

                            portfolio_data['accounts'].append(account_data)

                        logger.info(f"Retirement: Loaded {len(portfolio_data['accounts'])} accounts with positions")
                        logger.info(f"[TRACE] FINAL portfolio_data keys: {list(portfolio_data.keys())}")
                        logger.info(f"[TRACE] accounts length: {len(portfolio_data['accounts'])}")
                    else:
                        logger.error(f"Retirement: Job {job_id} not found")
                        return {
                            'statusCode': 404,
                            'body': json.dumps({'error': f'Job {job_id} not found'})
                        }
                except Exception as e:
                    logger.error(f"Could not load portfolio from database: {e}")
                    return {
                        'statusCode': 400,
                        'body': json.dumps({'error': 'No portfolio data provided'})
                    }
            logger.info(f"[TRACE] ABOUT TO RUN AGENT for job {job_id}")
            logger.info(f"[TRACE] portfolio_data summary: accounts={len(portfolio_data.get('accounts', []))}")
            logger.info(f"Retirement: Processing job {job_id}")

            # Run the agent
            result = asyncio.run(run_retirement_agent(job_id, user_id, portfolio_data))

            logger.info(f"Retirement completed for job {job_id}")

            return {
                'statusCode': 200,
                'body': json.dumps(result)
            }

        except Exception as e:
            logger.error(f"Error in retirement: {e}", exc_info=True)
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'success': False,
                    'error': str(e)
                })
            }

# For local testing
if __name__ == "__main__":
    test_event = {
        "job_id": "test-retirement-123",
        "portfolio_data": {
            "accounts": [
                {
                    "name": "401(k)",
                    "type": "retirement",
                    "cash_balance": 10000,
                    "positions": [
                        {
                            "symbol": "SPY",
                            "quantity": 100,
                            "instrument": {
                                "name": "SPDR S&P 500 ETF",
                                "current_price": 450,
                                "allocation_asset_class": {"equity": 100}
                            }
                        },
                        {
                            "symbol": "BND",
                            "quantity": 100,
                            "instrument": {
                                "name": "Vanguard Total Bond Market ETF",
                                "current_price": 75,
                                "allocation_asset_class": {"fixed_income": 100}
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))