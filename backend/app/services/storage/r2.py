"""
Cloudflare R2 storage via boto3 (S3-compatible API).

Cloudflare R2:
- S3-совместимый API
- 10GB бесплатно
- Без egress fees
- endpoint: https://<account_id>.r2.cloudflarestorage.com

ENV переменные нужны:
    R2_ACCOUNT_ID
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_BUCKET_NAME
"""

import logging
from typing import Optional

import boto3
from botocore.client import Config

from .base import StorageBackend

log = logging.getLogger(__name__)


class R2Storage(StorageBackend):
    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ):
        self.bucket_name = bucket_name
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

        log.info(f"R2 storage initialized: bucket={bucket_name}")

    def save(self, key: str, content: bytes, content_type: Optional[str] = None) -> str:
        kwargs = {"Bucket": self.bucket_name, "Key": key, "Body": content}
        if content_type:
            kwargs["ContentType"] = content_type
        self.client.put_object(**kwargs)
        return key

    def read(self, key: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket_name, Key=key)
            return obj["Body"].read()
        except self.client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Not found: {key}")

    def delete(self, key: str) -> None:
        # delete_object не кидает ошибку если файла нет
        self.client.delete_object(Bucket=self.bucket_name, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except self.client.exceptions.ClientError:
            return False

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Генерирует signed URL валидный expires_in секунд (по умолчанию 1 час)."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
