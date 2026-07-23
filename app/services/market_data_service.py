"""
app/services/market_data_service.py

Levi AI quantitative market-data engine.

Responsibilities:
- Fetch live Bybit OHLCV data
- Fetch 24-hour ticker data
- Calculate technical indicators without pandas-ta
- Detect trend, momentum, volume, volatility and market structure
- Generate multi-timeframe confluence
- Produce verified data for the AI layer

Compatible with Python 3.14.
"""

from dataclasses import dataclass, field
from typing import Optional

import httpx
import pandas as pd


BYBIT_BASE_URL = "https://api.bybit.com"

BYBIT_KLINES_URL = f"{BYBIT_BASE_URL}/v5/market/kline"
BYBIT_TICKER_URL = f"{BYBIT_BASE_URL}/v5/market/tickers"

TIMEFRAMES = ["15m", "1h", "4h", "1d"]

# Maps our timeframe labels to Bybit's interval codes
BYBIT_INTERVAL_MAP = {
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}

VALID_SYMBOL_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


# ============================================================
# HELPERS
# ============================================================

def normalize_symbol(pair: str) -> str:
    """
    Converts:

        BTC/USDT -> BTCUSDT
        btc/usdt -> BTCUSDT
        BTCUSDT  -> BTCUSDT
    """

    symbol = (
        pair
        .replace("/", "")
        .replace("-", "")
        .replace(" ", "")
        .upper()
    )

    if not symbol:
        raise ValueError(
            "Trading pair cannot be empty"
        )

    if not all(
        char in VALID_SYMBOL_CHARS
        for char in symbol
    ):
        raise ValueError(
            f"Invalid trading pair: {pair}"
        )

    return symbol


def safe_round(
    value,
    decimals: int = 6,
) -> Optional[float]:

    if value is None or pd.isna(value):
        return None

    return round(
        float(value),
        decimals,
    )


# ============================================================
# 1. LIVE MARKET DATA (BYBIT)
# ============================================================

