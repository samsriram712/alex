from __future__ import annotations

from typing import List, Optional
import os
import json
import logging
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel

from .events import DetectedEvent, EventSeverity
# from tenacity import retry, wait_exponential, stop_after_attempt

logger = logging.getLogger(__name__)

EVENT_AGENT_PROMPT = """
You are a financial Event Agent.

Your job is to detect IMPORTANT financial events from text.

You do NOT summarize.
You do NOT rewrite.

You extract actionable financial EVENTS.

Return ONLY JSON.
No explanation.
No prose.
No markdown.

Output format:

[
  {{
    "event_type": "string",
    "severity": "info | low | medium | high | critical",
    "confidence": 0.0-1.0,
    "title": "short title",
    "explanation": "plain English explanation",
    "evidence": ["short phrases"],
    "suggested_actions": ["actions"]
  }}
]

Rules:
- Minimum confidence = 0.65
- Be conservative
- Avoid duplicates
- Do not hallucinate numbers
- Only emit meaningful financial risk situations
- If nothing important, return []

Allowed event_type values:
- retirement_shortfall
- concentration_risk
- rebalance_recommended
- elevated_volatility

Do NOT invent new event_type values.

TEXT:
{input_text}
"""

def _make_event(
    *,
    user_id: Optional[str],
    job_id: Optional[str],
    source: str,
    event_type: str,
    severity: EventSeverity,
    confidence: float,
    title: str,
    explanation: str,
    evidence: list[str] | None = None,
    suggested_actions: list[str] | None = None,
) -> DetectedEvent:
    return DetectedEvent(
        event_type=event_type,
        severity=severity,
        confidence=confidence,
        title=title,
        explanation=explanation,
        evidence=evidence or [],
        suggested_actions=suggested_actions or [],
        source=source,
        job_id=job_id,
        user_id=user_id,
    )


def detect_events_from_narrative(
    *,
    user_id: Optional[str],
    job_id: Optional[str],
    source: str,
    narrative: str,
) -> List[DetectedEvent]:
    """
    Foundation for the Event Intelligence Layer.

    CURRENTLY:
      - Uses lightweight keyword/phrase heuristics.
      - Safe, deterministic, no AI calls.

    LATER:
      - Swap internals to call an Agent or Bedrock model
        that reads full context and emits DetectedEvent JSON.
    """
    text = (narrative or "").lower()
    events: List[DetectedEvent] = []

    # --- Example: concentration risk ---
    if "concentration" in text or "overweight" in text:
        events.append(
            _make_event(
                user_id=user_id,
                job_id=job_id,
                source=source,
                event_type="concentration_risk",
                severity="high",
                confidence=0.8,
                title="Potential concentration risk in portfolio",
                explanation=(
                    "The analysis suggests that a significant portion of the portfolio "
                    "may be concentrated in a small number of positions or themes."
                ),
                evidence=[
                    "Narrative references concentration or materially overweight positions."
                ],
                suggested_actions=[
                    "Review top holdings and their weight versus your target allocation.",
                    "Consider rebalancing to reduce concentration risk.",
                ],
            )
        )

    # --- Example: volatility / risk language ---
    if "high volatility" in text or "elevated risk" in text or "significant drawdown" in text:
        events.append(
            _make_event(
                user_id=user_id,
                job_id=job_id,
                source=source,
                event_type="elevated_volatility",
                severity="medium",
                confidence=0.7,
                title="Elevated volatility mentioned in analysis",
                explanation=(
                    "The report calls out elevated volatility or risk in parts of your portfolio."
                ),
                evidence=[
                    "Narrative references high volatility or elevated risk.",
                ],
                suggested_actions=[
                    "Check your risk tolerance and investment horizon.",
                    "Consider diversifying into lower-volatility assets.",
                ],
            )
        )

    # --- Example: rebalance suggestion ---
    if "rebalance" in text or "rebalancing" in text:
        events.append(
            _make_event(
                user_id=user_id,
                job_id=job_id,
                source=source,
                event_type="rebalance_recommended",
                severity="medium",
                confidence=0.9,
                title="Portfolio rebalance recommended",
                explanation=(
                    "The analysis explicitly suggests a portfolio rebalance to realign with targets."
                ),
                evidence=["Narrative mentions rebalance or rebalancing."],
                suggested_actions=[
                    "Schedule a review of your current allocation vs target.",
                    "Execute a rebalance or discuss options with an advisor.",
                ],
            )
        )

    # --- Example: retirement shortfall (from retirement agent language) ---
    if "shortfall" in text or "not on track" in text or "below target income" in text:
        events.append(
            _make_event(
                user_id=user_id,
                job_id=job_id,
                source=source,
                event_type="retirement_shortfall",
                severity="high",
                confidence=0.85,
                title="Retirement plan may be below target",
                explanation=(
                    "The retirement analysis indicates that projected income may fall short "
                    "of your target retirement income."
                ),
                evidence=[
                    "Narrative references shortfall, not on track, or income below target."
                ],
                suggested_actions=[
                    "Review your contribution rate and time horizon.",
                    "Consider increasing savings or adjusting retirement goals.",
                ],
            )
        )

    return events

