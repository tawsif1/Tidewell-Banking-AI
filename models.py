from pydantic import BaseModel, Field
from uuid import uuid4

class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    verified: bool = False
    customer_id: int | None = None
    messages: list[dict] = Field(default_factory=list)
    failed_attempts: int = 0
    locked: bool = False  
    actions_taken: list[str] = Field(default_factory=list) 
    escalation_id: str | None = None                       