def fetch_ohlcv(
    symbol: str,
    interval: str,
    limit: int = 500,
) -> pd.DataFrame:

    symbol = normalize_symbol(symbol)

    if interval not in TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe: {interval}. "
            f"Supported timeframes: "
            f"{', '.join(TIMEFRAMES)}"
        )

    bybit_interval = BYBIT_INTERVAL_MAP[interval]

    params = {
        "category": "spot",
        "symbol": symbol,
        "interval": bybit_interval,
        "limit": min(limit, 1000),
    }

    try:

        response = httpx.get(
            BYBIT_KLINES_URL,
            params=params,
            timeout=15.0,
        )

        response.raise_for_status()

        payload = response.json()

    except httpx.HTTPError as exc:

        raise RuntimeError(
            f"Unable to fetch live market data "
            f"for {symbol}"
        ) from exc

    if payload.get("retCode") != 0:

        raise ValueError(
            f"Bybit error for {symbol}: "
            f"{payload.get('retMsg', 'Unknown Bybit error')}"
        )

    raw = payload.get(
        "result",
        {},
    ).get(
        "list",
        [],
    )

    if not raw or len(raw) < 100:

        raise ValueError(
            f"Insufficient market data returned "
            f"for {symbol}"
        )

    # Bybit returns rows as:
    # [startTime, open, high, low, close, volume, turnover]
    # and orders them newest-first, so reverse to chronological order.
    raw = list(reversed(raw))

    df = pd.DataFrame(
        raw,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
        ],
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["open_time"] = pd.to_datetime(
        pd.to_numeric(
            df["open_time"]
        ),
        unit="ms",
    )

    df.set_index(
        "open_time",
        inplace=True,
    )

    df.dropna(
        subset=[
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
        inplace=True,
    )

    return df


def fetch_ticker(symbol: str) -> dict:

    symbol = normalize_symbol(symbol)

    try:

        response = httpx.get(
            BYBIT_TICKER_URL,
            params={
                "category": "spot",
                "symbol": symbol,
            },
            timeout=10.0,
        )

        response.raise_for_status()

        payload = response.json()

    except httpx.HTTPError as exc:

        raise RuntimeError(
            f"Unable to fetch 24-hour ticker "
            f"for {symbol}"
        ) from exc

    if payload.get("retCode") != 0:

        raise ValueError(
            f"Bybit ticker error: "
            f"{payload.get('retMsg', 'Unknown error')}"
        )

    result_list = payload.get(
        "result",
        {},
    ).get(
        "list",
        [],
    )

    if not result_list:

        raise ValueError(
            f"No ticker data returned for {symbol}"
        )

    data = result_list[0]

    price = float(data["lastPrice"])
    price_24h_ago = float(data["prevPrice24h"])

    price_change = price - price_24h_ago

    price_change_percent = (
        (price_change / price_24h_ago) * 100
        if price_24h_ago
        else 0.0
    )

    return {
        "symbol": symbol,
        "price": price,
        "price_change": price_change,
        "price_change_percent": price_change_percent,
        "high_24h": float(
            data["highPrice24h"]
        ),
        "low_24h": float(
            data["lowPrice24h"]
        ),
        "volume_24h": float(
            data["volume24h"]
        ),
        "quote_volume_24h": float(
            data["turnover24h"]
        ),
    }


# ============================================================
# 2. TECHNICAL INDICATORS
# ============================================================

def calculate_ema(
    series: pd.Series,
    period: int,
) -> pd.Series:

    return series.ewm(
        span=period,
        adjust=False,
        min_periods=period,
    ).mean()


def calculate_rsi(
    series: pd.Series,
    period: int = 14,
) -> pd.Series:

    delta = series.diff()

    gains = delta.clip(
        lower=0
    )

    losses = -delta.clip(
        upper=0
    )

    average_gain = gains.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    average_loss = losses.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    relative_strength = (
        average_gain
        / average_loss.replace(
            0,
            float("nan"),
        )
    )

    rsi = 100 - (
        100
        / (1 + relative_strength)
    )

    return rsi.fillna(50)


def calculate_macd(
    close: pd.Series,
) -> tuple[
    pd.Series,
    pd.Series,
    pd.Series,
]:

    fast_ema = calculate_ema(
        close,
        12,
    )

    slow_ema = calculate_ema(
        close,
        26,
    )

    macd = (
        fast_ema
        - slow_ema
    )

    signal = calculate_ema(
        macd,
        9,
    )

    histogram = (
        macd
        - signal
    )

    return (
        macd,
        signal,
        histogram,
    )


def calculate_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    standard_deviations: float = 2,
) -> tuple[
    pd.Series,
    pd.Series,
    pd.Series,
]:

    middle = close.rolling(
        window=period,
        min_periods=period,
    ).mean()

    standard_deviation = close.rolling(
        window=period,
        min_periods=period,
    ).std()

    upper = (
        middle
        + (
            standard_deviation
            * standard_deviations
        )
    )

    lower = (
        middle
        - (
            standard_deviation
            * standard_deviations
        )
    )

    return (
        upper,
        middle,
        lower,
    )