async def detect_events_via_llm(
    *,
    user_id,
    job_id,
    source,
    narrative,
):
    """
    LLM-driven Event Agent using the same LitellmModel+Agent+Runner pattern
    as Reporter / Retirement.
    Falls back to rule-based detector on failure.
    """

    try:
        # ---------------------------------------------------------
        # 1. Configure Bedrock model (same pattern as Reporter)
        # ---------------------------------------------------------
        model_id = os.getenv("BEDROCK_MODEL_ID")
        bedrock_region = os.getenv("BEDROCK_REGION", "us-west-2")

        if not model_id:
            raise RuntimeError("BEDROCK_MODEL_ID is not set")

        os.environ["AWS_REGION_NAME"] = bedrock_region
        logger.info(f"[EventAgent] Using Bedrock model={model_id}, region={bedrock_region}")

        model = LitellmModel(model=f"bedrock/{model_id}")

        # ---------------------------------------------------------
        # 2. Build agent
        # ---------------------------------------------------------
        agent = Agent(
            name="Event Intelligence Agent",
            instructions="You are a financial Event Extraction agent.",
            model=model,
            tools=[],  # no tools for now
        )

        # ---------------------------------------------------------
        # 3. Prepare LLM task
        # ---------------------------------------------------------
        task = EVENT_AGENT_PROMPT.format(input_text=narrative)

        # ---------------------------------------------------------
        # 4. Run Agent synchronously (bridges already in async loop)
        # ---------------------------------------------------------
        result = await Runner.run(agent, input=task)

        raw = result.final_output.strip()
        
        # Defensive stripping of markdown code blocks
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.replace("json", "", 1).strip()
        parsed = json.loads(raw)

        if not isinstance(parsed, list):
            raise ValueError("EventAgent output must be a JSON array")

        # ---------------------------------------------------------
        # 5. Convert JSON → DetectedEvent objects
        # ---------------------------------------------------------
        
        events = []

        for item in parsed:
            try:
                event = DetectedEvent(
                    event_type=item["event_type"],
                    severity=item["severity"],
                    confidence=float(item["confidence"]),
                    title=item["title"],
                    explanation=item["explanation"],
                    evidence=item.get("evidence", []),
                    suggested_actions=item.get("suggested_actions", []),
                    source=source,
                    job_id=job_id,
                    user_id=user_id,
                )
                if event.confidence < 0.65:
                    logger.warning(f"[EventAgent] Skipping low confidence event: {event}")
                    continue

                events.append(event)
            except Exception as e:
                logger.warning(f"[EventAgent] Skipping malformed event: {e} | item={item}")

        return events

    except Exception as e:
        logger.exception("[EventAgent] Failure — falling back to rules-based detection")

        # ---------------------------------------------------------
        # Fallback path (safe + deterministic)
        # ---------------------------------------------------------

        return detect_events_from_narrative(
            user_id=user_id,
            job_id=job_id,
            source=source,
            narrative=narrative,
        )