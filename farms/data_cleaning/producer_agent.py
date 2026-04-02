import time

import pandas as pd

from shared.models import Agent, AgentStatus, TaskResult


class ProducerAgent:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self.last_output: pd.DataFrame | None = None

    def execute_task(self, csv_path: str) -> TaskResult:
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            return TaskResult(success=False, credits_earned=0.0, description=str(exc))

        original_rows = len(df)
        start = time.perf_counter()

        # 1. Normalize all string columns to lowercase + strip whitespace
        str_cols = df.select_dtypes(include="str").columns
        df[str_cols] = df[str_cols].apply(lambda col: col.str.strip().str.lower())

        # 2. Drop rows containing any null values
        df = df.dropna()

        # 3. Remove duplicate rows
        df = df.drop_duplicates()

        elapsed_ms = (time.perf_counter() - start) * 1000

        df = df.reset_index(drop=True)
        self.last_output = df

        output_rows = len(df)
        rows_removed = original_rows - output_rows

        quality_score = min(100.0, (rows_removed / max(1, original_rows)) * 100.0)
        speed_score = max(0.0, 100.0 - elapsed_ms)
        resource_efficiency = (output_rows / max(1, original_rows)) * 100.0

        return TaskResult(
            success=True,
            credits_earned=0.0,
            description=(
                f"Cleaned {csv_path}: {original_rows} → {output_rows} rows "
                f"({rows_removed} removed)"
            ),
            quality_score=quality_score,
            speed_score=speed_score,
            resource_efficiency=resource_efficiency,
        )
