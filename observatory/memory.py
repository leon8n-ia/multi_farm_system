import json
import sqlite3
from datetime import datetime
from pathlib import Path

from shared.models import Agent, SaleResult

DB_PATH = Path(__file__).parent / "farm_memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    id          TEXT    NOT NULL,
    farm_id     TEXT    NOT NULL DEFAULT '',
    credits     REAL    NOT NULL,
    status      TEXT    NOT NULL,
    generation  INTEGER NOT NULL DEFAULT 0,
    parent_id   TEXT,
    strategy    TEXT,
    timestamp   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id     TEXT    NOT NULL DEFAULT '',
    sold        INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    item        TEXT    NOT NULL DEFAULT '',
    timestamp   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cycles (
    rowid           INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id         TEXT    NOT NULL,
    cycle_num       INTEGER NOT NULL,
    profit          REAL    NOT NULL,
    roi             REAL    NOT NULL,
    agents_alive    INTEGER NOT NULL,
    agents_dead     INTEGER NOT NULL,
    timestamp       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS failed_strategies (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_type   TEXT    NOT NULL,
    strategy    TEXT    NOT NULL,
    reason      TEXT    NOT NULL DEFAULT '',
    timestamp   TEXT    NOT NULL
);
"""


class Memory:
    def __init__(self, db_path: str | Path = DB_PATH) -> None:
        self.db_path = str(db_path)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat()

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def save_agent(self, agent: Agent, farm_id: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agents
                    (id, farm_id, credits, status, generation, parent_id, strategy, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent.id,
                    farm_id,
                    agent.credits,
                    agent.status.value,
                    agent.generation,
                    agent.parent_id,
                    json.dumps(agent.strategy),
                    self._now(),
                ),
            )

    def save_sale(self, sale: SaleResult, farm_id: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sales (farm_id, sold, amount, item, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    farm_id,
                    int(sale.sold),
                    sale.usd_amount,
                    sale.item,
                    self._now(),
                ),
            )

    def save_cycle(self, farm, cycle_num: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cycles
                    (farm_id, cycle_num, profit, roi, agents_alive, agents_dead, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    farm.id,
                    cycle_num,
                    farm.profit,
                    farm.roi,
                    len(farm.producer_agents),
                    len(farm.dead_agents),
                    self._now(),
                ),
            )

    def save_failed_strategy(
        self, farm_type: str, strategy: dict, reason: str = ""
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO failed_strategies (farm_type, strategy, reason, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (farm_type, json.dumps(strategy), reason, self._now()),
            )

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_failed_strategies(self, farm_type: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT strategy, reason, timestamp FROM failed_strategies WHERE farm_type = ?",
                (farm_type,),
            ).fetchall()
        return [
            {
                "strategy": json.loads(row["strategy"]),
                "reason": row["reason"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def get_cycle_history(self, farm_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT cycle_num, profit, roi, agents_alive, agents_dead, timestamp
                FROM cycles WHERE farm_id = ?
                ORDER BY cycle_num DESC LIMIT ?
                """,
                (farm_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
