from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)


class UpdateTurnStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["confirmed", "cancelled"]
