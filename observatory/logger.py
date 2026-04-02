import json
import logging
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).parent / "events.jsonl"


class _JsonLineHandler(logging.FileHandler):
    """Emits one JSON object per line using the record's ``payload`` attribute."""

    def emit(self, record: logging.LogRecord) -> None:
        payload = getattr(record, "payload", {})
        try:
            self.stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.stream.flush()
        except Exception:
            self.handleError(record)


def _build_event_logger() -> logging.Logger:
    logger = logging.getLogger("observatory.events")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(_JsonLineHandler(str(LOG_PATH), encoding="utf-8"))
    return logger


_event_logger = _build_event_logger()


def log_economic_event(
    event_type: str,
    agent_id: str,
    amount: float,
    balance: float,
    **extra,
) -> None:
    """Write a structured JSON economic event to ``observatory/events.jsonl``."""
    payload: dict = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "agent_id": agent_id,
        "amount": amount,
        "balance": balance,
        **extra,
    }
    record = logging.LogRecord(
        name=_event_logger.name,
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    )
    record.payload = payload  # type: ignore[attr-defined]
    _event_logger.handle(record)
