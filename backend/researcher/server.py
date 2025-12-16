"""
Alex Researcher Service - Investment Advice Agent
"""

import os
import logging
import asyncio
from datetime import datetime, UTC
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from agents import Agent, Runner, trace
from agents.extensions.models.litellm_model import LitellmModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from litellm.exceptions import RateLimitError
from database.src.models import Database

from common.job_tracker import JobTracker
from common.tools import get_latest_price_tool  # shared tool
# ingest_financial_document already imported from researcher.tools
from agents.mcp import MCPServerStdio

class AgentTemporaryError(Exception):
    """Temporary error that should trigger retry"""
    pass

# Suppress LiteLLM warnings about optional dependencies
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)

# Import from our modules
from researcher.context import get_agent_instructions, DEFAULT_RESEARCH_PROMPT
from researcher.mcp_servers import create_playwright_mcp_server
from researcher.tools import ingest_financial_document, get_latest_price_tool

# Load environment
load_dotenv(override=True)

app = FastAPI(title="Alex Researcher Service")


# Request model
class ResearchRequest(BaseModel):
    topic: Optional[str] = None  # Optional - if not provided, agent picks a topic


@retry(
    retry=retry_if_exception_type((RateLimitError, AgentTemporaryError, TimeoutError, asyncio.TimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=lambda retry_state: logging.info(
        f"Researcher: Temporary error, retrying in {retry_state.next_action.sleep} seconds..."
    ),
)

def build_brave_mcp_params():
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        raise RuntimeError("BRAVE_API_KEY is not set")

    return {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": api_key},
    }

async def run_research_agent(
    topic: str | None = None,
    *,
    use_browser: bool = True,
) -> str:
    """
    Run the research agent to generate investment advice with automatic retry for temporary errors.
    
    Dual-mode Researcher:

    use_browser=True  -> Brave + MCP browser (general / scheduler research)
    use_browser=False -> Brave only (symbol research)
    """

    # Prepare the user query
    if topic:
        query = f"Research this investment topic: {topic}"
    else:
        query = DEFAULT_RESEARCH_PROMPT

    # Please override these variables with the region you are using
    # Other choices: us-west-2 (for OpenAI OSS models) and eu-central-1
    REGION = "us-west-2"
    os.environ["AWS_REGION_NAME"] = REGION  # LiteLLM's preferred variable
    os.environ["AWS_REGION"] = REGION  # Boto3 standard
    os.environ["AWS_DEFAULT_REGION"] = REGION  # Fallback

    # Please override this variable with the model you are using
    # Common choices: bedrock/eu.amazon.nova-pro-v1:0 for EU and bedrock/us.amazon.nova-pro-v1:0 for US
    # or bedrock/amazon.nova-pro-v1:0 if you are not using inference profiles
    # bedrock/openai.gpt-oss-120b-1:0 for OpenAI OSS models
    # bedrock/converse/us.anthropic.claude-sonnet-4-20250514-v1:0 for Claude Sonnet 4
    # NOTE that nova-pro is needed to support tools and MCP servers; nova-lite is not enough - thank you Yuelin L.!
    MODEL = "bedrock/us.amazon.nova-pro-v1:0"
    model = LitellmModel(model=MODEL)

    tools = [ingest_financial_document, get_latest_price_tool]

# --- Brave MCP (enabled for BOTH modes) ---
    brave_params = build_brave_mcp_params()

    # Create and run the agent with MCP server
    try:
        browser_budget = 1 if use_browser else 0
        with trace("Researcher"):

            # Always enable Brave MCP
            async with MCPServerStdio(
                params=brave_params,
                client_session_timeout_seconds=30,
            ) as brave_mcp:

                mcp_servers = [brave_mcp]
                if use_browser:
                    # GENERAL MODE → Add Playwright MCP
                    async with create_playwright_mcp_server(timeout_seconds=60) as playwright_mcp:
                        agent = Agent(
                            name="Alex Investment Researcher",
                            instructions=get_agent_instructions() + f"\n\nBROWSER BUDGET: {browser_budget} page load(s) maximum.",
                            model=model,
                            # tools=[ingest_financial_document],
                            tools=tools,
                            mcp_servers=[brave_mcp, playwright_mcp],
                        )

                        result = await Runner.run(agent, input=query, max_turns=15)
                        if hasattr(result, "events"):
                            tool_calls = [e for e in result.events if getattr(e, "type", None) == "tool_call"]
                            logging.info(f"TOOLS USED: {[getattr(t, 'name', '?') for t in tool_calls]}")
                else:
                    # SYMBOL MODE → NO BROWSER
                    agent = Agent(
                        name="Alex Symbol Researcher",
                        instructions=get_agent_instructions() + f"\n\nBROWSER BUDGET: {browser_budget} page load(s) maximum.",
                        model=model,
                        tools=tools,
                        mcp_servers=[brave_mcp],
                    )

                    result = await Runner.run(agent, input=query, max_turns=15)
                    if hasattr(result, "events"):
                        tool_calls = [e for e in result.events if getattr(e, "type", None) == "tool_call"]
                        logging.info(f"TOOLS USED: {[getattr(t, 'name', '?') for t in tool_calls]}")

        return result.final_output

    except (TimeoutError, asyncio.TimeoutError) as e:
        logging.warning(f"Researcher agent timeout: {e}")
        raise AgentTemporaryError(f"Timeout during agent execution: {e}")
    except Exception as e:
        error_str = str(e).lower()
        if "timeout" in error_str or "throttled" in error_str:
            logging.warning(f"Researcher temporary error: {e}")
            raise AgentTemporaryError(f"Temporary error: {e}")
        raise  # Re-raise non-retryable errors


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "Alex Researcher",
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.post("/research")
async def research(request: ResearchRequest) -> str:
    """
    Generate investment research and advice.

    The agent will:
    1. Browse current financial websites for data
    2. Analyze the information found
    3. Store the analysis in the knowledge base

    If no topic is provided, the agent will pick a trending topic.
    """
    try:
        response = await run_research_agent(request.topic, use_browser=True)
        return response
    except Exception as e:
        print(f"Error in research endpoint: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/research/auto")
async def research_auto():
    """
    Automated research endpoint for scheduled runs.
    Picks a trending topic automatically and generates research.
    Used by EventBridge Scheduler for periodic research updates.
    """
    try:
        # Always use agent's choice for automated runs
        response = await run_research_agent(topic=None, use_browser=True)
        return {
            "status": "success",
            "timestamp": datetime.now(UTC).isoformat(),
            "message": "Automated research completed",
            "preview": response[:200] + "..." if len(response) > 200 else response,
        }
    except Exception as e:
        print(f"Error in automated research: {e}")
        return {"status": "error", "timestamp": datetime.now(UTC).isoformat(), "error": str(e)}

# ============================================================
# NEW ENDPOINT — Symbol-specific research
# ============================================================

@app.post("/research/symbol")
async def research_symbol(payload: dict):
    """
    Symbol-focused research for portfolio-level analysis.
    Triggered by Reporter during Increment 5.
    """

    job_id = payload.get("job_id")
    user_id = payload.get("user_id")
    # account_id = payload.get("account_id")
    symbol = payload.get("symbol")

    if not all([job_id, user_id, symbol]):
        raise HTTPException(status_code=400, detail="Missing parameters")

    tracker = JobTracker()
    tracker.mark_symbol_running(job_id, symbol)

    # Build topic for Runner.run
    topic = (
        f"Focused equity analysis for {symbol}. "
        f"Use get_latest_price_tool to retrieve the latest price. "
        f"Provide company overview, financial outlook, growth drivers, risks, "
        f"and a concise investment thesis. "
        f"This is strictly symbol-specific research. Do NOT perform general market analysis."
    )

    try:
        # Reuse existing pipeline
        result = await run_research_agent(topic, use_browser=False)

        tracker.mark_symbol_done(job_id, symbol)

        # return a preview for debugging
        preview = result[:250] + "..." if len(result) > 250 else result
        return {
            "status": "success",
            "job_id": job_id,
            "symbol": symbol,
            "preview": preview
        }

    except Exception as e:
        tracker.mark_symbol_error(job_id, symbol, str(e))
        raise


@app.get("/health")
async def health():
    """Detailed health check."""
    # Debug container detection
    container_indicators = {
        "dockerenv": os.path.exists("/.dockerenv"),
        "containerenv": os.path.exists("/run/.containerenv"),
        "aws_execution_env": os.environ.get("AWS_EXECUTION_ENV", ""),
        "ecs_container_metadata": os.environ.get("ECS_CONTAINER_METADATA_URI", ""),
        "kubernetes_service": os.environ.get("KUBERNETES_SERVICE_HOST", ""),
    }

    return {
        "service": "Alex Researcher",
        "status": "healthy",
        "alex_api_configured": bool(os.getenv("ALEX_API_ENDPOINT") and os.getenv("ALEX_API_KEY")),
        "timestamp": datetime.now(UTC).isoformat(),
        "debug_container": container_indicators,
        "aws_region": os.environ.get("AWS_DEFAULT_REGION", "not set"),
        "bedrock_model": "bedrock/amazon.nova-pro-v1:0",
    }


@app.get("/test-bedrock")
async def test_bedrock():
    """Test Bedrock connection directly."""
    try:
        import boto3

        # Set ALL region environment variables
        os.environ["AWS_REGION_NAME"] = "us-east-1"
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        # Debug: Check what region boto3 is actually using
        session = boto3.Session()
        actual_region = session.region_name

        # Try to create Bedrock client explicitly in us-west-2
        client = boto3.client("bedrock-runtime", region_name="us-west-2")

        # Debug: Try to list models to verify connection
        try:
            bedrock_client = boto3.client("bedrock", region_name="us-west-2")
            models = bedrock_client.list_foundation_models()
            openai_models = [
                m["modelId"] for m in models["modelSummaries"] if "openai" in m["modelId"].lower()
            ]
        except Exception as list_error:
            openai_models = f"Error listing: {str(list_error)}"

        # Try basic model invocation with Nova Pro
        model = LitellmModel(model="bedrock/amazon.nova-pro-v1:0")

        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant. Be very brief.",
            model=model,
        )

        result = await Runner.run(agent, input="Say hello in 5 words or less", max_turns=1)

        return {
            "status": "success",
            "model": str(model.model),  # Use actual model from LitellmModel
            "region": actual_region,
            "response": result.final_output,
            "debug": {
                "boto3_session_region": actual_region,
                "available_openai_models": openai_models,
            },
        }
    except Exception as e:
        import traceback

        return {
            "status": "error",
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "debug": {
                "boto3_session_region": session.region_name if "session" in locals() else "unknown",
                "env_vars": {
                    "AWS_REGION_NAME": os.environ.get("AWS_REGION_NAME"),
                    "AWS_REGION": os.environ.get("AWS_REGION"),
                    "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION"),
                },
            },
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
