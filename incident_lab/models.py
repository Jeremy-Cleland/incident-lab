from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Proposal(StrictModel):
    diagnosis: Literal["bad_deployment", "connection_exhaustion", "upstream_outage", "insufficient_evidence"]
    action: Literal["rollback_release", "restore_worker_concurrency", "enable_degraded_mode", "none"]
    target: Literal["orders-api", "orders-worker", "upstream-client", "none"]
    summary: str = Field(min_length=1, max_length=1600)
    evidence_ids: list[str] = Field(max_length=12)
    uncertainty: str = Field(min_length=1, max_length=1000)
    expected_effect: str = Field(min_length=1, max_length=700)


class Approval(StrictModel):
    proposal_id: str
    revision: int = Field(ge=0)
    decision: Literal["approve", "reject"]


class CreateRun(StrictModel):
    case_id: str
