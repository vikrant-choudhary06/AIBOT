import json
import httpx
import asyncio
from config import OLLAMA_URL, MODEL_NAME
from utils.logger import logger

async def verify_ollama_model() -> bool:
    """
    Verifies if Ollama is running and if the configured MODEL_NAME exists.
    Returns True if valid, False/raises exception otherwise.
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
            
            # Check for exact name or prefix matches (e.g., 'gemma:2b' vs 'gemma:2b' tag variants)
            if MODEL_NAME in models:
                logger.info(f"Ollama model '{MODEL_NAME}' verified successfully.")
                return True
                
            # If not exact match, check if there's a tagless or tagged variation
            short_name = MODEL_NAME.split(":")[0]
            matched_models = [m for m in models if m.startswith(short_name)]
            if matched_models:
                logger.warning(f"Model '{MODEL_NAME}' not found exactly, but similar models found: {matched_models}.")
                logger.warning(f"Will try running with '{MODEL_NAME}'. Make sure it is pulled.")
                return True

            logger.error(f"Model '{MODEL_NAME}' was not found in Ollama.")
            logger.error(f"Available models: {models}")
            logger.error(f"Please run: 'ollama pull {MODEL_NAME}' in your terminal.")
            return False
            
    except httpx.ConnectError:
        logger.error(f"Could not connect to Ollama at {OLLAMA_URL}. Is Ollama running?")
        return False
    except Exception as e:
        logger.error(f"Unexpected error verifying Ollama: {e}")
        return False

async def generate_response_stream(messages: list[dict], system_prompt: str, retries: int = 3):
    """
    Calls local Ollama /api/chat endpoint and streams back response chunks.
    Injects system prompt as the first message.
    """
    url = f"{OLLAMA_URL}/api/chat"
    
    # Format messages for Ollama API
    formatted_messages = [{"role": "system", "content": system_prompt}] + messages
    
    payload = {
        "model": MODEL_NAME,
        "messages": formatted_messages,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_predict": 150,  # limit max response length to keep it short & conversational
        }
    }
    
    backoff = 1.0
    for attempt in range(retries):
        try:
            # We use a long timeout for reading because 2b models can occasionally have high TTFT (first token latency)
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        logger.error(f"Ollama returned error: {response.status_code} - {err_text.decode('utf-8')}")
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
            return  # Successful generation, exit retry loop
            
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning(f"Ollama generation failed (attempt {attempt + 1}/{retries}): {e}")
            if attempt == retries - 1:
                logger.error("Max retries reached. Ollama is unreachable.")
                raise e
            await asyncio.sleep(backoff)
            backoff *= 2
