import json
import httpx
import asyncio
from config import OLLAMA_URL, PRIMARY_MODEL, FALLBACK_MODEL
from utils.logger import logger

async def preload_model(model_name: str):
    """
    Sends a dummy request to Ollama to load the model into memory.
    This prevents cold start delays (taking 60s+ to respond to the first message).
    """
    logger.info(f"Preloading model '{model_name}' into server memory...")
    try:
        # 120 second timeout for loading large models
        async with httpx.AsyncClient(timeout=120.0) as client:
            await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False
                }
            )
        logger.info(f"Model '{model_name}' preloaded successfully.")
    except Exception as e:
        logger.warning(f"Could not preload model '{model_name}': {e}")

async def verify_ollama_model() -> bool:
    """
    Verifies if Ollama is running and checks the status of configured models.
    At least one model must be present to start.
    """
    url = f"{OLLAMA_URL}/api/tags"
    logger.info(f"Connecting to Ollama at {url}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.error(f"Ollama server returned status code {response.status_code}")
                return False
                
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            
            primary_ok = PRIMARY_MODEL in models or any(m.startswith(PRIMARY_MODEL.split(":")[0]) for m in models)
            fallback_ok = FALLBACK_MODEL in models or any(m.startswith(FALLBACK_MODEL.split(":")[0]) for m in models)
            
            if primary_ok:
                logger.info(f"Primary model '{PRIMARY_MODEL}' verified successfully.")
            else:
                logger.warning(f"Primary model '{PRIMARY_MODEL}' is missing in Ollama. Available: {models}")
                
            if fallback_ok:
                logger.info(f"Fallback model '{FALLBACK_MODEL}' verified successfully.")
            else:
                logger.warning(f"Fallback model '{FALLBACK_MODEL}' is missing in Ollama. Available: {models}")

            if not primary_ok and not fallback_ok:
                logger.error("Neither primary nor fallback models are available in Ollama.")
                logger.error(f"Please run: 'ollama pull {PRIMARY_MODEL}' or 'ollama pull {FALLBACK_MODEL}'")
                return False

            # Start preloading models in the background to prevent cold-start latency
            if primary_ok:
                asyncio.create_task(preload_model(PRIMARY_MODEL))
            if fallback_ok:
                asyncio.create_task(preload_model(FALLBACK_MODEL))

            return True
            
    except httpx.ConnectError:
        logger.error(f"Could not connect to Ollama at {OLLAMA_URL}. Is Ollama running?")
        return False
    except Exception as e:
        logger.error(f"Unexpected error verifying Ollama: {e}")
        return False

async def _stream_with_model(model_name: str, messages: list[dict], system_prompt: str, retries: int = 2):
    """
    Internal helper to stream response from a specific model.
    """
    url = f"{OLLAMA_URL}/api/chat"
    formatted_messages = [{"role": "system", "content": system_prompt}] + messages
    
    payload = {
        "model": model_name,
        "messages": formatted_messages,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_predict": 70,  # Reduced from 180 to 70 for much faster CPU generation of short replies
        }
    }
    
    backoff = 1.0
    for attempt in range(retries):
        try:
            # Increased timeout to 180.0s to accommodate slower CPU start-times/TTFT
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        logger.error(f"Ollama returned error for {model_name}: {response.status_code} - {err_text.decode('utf-8')}")
                        raise httpx.HTTPStatusError("Ollama Error", request=response.request, response=response)
                        
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            content = chunk.get("message", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
            return  # Succeeded
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning(f"Generation failed with {model_name} (attempt {attempt + 1}/{retries}): {e}")
            if attempt == retries - 1:
                raise e
            await asyncio.sleep(backoff)
            backoff *= 2

async def generate_response_stream(messages: list[dict], system_prompt: str):
    """
    Streams response from primary model (Qwen 2.5), falling back to Mistral if it fails.
    """
    try:
        logger.info(f"Attempting response generation with primary model: {PRIMARY_MODEL}")
        async for chunk in _stream_with_model(PRIMARY_MODEL, messages, system_prompt):
            yield chunk
    except Exception as e:
        logger.error(f"Primary model '{PRIMARY_MODEL}' failed: {e}. Switching to fallback model '{FALLBACK_MODEL}'...")
        try:
            async for chunk in _stream_with_model(FALLBACK_MODEL, messages, system_prompt):
                yield chunk
        except Exception as fallback_err:
            logger.critical(f"Both primary and fallback models failed: {fallback_err}")
            # Yield a friendly fallback notification or raise
            raise fallback_err
