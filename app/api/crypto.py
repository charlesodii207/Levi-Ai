"""
app/api/crypto.py

Levi AI — Quant-Grounded Crypto Analysis API

Flow:
    User request
        ↓
    Live Binance market data
        ↓
    Real technical indicators
        ↓
    Multi-timeframe confluence
        ↓
    Deterministic trade-level validation
        ↓
    Levi AI interpretation
        ↓
    Structured analysis response
"""

import json
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.users import get_current_user
from app.models.user import User
from app.services.ai_service import generate_response
from app.services.market_data_service import (
    TIMEFRAMES,
    TimeframeSnapshot,
    build_multi_timeframe_context,
    get_multi_timeframe_snapshots,
)
from app.core.subscription_tiers import check_and_consume_activity


router = APIRouter(prefix="/crypto", tags=["Crypto"])


# ============================================================================
# SCHEMAS
# ============================================================================

class CryptoAnalyzeRequest(BaseModel):
    pair: str = Field(..., min_length=3, max_length=30)
    timeframe: str = "4h"
    model: Optional[str] = "swift"


class CryptoAnalyzeResponse(BaseModel):
    trend: str
    confidence: int
    indicators: list[str]

    entry: str
    stopLoss: str
    takeProfit: str
    riskReward: str

    summary: str
    novaInsight: Optional[str] = None

    mtfBias: dict[str, str]
    livePrice: float


# ============================================================================
# HELPERS
# ============================================================================

def clean_pair(pair: str) -> str:
    """
    Normalizes:
        BTC/USDT
        BTCUSDT
        btc/usdt

    into:
        BTC/USDT
    """

    pair = pair.strip().upper().replace("-", "/")

    if "/" not in pair:
        if pair.endswith("USDT"):
            pair = pair[:-4] + "/USDT"
        elif pair.endswith("USDC"):
            pair = pair[:-4] + "/USDC"
        elif pair.endswith("BUSD"):
            pair = pair[:-4] + "/BUSD"

    return pair


def safe_number(value) -> Optional[float]:
    try:
        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


def parse_model_json(text: str) -> dict:
    """
    Safely extracts JSON from the AI response.

    Handles accidental markdown fences while still requiring
    a valid JSON object.
    """

    if not text:
        raise ValueError("Empty model response")

    cleaned = text.strip()

    cleaned = cleaned.replace("```json", "")
    cleaned = cleaned.replace("```JSON", "")
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No valid JSON object found")

    candidate = cleaned[start:end + 1]

    try:
        return json.loads(candidate)

    except json.JSONDecodeError:

        repaired = []
        in_string = False
        escaped = False

        for char in candidate:

            if char == '"' and not escaped:
                in_string = not in_string

            if in_string and char == "\n":
                repaired.append("\\n")

            elif in_string and char == "\r":
                repaired.append("\\r")

            elif in_string and char == "\t":
                repaired.append("\\t")

            else:
                repaired.append(char)

            escaped = char == "\\" and not escaped

            if char != "\\":
                escaped = False

        return json.loads("".join(repaired))


# ============================================================================
# MTF CONFIDENCE ENGINE
# ============================================================================

def calculate_mtf_confidence(
    snapshots: dict[str, TimeframeSnapshot],
    primary_timeframe: str,
) -> int:

    biases = [
        snapshot.simple_bias
        for snapshot in snapshots.values()
    ]

    bullish = biases.count("BULLISH")
    bearish = biases.count("BEARISH")
    neutral = biases.count("NEUTRAL")

    total = len(biases)

    if total == 0:
        return 35

    dominant = max(bullish, bearish)

    agreement = dominant / total

    confidence = 35 + int(agreement * 45)

    primary = snapshots.get(primary_timeframe)

    if primary:

        if primary.simple_bias in ("BULLISH", "BEARISH"):
            confidence += 10

        if primary.rsi_state == "neutral":
            confidence += 5

        if primary.volume_state == "above_average":
            confidence += 5

    if neutral >= 2:
        confidence -= 8

    return max(25, min(90, confidence))


