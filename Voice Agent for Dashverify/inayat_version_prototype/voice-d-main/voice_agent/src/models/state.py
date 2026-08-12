from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class SessionContext(BaseModel):
    """
    Context for the current WebSocket session.
    """
    session_id: str
    mode: str = Field(default="default", description="The mode of the interaction (e.g., interview, background_check)")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PipelineState(BaseModel):
    """
    Internal state of the orchestrator pipeline.
    """
    is_interrupted: bool = Field(default=False, description="Flag indicating if the user has interrupted the bot")
    is_speaking: bool = Field(default=False, description="Flag indicating if the user is currently speaking")
    is_bot_speaking: bool = Field(default=False, description="Flag indicating if the bot is currently generating/speaking")
