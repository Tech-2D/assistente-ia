from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ActivityType = Literal["tarefa", "licao", "trabalho", "prova", "evento"]


class ActivityFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date | None = None
    finish_date: date | None = None
    types: list[ActivityType] = Field(default_factory=list, max_length=5)
    subject: str | None = Field(default=None, max_length=160)
    class_id: str | None = Field(default=None, max_length=160)
    include_general: bool = True
