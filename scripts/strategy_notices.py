"""3C research notices based on official TAIEX closes and the fixed scenario."""
from datetime import datetime, time, timedelta, timezone
import math

from phase3c_strategy_integration import build

TAIPEI = timezone(timedelta(hours=8))
CLOSE_TIME = time(13, 30)


def after_close(now):
    local = now.astimezone(TAIPEI)
    return local.weekday() < 5 and local.time() >= CLOSE_TIME


def fresh_close(record, now):
    try:
        close = record["value"]
        today = now.astimezone(TAIPEI).date()
        observed = datetime.fromisoformat(record["checked_at"])
        if observed.tzinfo is None:
            return False
        cutoff = datetime.combine(today, CLOSE_TIME, tzinfo=TAIPEI)
        return (
            after_close(now) and cutoff <= observed <= now
            and record["date"] == today.isoformat() and record["status"] == "ok"
            and record["provider"] == "TWSE" and record["unit"] == "points"
            and record.get("cache_status") != "stale" and not record.get("last_error")
            and type(close) in (int, float) and math.isfinite(close) and close > 0
        )
    except (KeyError, TypeError, ValueError):
        return False


def evaluate(record, previous, now):
    scenario = build()
    close = record.get("value")
    if type(close) not in (int, float) or not math.isfinite(close) or close <= 0:
        close = None
    fresh = fresh_close(record, now)
    old_stage = previous.get("confirmed_stage", 0)
    pending = previous.get("pending_stage")
    stage = None
    if fresh:
        stage = sum(close <= row["trigger_taiex_points"] for row in scenario["stages"])
        # Keep a failed notice only while the current close still meets that stage.
        pending = pending if pending and pending <= stage else None
        if stage > old_stage:
            pending = stage
    return {
        "anchor": scenario["anchor_taiex_points"],
        "planned_total_twd": scenario["planned_total_twd"],
        "stages": scenario["stages"],
        "official_close": close,
        "close_date": record.get("date"),
        "official_close_fresh": fresh,
        "evaluated_at_utc": now.isoformat(),
        "current_stage": stage,
        "confirmed_stage": stage if fresh else old_stage,
        "pending_stage": pending,
        "last_delivered": previous.get("last_delivered"),
    }


def message(state):
    stage = state["pending_stage"]
    if not state["official_close_fresh"] or not stage:
        return None
    threshold = state["stages"][stage - 1]
    return (
        f"研究提示｜台股分批加碼第 {stage} 階門檻達成。"
        f"TWSE {state['close_date']} 收盤 {state['official_close']:,.2f} 點，"
        f"觸及 {threshold['trigger_taiex_points']:,.2f} 點"
        f"（固定基準 {state['anchor']:,} 點 × {100 + threshold['drawdown_from_fixed_anchor_pct']}%）。"
        "僅供情境研究，正式模型分數請以儀表板為準。"
    )
