from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Application settings and configuration.
    """
    app_name: str = "Voice Agent Pipeline"
    debug: bool = True
    websocket_route: str = "/ws/voice"
    
    # Model Paths
    llm_model_path: str = "models/llm/Meta-Llama-3-8B-Instruct.Q4_K_M.gguf"
    tts_model_path: str = "models/tts/kokoro-v1.0.int8.onnx"
    tts_voices_path: str = "models/tts/voices.json"

    # Groq Cloud LLM (optional — if set, auto-switches to Groq backend)
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    class Config:
        env_file = ".env"

settings = Settings()
