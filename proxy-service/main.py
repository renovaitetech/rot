from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union, AsyncGenerator
import httpx
import json
import uvicorn
import logging
import asyncio
import redis.asyncio as aioredis
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from config import settings
from tools import TOOLS, execute_tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient = None
redis_client: aioredis.Redis = None

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"

WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS_RU = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def get_system_prompt() -> str:
    """Read system_prompt.txt and substitute runtime variables."""
    try:
        template = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""

    now = datetime.now()
    variables = defaultdict(str, {
        "date": f"{now.day} {MONTHS_RU[now.month]} {now.year}",
        "time": now.strftime("%H:%M"),
        "weekday": WEEKDAYS_RU[now.weekday()],
    })
    return template.format_map(variables)


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
MAX_TOOL_ITERATIONS = 3


# ============================================================================
# DeepSeek API calls
# ============================================================================


async def call_deepseek(
    messages: List[Dict[str, Any]],
    model: str,
    temperature: float,
    max_tokens: Optional[int],
    tools: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    logger.info(f"DeepSeek request: model={model}, messages={len(messages)}, tools={bool(tools)}")

    last_exception = None

    for attempt in range(1, settings.max_retries + 1):
        try:
            response = await http_client.post(
                settings.deepseek_api_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(f"DeepSeek HTTP {status_code} (attempt {attempt}/{settings.max_retries}): {e.response.text[:500]}")
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
            logger.error(f"DeepSeek error (attempt {attempt}/{settings.max_retries}): {type(e).__name__}: {e}")
            last_exception = e

            if attempt < settings.max_retries:
                delay = min(settings.retry_base_delay * (2 ** (attempt - 1)), 30)
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

    error_detail = f"DeepSeek API failed after {settings.max_retries} attempts"
    if isinstance(last_exception, httpx.HTTPStatusError):
        error_detail += f": HTTP {last_exception.response.status_code} - {last_exception.response.text[:500]}"
    else:
        error_detail += f": {type(last_exception).__name__}: {last_exception}"

    raise HTTPException(status_code=502, detail=error_detail)


async def stream_deepseek(
    messages: List[Dict[str, Any]],
    model: str,
    temperature: float,
    max_tokens: Optional[int],
) -> AsyncGenerator[bytes, None]:
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    logger.info(f"DeepSeek stream request: model={model}, messages={len(messages)}")

    async with http_client.stream("POST", settings.deepseek_api_url, headers=headers, json=payload) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            yield chunk


# ============================================================================
# Models
# ============================================================================


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


# ============================================================================
# Endpoints
# ============================================================================


@app.get("/")
async def root():
    return {
        "service": "Proxy Service",
        "version": "1.0.0",
        "status": "operational",
        "deepseek_configured": bool(settings.deepseek_api_key),
        "tools": [t["function"]["name"] for t in TOOLS],
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    logger.info(f"Received chat request: messages={len(request.messages)}, stream={request.stream}")

    if not settings.deepseek_api_key:
        raise HTTPException(status_code=500, detail="DEEPSEEK_API_KEY not configured")

    messages = [msg.model_dump(exclude_none=True) for msg in request.messages]

    # Inject system prompt if not present
    prompt = get_system_prompt()
    if prompt and not any(m["role"] == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": prompt})

    # Streaming: simple pass-through, no tool loop
    if request.stream:
        return StreamingResponse(
            stream_deepseek(messages, request.model, request.temperature, request.max_tokens),
            media_type="text/event-stream",
        )

    # Non-streaming without tools: single call
    active_tools = TOOLS if TOOLS else None
    if not active_tools:
        return await call_deepseek(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    # Non-streaming with tools: tool-calling loop
    for iteration in range(1, MAX_TOOL_ITERATIONS + 2):
        use_tools = active_tools if iteration <= MAX_TOOL_ITERATIONS else None

        call_messages = messages
        if use_tools is None:
            call_messages = list(messages)
            call_messages.append({
                "role": "user",
                "content": "На основе всех данных, которые ты уже нашёл, дай итоговый ответ. Не нужно искать дополнительную информацию.",
            })

        logger.info(f"Iteration {iteration}: tools={'on' if use_tools else 'off'}")

        response = await call_deepseek(
            messages=call_messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tools=use_tools,
        )

        choice = response.get("choices", [{}])[0]
        assistant_message = choice.get("message", {})
        finish_reason = choice.get("finish_reason")
        tool_calls = assistant_message.get("tool_calls")

        if not tool_calls or finish_reason == "stop":
            return response

        # Execute tool calls and append results to history
        messages.append(assistant_message)
        for tool_call in tool_calls:
            tool_id = tool_call.get("id")
            function_name = tool_call.get("function", {}).get("name")
            function_args_str = tool_call.get("function", {}).get("arguments", "{}")
            try:
                function_args = json.loads(function_args_str)
            except json.JSONDecodeError:
                function_args = {}

            logger.info(f"Executing tool: {function_name}({function_args})")
            tool_result = await execute_tool(function_name, function_args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": json.dumps(tool_result, ensure_ascii=False),
            })

    logger.warning(f"Reached max tool iterations ({MAX_TOOL_ITERATIONS})")
    return {
        "choices": [{
            "message": {"role": "assistant", "content": "Превышено максимальное количество итераций."},
            "finish_reason": "length",
        }]
    }


MODELS = [
    {
        "id": "deepseek-chat",
        "object": "model",
        "created": 1677610602,
        "owned_by": "deepseek",
    }
]


@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": MODELS}


@app.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    for model in MODELS:
        if model["id"] == model_id:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
