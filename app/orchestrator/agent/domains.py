from pydantic import BaseModel, Field
from typing import Literal

class QueryPlan(BaseModel):
    route: Literal["sql", "knowledge_base", "hybrid"]
    park_name: str | None = None
    state_code: str | None = Field(
        default=None,
        description="Two-letter uppercase US state code"
    )
