from pydantic import BaseModel, Field

class Park(BaseModel):
    park_code: str = Field(min_length=4, max_length=4)
    name: str
    state_code: str = Field(min_length=2, max_length=2)
    established_year: int = Field(gt=0, lt=2100)

class ParkLookupResult(BaseModel):
    parks: list[Park]
    count: int