def calculate_atr(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.Series:

    previous_close = (
        df["close"].shift(1)
    )

    true_range = pd.concat(
        [
            df["high"]
            - df["low"],

            (
                df["high"]
                - previous_close
            ).abs(),

            (
                df["low"]
                - previous_close
            ).abs(),
        ],
        axis=1,
    ).max(
        axis=1
    )

    return true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()


# ============================================================
# 3. COMPUTE ALL INDICATORS
# ============================================================

def compute_indicators(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    df["ema20"] = calculate_ema(
        df["close"],
        20,
    )

    df["ema50"] = calculate_ema(
        df["close"],
        50,
    )

    df["ema200"] = calculate_ema(
        df["close"],
        200,
    )

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    df["rsi14"] = calculate_rsi(
        df["close"],
        14,
    )

    (
        df["macd"],
        df["macd_signal"],
        df["macd_hist"],
    ) = calculate_macd(
        df["close"]
    )

    # --------------------------------------------------------
    # BOLLINGER BANDS
    # --------------------------------------------------------

    (
        df["bb_upper"],
        df["bb_mid"],
        df["bb_lower"],
    ) = calculate_bollinger_bands(
        df["close"],
        20,
        2,
    )

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    df["atr14"] = calculate_atr(
        df,
        14,
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    df["vol_avg20"] = (
        df["volume"]
        .rolling(
            20
        )
        .mean()
    )

    df["volume_ratio"] = (
        df["volume"]
        / df["vol_avg20"]
    )

    # --------------------------------------------------------
    # CANDLE DATA
    # --------------------------------------------------------

    df["candle_body"] = (
        df["close"]
        - df["open"]
    )

    df["candle_direction"] = "neutral"

    df.loc[
        df["close"]
        > df["open"],
        "candle_direction",
    ] = "bullish"

    df.loc[
        df["close"]
        < df["open"],
        "candle_direction",
    ] = "bearish"

    return df


# ============================================================
# 4. TIMEFRAME SNAPSHOT
# ============================================================

@dataclass
class TimeframeSnapshot:

    timeframe: str

    price: float

    ema20: float
    ema50: float
    ema200: Optional[float]

    rsi14: float

    macd: float
    macd_signal: float
    macd_hist: float

    bb_upper: float
    bb_mid: float
    bb_lower: float

    atr14: float

    volume: float
    vol_avg20: float
    volume_ratio: float

    recent_high: float
    recent_low: float

    candle_direction: str

    trend_bias: str = field(
        init=False
    )

    rsi_state: str = field(
        init=False
    )

    macd_state: str = field(
        init=False
    )

    volume_state: str = field(
        init=False
    )

    volatility_state: str = field(
        init=False
    )

    bullish_score: int = field(
        init=False
    )

    bearish_score: int = field(
        init=False
    )

    # ========================================================
    # DERIVED STATES
    # ========================================================

    def __post_init__(self):

        # ----------------------------------------------------
        # TREND
        # ----------------------------------------------------

        if (
            self.ema200 is not None
            and self.price > self.ema20
            and self.ema20 > self.ema50
            and self.ema50 > self.ema200
        ):

            self.trend_bias = (
                "strong_uptrend"
            )

        elif (
            self.ema200 is not None
            and self.price < self.ema20
            and self.ema20 < self.ema50
            and self.ema50 < self.ema200
        ):

            self.trend_bias = (
                "strong_downtrend"
            )

        elif self.price > self.ema50:

            self.trend_bias = (
                "mild_uptrend"
            )

        elif self.price < self.ema50:

            self.trend_bias = (
                "mild_downtrend"
            )

        else:

            self.trend_bias = (
                "sideways"
            )

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        if self.rsi14 >= 70:

            self.rsi_state = (
                "overbought"
            )

        elif self.rsi14 <= 30:

            self.rsi_state = (
                "oversold"
            )

        elif self.rsi14 >= 55:

            self.rsi_state = (
                "bullish_zone"
            )

        elif self.rsi14 <= 45:

            self.rsi_state = (
                "bearish_zone"
            )

        else:

            self.rsi_state = (
                "neutral"
            )

        # ----------------------------------------------------
        # MACD
        # ----------------------------------------------------

        if (
            self.macd
            > self.macd_signal
            and self.macd_hist
            > 0
        ):

            self.macd_state = (
                "bullish_momentum"
            )

        elif (
            self.macd
            < self.macd_signal
            and self.macd_hist
            < 0
        ):

            self.macd_state = (
                "bearish_momentum"
            )

        else:

            self.macd_state = (
                "momentum_shifting"
            )

        # ----------------------------------------------------
        # VOLUME
        # ----------------------------------------------------

        if self.volume_ratio >= 1.5:

            self.volume_state = (
                "strongly_above_average"
            )

        elif self.volume_ratio >= 1.1:

            self.volume_state = (
                "above_average"
            )

        elif self.volume_ratio <= 0.7:

            self.volume_state = (
                "low_volume"
            )

        else:

            self.volume_state = (
                "average_volume"
            )

        # ----------------------------------------------------
        # VOLATILITY
        # ----------------------------------------------------

        atr_percentage = (
            self.atr14
            / self.price
        ) * 100

        if atr_percentage >= 5:

            self.volatility_state = (
                "very_high"
            )

        elif atr_percentage >= 2:

            self.volatility_state = (
                "high"
            )

        elif atr_percentage <= 0.75:

            self.volatility_state = (
                "low"
            )

        else:

            self.volatility_state = (
                "normal"
            )

        # ----------------------------------------------------
        # WEIGHTED DIRECTIONAL SCORE
        # ----------------------------------------------------

        bullish = 0
        bearish = 0

        # Trend
        if self.trend_bias == "strong_uptrend":

            bullish += 3

        elif self.trend_bias == "mild_uptrend":

            bullish += 2

        elif self.trend_bias == "strong_downtrend":

            bearish += 3

        elif self.trend_bias == "mild_downtrend":

            bearish += 2

        # MACD
        if self.macd_state == "bullish_momentum":

            bullish += 2

        elif self.macd_state == "bearish_momentum":

            bearish += 2

        # RSI
        if self.rsi_state == "bullish_zone":

            bullish += 1

        elif self.rsi_state == "bearish_zone":

            bearish += 1

        # Volume confirms existing direction
        if self.volume_state in (
            "above_average",
            "strongly_above_average",
        ):

            if bullish > bearish:

                bullish += 1

            elif bearish > bullish:

                bearish += 1

        self.bullish_score = bullish

        self.bearish_score = bearish

    # ========================================================
    # FINAL BIAS
    # ========================================================

    @property
    def simple_bias(self) -> str:

        difference = (
            self.bullish_score
            - self.bearish_score
        )

        if difference >= 2:

            return "BULLISH"

        if difference <= -2:

            return "BEARISH"

        return "NEUTRAL"


# ============================================================
# 5. BUILD SNAPSHOT
# ============================================================

def build_snapshot(
    timeframe: str,
    df: pd.DataFrame,
) -> TimeframeSnapshot:

    required_columns = [

        "ema20",
        "ema50",
        "ema200",

        "rsi14",

        "macd",
        "macd_signal",
        "macd_hist",

        "bb_upper",
        "bb_mid",
        "bb_lower",

        "atr14",

        "vol_avg20",
        "volume_ratio",

    ]

    latest = df.iloc[-1]

    missing = [

        column
        for column in required_columns
        if pd.isna(
            latest[column]
        )

    ]

    if missing:

        raise ValueError(
            "Insufficient indicator data. "
            f"Missing: {', '.join(missing)}"
        )

    recent = df.tail(20)

    return TimeframeSnapshot(

        timeframe=timeframe,

        price=safe_round(
            latest["close"],
            6,
        ),

        ema20=safe_round(
            latest["ema20"],
            6,
        ),

        ema50=safe_round(
            latest["ema50"],
            6,
        ),

        ema200=safe_round(
            latest["ema200"],
            6,
        ),

        rsi14=safe_round(
            latest["rsi14"],
            2,
        ),

        macd=safe_round(
            latest["macd"],
            6,
        ),

        macd_signal=safe_round(
            latest["macd_signal"],
            6,
        ),

        macd_hist=safe_round(
            latest["macd_hist"],
            6,
        ),

        bb_upper=safe_round(
            latest["bb_upper"],
            6,
        ),

        bb_mid=safe_round(
            latest["bb_mid"],
            6,
        ),

        bb_lower=safe_round(
            latest["bb_lower"],
            6,
        ),

        atr14=safe_round(
            latest["atr14"],
            6,
        ),

        volume=safe_round(
            latest["volume"],
            2,
        ),

        vol_avg20=safe_round(
            latest["vol_avg20"],
            2,
        ),

        volume_ratio=safe_round(
            latest["volume_ratio"],
            2,
        ),

        recent_high=safe_round(
            recent["high"].max(),
            6,
        ),

        recent_low=safe_round(
            recent["low"].min(),
            6,
        ),

        candle_direction=latest[
            "candle_direction"
        ],

    )


# ============================================================
# 6. MULTI-TIMEFRAME ANALYSIS
# ============================================================

def get_multi_timeframe_snapshots(
    pair: str,
    primary_timeframe: str,
) -> dict[str, TimeframeSnapshot]:

    if primary_timeframe not in TIMEFRAMES:

        raise ValueError(
            f"Unsupported timeframe: "
            f"{primary_timeframe}"
        )

    symbol = normalize_symbol(
        pair
    )

    snapshots = {}

    for timeframe in TIMEFRAMES:

        df = fetch_ohlcv(
            symbol,
            timeframe,
            limit=500,
        )

        df = compute_indicators(
            df
        )

        snapshots[timeframe] = build_snapshot(
            timeframe,
            df,
        )

    return snapshots


# ============================================================
# 7. LLM CONTEXT
# ============================================================

def format_snapshot_for_llm(
    snap: TimeframeSnapshot,
) -> str:

    ema200 = (

        str(snap.ema200)

        if snap.ema200 is not None

        else "insufficient history"

    )

    return f"""
[{snap.timeframe} TIMEFRAME]

PRICE:
{snap.price}

TREND:
{snap.trend_bias}

EMA STRUCTURE:
EMA20: {snap.ema20}
EMA50: {snap.ema50}
EMA200: {ema200}

MOMENTUM:
RSI(14): {snap.rsi14}
RSI STATE: {snap.rsi_state}

MACD:
MACD: {snap.macd}
SIGNAL: {snap.macd_signal}
HISTOGRAM: {snap.macd_hist}
STATE: {snap.macd_state}

BOLLINGER BANDS:
UPPER: {snap.bb_upper}
MIDDLE: {snap.bb_mid}
LOWER: {snap.bb_lower}

VOLATILITY:
ATR(14): {snap.atr14}
STATE: {snap.volatility_state}

VOLUME:
CURRENT: {snap.volume}
20-PERIOD AVERAGE: {snap.vol_avg20}
VOLUME RATIO: {snap.volume_ratio}x
STATE: {snap.volume_state}

MARKET RANGE:
RECENT HIGH: {snap.recent_high}
RECENT LOW: {snap.recent_low}

LATEST CANDLE:
{snap.candle_direction}

QUANTITATIVE SCORE:
BULLISH SCORE: {snap.bullish_score}
BEARISH SCORE: {snap.bearish_score}
COMPUTED BIAS: {snap.simple_bias}
""".strip()


def build_multi_timeframe_context(
    pair: str,
    primary_timeframe: str,
    snapshots: dict[
        str,
        TimeframeSnapshot,
    ],
) -> str:

    ordered = [

        snapshots[timeframe]

        for timeframe in TIMEFRAMES

        if timeframe in snapshots

    ]

    blocks = "\n\n".join(

        format_snapshot_for_llm(
            snapshot
        )

        for snapshot in ordered

    )

    return f"""
LIVE VERIFIED MARKET DATA

PAIR:
{pair.upper()}

PRIMARY ANALYSIS TIMEFRAME:
{primary_timeframe}

The values below were calculated from live exchange OHLCV data.

The AI must:

- Never invent current prices.
- Never invent indicator values.
- Never claim an indicator is bullish or bearish if the supplied values do not support it.
- Respect disagreements between timeframes.
- Avoid forcing a trade when evidence is conflicting.
- Treat oversold and overbought conditions as context, not automatic reversal signals.
- Use the primary timeframe for the actual trade setup.
- Use higher timeframes for directional context.
- Use lower timeframes for timing and momentum confirmation.

{blocks}
""".strip()
