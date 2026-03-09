from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import uvicorn
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MCP Server", version="1.0.0")


# ============================================================================
# Models
# ============================================================================


class SearchDocumentsRequest(BaseModel):
    query: str
    limit: Optional[int] = 5


class GetProjectInfoRequest(BaseModel):
    project_name: str


# ============================================================================
# Mock data
# ============================================================================

MOCK_DOCUMENTS = [
    {
        "id": "TD-001",
        "title": "Тендер на капитальный ремонт кровли жилого дома по ул. Ленина, 42",
        "status": "open",
        "deadline": "2026-03-15",
        "budget": "4 500 000 ₽",
    },
    {
        "id": "TD-002",
        "title": "Тендер на замену инженерных коммуникаций в МКД по пр. Мира, 17",
        "status": "open",
        "deadline": "2026-03-20",
        "budget": "12 800 000 ₽",
    },
    {
        "id": "TD-003",
        "title": "Тендер на утепление фасада и замену окон — ул. Строителей, 5",
        "status": "closed",
        "deadline": "2026-02-28",
        "budget": "8 200 000 ₽",
    },
    {
        "id": "TD-004",
        "title": "Тендер на ремонт подъездов и лестничных клеток — ул. Гагарина, 10",
        "status": "open",
        "deadline": "2026-04-01",
        "budget": "2 100 000 ₽",
    },
    {
        "id": "TD-005",
        "title": "Тендер на реконструкцию системы отопления — ул. Пушкина, 33",
        "status": "evaluation",
        "deadline": "2026-03-10",
        "budget": "6 700 000 ₽",
    },
]

MOCK_PROJECTS = {
    "ленина 42": {
        "name": "Капремонт кровли — Ленина, 42",
        "address": "ул. Ленина, 42",
        "stage": "Подготовка документации",
        "contractor": "ООО СтройРемонт",
        "start_date": "2026-04-01",
        "end_date": "2026-08-30",
        "budget": "4 500 000 ₽",
        "progress": "15%",
    },
    "мира 17": {
        "name": "Замена коммуникаций — Мира, 17",
        "address": "пр. Мира, 17",
        "stage": "Выбор подрядчика",
        "contractor": None,
        "start_date": "2026-05-01",
        "end_date": "2026-12-31",
        "budget": "12 800 000 ₽",
        "progress": "5%",
    },
}


# ============================================================================
# Tool endpoints
# ============================================================================


@app.post("/tools/search_documents")
async def search_documents(req: SearchDocumentsRequest):
    logger.info(f"search_documents: query='{req.query}', limit={req.limit}")
    query_lower = req.query.lower()
    results = [
        doc for doc in MOCK_DOCUMENTS
        if query_lower in doc["title"].lower() or query_lower in doc["status"]
    ]
    if not results:
        results = MOCK_DOCUMENTS
    return {"documents": results[:req.limit], "total": len(results)}


@app.post("/tools/get_project_info")
async def get_project_info(req: GetProjectInfoRequest):
    logger.info(f"get_project_info: project_name='{req.project_name}'")
    name_lower = req.project_name.lower()
    for key, project in MOCK_PROJECTS.items():
        if key in name_lower or name_lower in project["name"].lower():
            return {"project": project}
    return {"error": f"Проект '{req.project_name}' не найден", "available_projects": list(MOCK_PROJECTS.keys())}


@app.get("/")
async def root():
    return {
        "service": "MCP Server",
        "version": "1.0.0",
        "tools": ["search_documents", "get_project_info"],
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
