# VLM Migration Guide (Local Qwen 3)

This guide documents how to switch the extraction pipeline from the temporary cloud Groq LLM to your on-premise **Qwen 3 8B VLM**.

## 1. Ensure Full VLM Processing

The pipeline should now process all detected VLM targets rather than reducing them to a single table. If you previously added a temporary limit, remove it so the full extraction workflow runs.

*   Open `graph/sources/annual_report/extraction_pipeline.py`.
*   Confirm there is no block that filters `vlm_targets` down to a single target.

## 2. Update the LLM Configuration

The pipeline's VLM configurations are centralized in `graph/sources/annual_report/llm_config.py`. 

### For Ollama (Local Hosting)
If your Qwen 3 8B model is being served via Ollama locally:
```python
# graph/sources/annual_report/llm_config.py

# Point to your local Ollama server running the OpenAI-compatible API
DEFAULT_LLM_BASE_URL = "http://localhost:11434/v1"

# Specify your exact Qwen model name as pulled in Ollama
DEFAULT_LLM_MODEL = "qwen2.5:72b" # or whatever your specific tag is

# Local models do not require a real API key, but the OpenAI client requires the variable to exist
DEFAULT_LLM_API_KEY = "dummy" 
```

### For vLLM (Local Hosting)
If you are running the model via vLLM:
```python
# graph/sources/annual_report/llm_config.py

DEFAULT_LLM_BASE_URL = "http://localhost:8000/v1" 
DEFAULT_LLM_MODEL = "Qwen/Qwen2-VL-7B-Instruct"
DEFAULT_LLM_API_KEY = "dummy" 
```

## 3. Verify VLM Capabilities

Once configured, the system will start sending base64-encoded images to your local Qwen VLM. 

> [!WARNING]
> Ensure your local hardware has enough VRAM (approx 8GB-12GB depending on quantization) to handle Qwen 3 8B alongside high-resolution document images.

> [!TIP]
> The `vlm_extractor.py` uses `ChatOpenAI` which natively supports OpenAI-compatible endpoints like Ollama and vLLM. No structural changes to the extraction logic are necessary.
