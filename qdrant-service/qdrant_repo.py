import logging
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from config import settings

logger = logging.getLogger(__name__)

client: QdrantClient = None


def init_client():
    global client
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    logger.info(f"Connected to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}")


def init_collection(recreate: bool = False):
    """Create collection if not exists. Optionally recreate."""
    name = settings.collection_name

    if recreate:
        client.delete_collection(name)
        logger.info(f"Deleted collection '{name}'")

    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.DOT,
            ),
        )
        logger.info(f"Created collection '{name}' (dim={settings.embedding_dimensions}, metric=Dot)")
    else:
        logger.info(f"Collection '{name}' already exists")

    return client.get_collection(name)


def upsert_points(
    points: list[dict],
) -> int:
    """Upsert points into collection.
    Each point: {embedding: [...], payload: {...}}
    """
    structs = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=p["embedding"],
            payload=p["payload"],
        )
        for p in points
    ]

    client.upsert(
        collection_name=settings.collection_name,
        points=structs,
    )
    logger.info(f"Upserted {len(structs)} points")
    return len(structs)


def search_points(
    vector: list[float],
    limit: int = 5,
    filters: dict | None = None,
) -> list[dict]:
    """Search for similar points. Filters: {field: value}."""
    query_filter = None
    if filters:
        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filters.items()
            if v is not None
        ]
        if conditions:
            query_filter = Filter(must=conditions)

    results = client.query_points(
        collection_name=settings.collection_name,
        query=vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        {
            "id": str(point.id),
            "score": point.score,
            "payload": point.payload,
        }
        for point in results.points
    ]


def delete_by_filter(filters: dict) -> None:
    """Delete points matching filter conditions."""
    conditions = [
        FieldCondition(key=k, match=MatchValue(value=v))
        for k, v in filters.items()
        if v is not None
    ]
    if not conditions:
        raise ValueError("At least one filter is required for deletion")

    client.delete(
        collection_name=settings.collection_name,
        points_selector=Filter(must=conditions),
    )
    logger.info(f"Deleted points matching {filters}")
