import json
import re
import logging
from dataclasses import dataclass
from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)

AGENTIC_PROMPT = """Ты — система для разбиения документов на чанки для RAG (Retrieval Augmented Generation).

Документ представлен с пронумерованными строками в формате [N] текст.

Задача: определи границы семантически целостных чанков. Каждый чанк должен содержать одну логическую единицу информации, чтобы при поиске по эмбеддингам результат был точным и релевантным.

ПРАВИЛА:
- Каждый чанк — до {max_tokens} токенов (1 токен ≈ 4 символа для латиницы, ≈ 2 символа для кириллицы)
- Лучше сделать чанк меньше, но семантически чистым, чем большой но с разнородной информацией
- Разбивай по логическим секциям документа: если секция маленькая — это один чанк целиком
- Если секция большая — разбей на подтемы (например бюджет отдельных статей, требования по отдельным системам)
- НЕ разрывай таблицы, списки и связанные пункты
- Каждый чанк должен быть понятен без контекста остальных чанков
- Чанки должны покрывать весь документ без пропусков: end_line одного чанка + 1 = start_line следующего
- Комментарии вида <!-- Page N --> обозначают начало страницы N оригинального PDF. Используй их для ориентации, но не разбивай чанк только из-за смены страницы — приоритет у семантической целостности

ФОРМАТ ОТВЕТА — строго JSON:
{{
  "chunks": [
    {{"title": "краткое название чанка", "start_line": 1, "end_line": 15}},
    {{"title": "...", "start_line": 16, "end_line": 41}}
  ]
}}

Верни ТОЛЬКО JSON с номерами строк, НЕ включай текст документа в ответ.

ДОКУМЕНТ:
{document}"""


@dataclass
class ChunkResult:
    text: str
    text_clean: str
    token_count: int
    index: int
    source: str
    section_title: str


def _clean_text(text: str) -> str:
    """Strip markdown formatting and metadata for embedding."""
    cleaned = text
    # Remove HTML comments (<!-- Page N --> etc.)
    cleaned = re.sub(r'<!--.*?-->', '', cleaned)
    # Remove markdown headings syntax but keep text
    cleaned = re.sub(r'^#{1,6}\s+', '', cleaned, flags=re.MULTILINE)
    # Remove bold/italic markers
    cleaned = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', cleaned)
    # Remove horizontal rules
    cleaned = re.sub(r'^-{3,}\s*$', '', cleaned, flags=re.MULTILINE)
    # Remove bullet markers but keep text
    cleaned = re.sub(r'^[\s]*[-*+]\s+', '', cleaned, flags=re.MULTILINE)
    # Collapse multiple newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def _extract_section_title(text: str) -> str:
    """Extract the first markdown heading from chunk text."""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for latin, ~2 for cyrillic."""
    latin = sum(1 for c in text if c.isascii())
    non_latin = len(text) - latin
    return int(latin / 4 + non_latin / 2)


def _number_lines(text: str) -> tuple[str, list[str]]:
    """Add line numbers to text. Returns numbered text and original lines."""
    lines = text.splitlines()
    numbered = "\n".join(f"[{i + 1}] {line}" for i, line in enumerate(lines))
    return numbered, lines


def _to_results(chunks, source: str) -> list[ChunkResult]:
    """Convert chonkie Chunk objects to ChunkResult list."""
    results = []
    for i, chunk in enumerate(chunks):
        results.append(ChunkResult(
            text=chunk.text,
            text_clean=_clean_text(chunk.text),
            token_count=chunk.token_count,
            index=i,
            source=source,
            section_title=_extract_section_title(chunk.text),
        ))
    return results


def chunk_agentic(text: str, source: str) -> list[ChunkResult]:
    """Agentic chunking: send numbered lines to DeepSeek, get back line ranges."""
    client = OpenAI(
        base_url=settings.deepseek_api_url,
        api_key=settings.deepseek_api_key,
    )

    numbered_text, lines = _number_lines(text)
    total_lines = len(lines)

    prompt = AGENTIC_PROMPT.format(
        max_tokens=settings.chunk_size,
        document=numbered_text,
    )

    logger.info(f"Sending document to DeepSeek for agentic chunking ({total_lines} lines, {len(text)} chars)")
    response = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty response from DeepSeek")

    # Log token usage
    usage = response.usage
    if usage:
        logger.info(f"Token usage: input={usage.prompt_tokens}, output={usage.completion_tokens}, total={usage.total_tokens}")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse DeepSeek response as JSON: {e}\nResponse: {content[:500]}")
        raise ValueError(f"DeepSeek returned invalid JSON: {e}")

    raw_chunks = parsed.get("chunks", parsed if isinstance(parsed, list) else [])

    # Build chunks from line ranges
    results = []
    for i, chunk in enumerate(raw_chunks):
        start = chunk.get("start_line", 1) - 1  # to 0-indexed
        end = chunk.get("end_line", total_lines)  # inclusive
        start = max(0, min(start, total_lines - 1))
        end = max(start + 1, min(end, total_lines))

        chunk_text = "\n".join(lines[start:end])
        results.append(ChunkResult(
            text=chunk_text,
            text_clean=_clean_text(chunk_text),
            token_count=_estimate_tokens(chunk_text),
            index=i,
            source=source,
            section_title=chunk.get("title", _extract_section_title(chunk_text)),
        ))

    logger.info(f"Agentic chunking: {len(results)} chunks from {total_lines} lines")
    return results


def chunk_recursive(text: str, source: str) -> list[ChunkResult]:
    """Recursive chunking by document structure."""
    from chonkie import RecursiveChunker

    chunker = RecursiveChunker(
        chunk_size=settings.chunk_size,
    )
    chunks = chunker(text)
    return _to_results(chunks, source)


STRATEGIES = {
    "agentic": chunk_agentic,
    "recursive": chunk_recursive,
}


def chunk_text(text: str, source: str, strategy: str = "") -> list[ChunkResult]:
    """Chunk text using the specified strategy."""
    strategy = strategy or settings.default_strategy
    fn = STRATEGIES.get(strategy)
    if not fn:
        raise ValueError(f"Unknown strategy: {strategy}. Available: {list(STRATEGIES.keys())}")
    logger.info(f"Chunking with strategy='{strategy}', chunk_size={settings.chunk_size}")
    return fn(text, source)
