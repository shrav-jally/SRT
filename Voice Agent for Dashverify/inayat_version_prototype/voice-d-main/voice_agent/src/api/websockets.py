import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from src.models.state import SessionContext
from src.core.pipeline import Pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/voice")
async def voice_websocket_endpoint(
    websocket: WebSocket,
    mode: str = Query(default="default", description="The behavior mode of the agent")
):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    logger.info(f"WebSocket connected: Session {session_id}, Mode {mode}")
    
    # Initialize dynamic context manager
    from src.main import app_state
    context = SessionContext(session_id=session_id, mode=mode)
    pipeline = Pipeline(
        websocket=websocket, 
        context=context,
        stt=app_state.stt,
        llm=app_state.llm,
        tts=app_state.tts
    )
    
    try:
        # Start the pipeline (this runs indefinitely until disconnected)
        await pipeline.start()
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: Session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        await pipeline.stop()
