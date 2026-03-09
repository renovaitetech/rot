import aioboto3
from botocore.exceptions import ClientError
from typing import Optional
import logging

from config import settings

logger = logging.getLogger(__name__)

session = aioboto3.Session()


def _client():
    return session.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


async def ensure_bucket():
    """Create bucket if it doesn't exist."""
    async with _client() as s3:
        try:
            await s3.head_bucket(Bucket=settings.s3_bucket_name)
            logger.info(f"Bucket '{settings.s3_bucket_name}' exists")
        except ClientError:
            await s3.create_bucket(Bucket=settings.s3_bucket_name)
            logger.info(f"Bucket '{settings.s3_bucket_name}' created")


async def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload file to S3. Returns the key."""
    async with _client() as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    logger.info(f"Uploaded: {key} ({len(data)} bytes)")
    return key


async def download_file(key: str) -> Optional[dict]:
    """Download file from S3. Returns dict with body bytes and content_type, or None."""
    async with _client() as s3:
        try:
            resp = await s3.get_object(Bucket=settings.s3_bucket_name, Key=key)
            body = await resp["Body"].read()
            return {
                "body": body,
                "content_type": resp.get("ContentType", "application/octet-stream"),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise


async def list_files(prefix: str = "") -> list[dict]:
    """List files in bucket with optional prefix. Returns list of {key, size, last_modified}."""
    async with _client() as s3:
        result = []
        paginator = s3.get_paginator("list_objects_v2")
        params = {"Bucket": settings.s3_bucket_name}
        if prefix:
            params["Prefix"] = prefix
        async for page in paginator.paginate(**params):
            for obj in page.get("Contents", []):
                result.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })
        return result


async def delete_file(key: str) -> bool:
    """Delete file from S3. Returns True if deleted."""
    async with _client() as s3:
        try:
            await s3.head_object(Bucket=settings.s3_bucket_name, Key=key)
        except ClientError:
            return False
        await s3.delete_object(Bucket=settings.s3_bucket_name, Key=key)
        logger.info(f"Deleted: {key}")
        return True
