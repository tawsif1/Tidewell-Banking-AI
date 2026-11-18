from typing import Literal
from pydantic import BaseModel, ConfigDict, ValidationError
from pathlib import Path
import yaml


SCENARIO_DIR = Path("evals/scenarios")


ToolName = Literal[
    "verify_identity", "get_accounts", "get_recent_transactions", "freeze_card",
    "dispute_transaction", "request_fee_reversal", "escalate_to_human", "search_help_center",
]

class DbCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str
    equals: str | int | float | bool | None

class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified: bool | None = None          # None = don't check
    tools_called: list[ToolName] = []
    tools_not_called: list[ToolName] = []
    reply_must_include: list[str] = []
    reply_must_not_include: list[str] = []
    db: list[DbCheck] = []


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    persona: str
    goal: str
    knows: dict[str, str] = {}
    opening: str
    max_turns: int = 12
    expected: Expected


def load_scenarios(folder: Path = SCENARIO_DIR) -> list[Scenario]:
    scenarios = []
    for path in sorted(folder.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        try:
            scenarios.append(Scenario(**data))
        except ValidationError as e:
            raise ValueError(f"{path.name} is invalid:\n{e}") from e
    return scenarios