# ============================================================================
# ANALYSIS PROMPT
# ============================================================================

def build_prompt(
    pair: str,
    timeframe: str,
    market_context: str,
    is_nova: bool,
    calculated_confidence: int,
) -> str:

    nova_instruction = ""

    if is_nova:
        nova_instruction = """
"novaInsight": "A deep professional analysis covering volume conviction,
momentum divergence, psychological price levels, market structure,
and important macro or on-chain factors to monitor. Do not invent
specific live macro or on-chain values that were not provided."
"""

    return f"""
You are Levi AI's professional quantitative crypto analysis engine.

You are NOT a price fortune teller.

You are receiving REAL market data calculated from live exchange candles.

Your job is to:
1. Interpret the data.
2. Identify the dominant market direction.
3. Detect agreement and disagreement between timeframes.
4. Explain the setup clearly.
5. Never invent indicator values.
6. Never claim certainty.
7. Never promise profit.

Return ONLY valid JSON.

Required format:

{{
  "trend": "BULLISH" | "BEARISH" | "NEUTRAL",

  "confidence": 0-100,

  "indicators": [
    "short factual indicator observation",
    "short factual indicator observation",
    "short factual indicator observation"
  ],

  "entry": "specific price level or price zone",

  "stopLoss": "specific price level",

  "takeProfit": "specific price level",

  "riskReward": "example: 1:2.4",

  "summary": "detailed analysis covering market structure, momentum,
multi-timeframe agreement or disagreement, important support/resistance,
and the reasoning behind the setup",

  {nova_instruction}
}}

IMPORTANT RULES:

- Only use facts present in the supplied market data.
- Do not invent prices.
- Do not invent indicator readings.
- Do not claim that any trade is guaranteed.
- If timeframes disagree, reduce confidence.
- If the market is unclear, trend may be NEUTRAL.
- If there is no clean trade setup, say so clearly in the summary.
- A confidence above 80 requires strong agreement across multiple timeframes.
- A confidence above 90 should almost never be used.
- Do not force a trade simply because the user requested analysis.
- The risk/reward ratio must mathematically match the proposed levels.
- For a bullish setup: stop loss should be below entry and take profit above entry.
- For a bearish setup: stop loss should be above entry and take profit below entry.
- For a neutral setup: entry, stop loss and take profit may be "No clear setup".

The quantitative engine currently estimates a baseline confidence of approximately:
{calculated_confidence}/100

You may adjust this slightly based on the actual indicator evidence,
but you must not ignore major timeframe disagreement.

{market_context}

Analyze {pair} using {timeframe} as the primary timeframe.
"""


# ============================================================================
# RESPONSE VALIDATION
# ============================================================================

def validate_analysis(
    parsed: dict,
    primary: TimeframeSnapshot,
) -> dict:

    trend = str(
        parsed.get("trend", "NEUTRAL")
    ).upper().strip()

    if trend not in {"BULLISH", "BEARISH", "NEUTRAL"}:
        trend = "NEUTRAL"

    confidence = safe_number(parsed.get("confidence"))

    if confidence is None:
        confidence = 50

    confidence = max(0, min(100, int(confidence)))

    indicators = parsed.get("indicators", [])

    if not isinstance(indicators, list):
        indicators = []

    indicators = [
        str(item).strip()
        for item in indicators
        if str(item).strip()
    ][:5]

    if not indicators:
        indicators = ["Multi-timeframe technical analysis completed"]

    entry = str(parsed.get("entry", "")).strip()
    stop_loss = str(parsed.get("stopLoss", "")).strip()
    take_profit = str(parsed.get("takeProfit", "")).strip()
    risk_reward = str(parsed.get("riskReward", "")).strip()
    summary = str(parsed.get("summary", "")).strip()

    if not summary:
        summary = (
            "The available indicators do not provide enough information "
            "for a complete high-confidence setup."
        )

    return {
        "trend": trend,
        "confidence": confidence,
        "indicators": indicators,
        "entry": entry,
        "stopLoss": stop_loss,
        "takeProfit": take_profit,
        "riskReward": risk_reward,
        "summary": summary,
    }


