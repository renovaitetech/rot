from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
import httpx
import uvicorn
import logging
import asyncio
import redis.asyncio as aioredis
from contextlib import asynccontextmanager

from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient = None
redis_client: aioredis.Redis = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client, redis_client
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    redis_client = aioredis.from_url(settings.redis_url)
    yield
    await http_client.aclose()
    await redis_client.aclose()


app = FastAPI(title="Proxy Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def call_upstream(
    messages: List[Dict[str, Any]],
    model: str,
    temperature: float,
    max_tokens: Optional[int],
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.upstream_api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    logger.info(f"Upstream request: model={model}, messages={len(messages)}, url={settings.upstream_api_url}")

    last_exception = None

    for attempt in range(1, settings.max_retries + 1):
        try:
            response = await http_client.post(
                settings.upstream_api_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(f"Upstream HTTP {status_code} (attempt {attempt}/{settings.max_retries}): {e.response.text[:500]}")
            last_exception = e

            if status_code not in RETRYABLE_STATUS_CODES:
                break

            if attempt < settings.max_retries:
                delay = settings.retry_base_delay * (2 ** (attempt - 1))
                if status_code == 429:
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        delay = max(delay, float(retry_after))
                delay = min(delay, 30)
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.error(f"Upstream error (attempt {attempt}/{settings.max_retries}): {type(e).__name__}: {e}")
            last_exception = e

            if attempt < settings.max_retries:
                delay = min(settings.retry_base_delay * (2 ** (attempt - 1)), 30)
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

    error_detail = f"Upstream API failed after {settings.max_retries} attempts"
    if isinstance(last_exception, httpx.HTTPStatusError):
        error_detail += f": HTTP {last_exception.response.status_code} - {last_exception.response.text[:500]}"
    else:
        error_detail += f": {type(last_exception).__name__}: {last_exception}"

    raise HTTPException(status_code=502, detail=error_detail)


class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]], None] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


@app.get("/")
async def root():
    return {
        "service": "Proxy Service",
        "version": "1.0.0",
        "status": "operational",
        "upstream_configured": bool(settings.upstream_api_key),
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    logger.info(f"Received chat request with {len(request.messages)} messages")

    if not settings.upstream_api_key:
        raise HTTPException(status_code=500, detail="UPSTREAM_API_KEY not configured")

    messages = [msg.model_dump(exclude_none=True) for msg in request.messages]
    return await call_upstream(
        messages=messages,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
