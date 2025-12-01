import json
import os
from typing import List
import asyncio

import boto3
from common.job_tracker import JobTracker
from common.tools import get_latest_price_tool

from agents import RunContextWrapper  # or your actual wrapper import
from agents import function_tool             # adjust if you use a different decorator

from context import ReporterContext
from uuid import UUID
from datetime import datetime, timezone

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

SQS_QUEUE_URL = os.environ["SYMBOL_RESEARCH_QUEUE_URL"]
sqs = boto3.client("sqs")


@function_tool
async def submit_portfolio_research_job(
    wrapper: RunContextWrapper[ReporterContext],
    symbols: List[str],
    ) -> dict:
    """
    Attach job tracker rows to an existing jobs.id and enqueue one SQS message per symbol.
    """
    job_id = wrapper.context.job_id   # ✅ Always correct UUID
    UUID(job_id)  # Raises ValueError if invalid
    
    logger.info(f"[Reporter] Starting submit_portfolio_research_job job_id={job_id}")

    tracker = JobTracker()
    # ✅ HARD IDEMPOTENCY GUARD
    existing = tracker.get_job_status(job_id)
    if existing is not None:
        logger.warning(f"[Reporter] Job {job_id} already exists. Skipping resubmission.")
        return {
            "job_id": job_id,
            "status": existing.get("status", "exists"),
            "message": "Research job already submitted. Skipping duplicate invocation."
        }

    portfolio = wrapper.context.portfolio_data
    symbols = {
        pos["symbol"]
        for account in portfolio["accounts"]
        for pos in account["positions"]
    }
    symbols = sorted(symbols)

    logger.info(f"[Reporter] Unique symbols for research: job_id={job_id}, symbols={symbols}")
    

    # 1) Initialise tracker rows
    tracker.init_tracker_for_job(job_id=job_id, symbols=symbols)

    # 2) Enqueue one message per symbol
    # user_id = wrapper.context.clerk_user_id
    user_id = wrapper.context.portfolio_data["user_id"]

    for sym in symbols:
        body = {
            "job_id": job_id,
            "user_id": user_id,
            "symbol": sym,
        }
        sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(body),
        )
        logger.info(f"[Reporter] Enqueued symbol job: {sym}")

    logger.info(f"[Reporter] Submitted symbol research job: job_id={job_id}, symbols={symbols}")

    await asyncio.sleep(3)

    return {"job_id": job_id, "symbol_count": len(symbols)}


@function_tool
async def check_research_job_status(
    wrapper: RunContextWrapper[ReporterContext]
    ) -> dict:
    """
    Returns job_tracker + job_tracker_items for a given job_id.
    """
    job_id = wrapper.context.job_id   # ✅ Always correct UUID
    UUID(job_id)  # Raises ValueError if invalid

    tracker = JobTracker()

    status = tracker.get_job_status(job_id)
    if status is None:
        return {"job_id": job_id, "status": "not_found"}

    # ✅ Initial backoff if job is still "young"
    created = status.get("created_at")
    if created:
        if isinstance(created, str):
            created = datetime.fromisoformat(created)

        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age < 30:
            await asyncio.sleep(30 - age)
        else:
            await asyncio.sleep(15)

            
    if tracker.is_job_complete(job_id):
        return {
            "job_id": job_id,
            "status": "done"
        }

    # ✅ Normal poll pacing
    # await asyncio.sleep(15)
    return status

@function_tool
async def get_market_insights(
    wrapper: RunContextWrapper[ReporterContext], symbols: List[str]
) -> str:
    """
    Retrieve market insights from S3 Vectors knowledge base.

    Args:
        wrapper: Context wrapper with job_id and database
        symbols: List of symbols to get insights for

    Returns:
        Relevant market context and insights
    """
    try:
        import boto3
        import logging
        logger = logging.getLogger()

        # Get account ID
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
        bucket = f"alex-vectors-{account_id}"

        # Get embeddings
        sagemaker_region = os.getenv("DEFAULT_AWS_REGION", "us-east-1")
        sagemaker = boto3.client("sagemaker-runtime", region_name=sagemaker_region)
        endpoint_name = os.getenv("SAGEMAKER_ENDPOINT", "alex-embedding-endpoint")
        query = f"market analysis {' '.join(symbols[:5])}" if symbols else "market outlook"

        response = sagemaker.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=json.dumps({"inputs": query}),
        )

        result = json.loads(response["Body"].read().decode())
        # Extract embedding (handle nested arrays)
        if isinstance(result, list) and result:
            embedding = result[0][0] if isinstance(result[0], list) else result[0]
        else:
            embedding = result

        # Search vectors
        s3v = boto3.client("s3vectors", region_name=sagemaker_region)
        response = s3v.query_vectors(
            vectorBucketName=bucket,
            indexName="financial-research",
            queryVector={"float32": embedding},
            topK=3,
            returnMetadata=True,
        )

        # Format insights
        insights = []
        for vector in response.get("vectors", []):
            metadata = vector.get("metadata", {})
            text = metadata.get("text", "")[:200]
            if text:
                company = metadata.get("company_name", "")
                prefix = f"{company}: " if company else "- "
                insights.append(f"{prefix}{text}...")

        if insights:
            return "Market Insights:\n" + "\n".join(insights)
        else:
            return "Market insights unavailable - proceeding with standard analysis."

    except Exception as e:
        logger.warning(f"Reporter: Could not retrieve market insights: {e}")
        return "Market insights unavailable - proceeding with standard analysis."