# ============================================================================
# ROUTE
# ============================================================================

@router.post(
    "/analyze",
    response_model=CryptoAnalyzeResponse,
)
def analyze_crypto(
    request: CryptoAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    # ------------------------------------------------------------------------
    # 1. Validate request
    # ------------------------------------------------------------------------

    pair = clean_pair(request.pair)

    timeframe = request.timeframe.strip().lower()

    if timeframe not in TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"timeframe must be one of: {TIMEFRAMES}",
        )

    # ------------------------------------------------------------------------
    # 2. Enforce subscription activity limits
    # ------------------------------------------------------------------------

    check_and_consume_activity(
        db,
        current_user,
        request.model or "swift",
    )

    # ------------------------------------------------------------------------
    # 3. Fetch live market data
    # ------------------------------------------------------------------------

    try:

        snapshots = get_multi_timeframe_snapshots(
            pair,
            timeframe,
        )

    except ValueError as error:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )

    except Exception as error:

        print(
            f"[CRYPTO DATA ERROR] "
            f"pair={pair} "
            f"timeframe={timeframe} "
            f"error={error}"
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Unable to retrieve live market data for {pair}. "
                "Please try again."
            ),
        )

    # ------------------------------------------------------------------------
    # 4. Build quantitative context
    # ------------------------------------------------------------------------

    market_context = build_multi_timeframe_context(
        pair,
        timeframe,
        snapshots,
    )

    primary_snapshot = snapshots[timeframe]

    calculated_confidence = calculate_mtf_confidence(
        snapshots,
        timeframe,
    )

    # ------------------------------------------------------------------------
    # 5. Ask Levi to interpret the quantitative data
    # ------------------------------------------------------------------------

    is_nova = (
        request.model or "swift"
    ).lower() == "nova"

    prompt = build_prompt(
        pair=pair,
        timeframe=timeframe,
        market_context=market_context,
        is_nova=is_nova,
        calculated_confidence=calculated_confidence,
    )

    try:

        ai_reply = generate_response(
            prompt,
            [],
            model=request.model or "swift",
        )

    except Exception as error:

        print(f"[CRYPTO AI ERROR] {error}")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Levi AI was unable to complete the analysis.",
        )

    # ------------------------------------------------------------------------
    # 6. Parse AI response
    # ------------------------------------------------------------------------

    try:

        parsed = parse_model_json(ai_reply)

    except (ValueError, json.JSONDecodeError) as error:

        print(f"[CRYPTO JSON ERROR] {error}")
        print(f"[CRYPTO RAW RESPONSE] {ai_reply}")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Levi returned an invalid analysis format. "
                "Please try again."
            ),
        )

    # ------------------------------------------------------------------------
    # 7. Validate output
    # ------------------------------------------------------------------------

    validated = validate_analysis(
        parsed,
        primary_snapshot,
    )

    # Never allow the AI to claim a confidence wildly above
    # what the quantitative evidence supports.

    max_allowed_confidence = min(
        95,
        calculated_confidence + 15,
    )

    validated["confidence"] = min(
        validated["confidence"],
        max_allowed_confidence,
    )

    # ------------------------------------------------------------------------
    # 8. Build deterministic MTF bias row
    # ------------------------------------------------------------------------

    mtf_bias = {
        timeframe_name: snapshot.simple_bias
        for timeframe_name, snapshot in snapshots.items()
    }

    # ------------------------------------------------------------------------
    # 9. Return frontend-compatible response
    # ------------------------------------------------------------------------

    return CryptoAnalyzeResponse(
        trend=validated["trend"],
        confidence=validated["confidence"],
        indicators=validated["indicators"],
        entry=validated["entry"],
        stopLoss=validated["stopLoss"],
        takeProfit=validated["takeProfit"],
        riskReward=validated["riskReward"],
        summary=validated["summary"],
        novaInsight=(
            parsed.get("novaInsight")
            if is_nova
            else None
        ),
        mtfBias=mtf_bias,
        livePrice=primary_snapshot.price,
    )