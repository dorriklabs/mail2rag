# include/http_client.py

import logging
import requests
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class HTTPClient:
    """Client HTTP partagé pour LM Studio (ou autre backend)."""

    def __init__(self, base_url: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def post(self, path: str, json: dict):
        url = f"{self.base_url}{path}"
        try:
            res = self.session.post(url, json=json, timeout=self.timeout)
        except Exception as e:
            logger.error(f"HTTP POST {url} failed: {e}")
            raise HTTPException(
                status_code=502,
                detail="Upstream LM Studio unreachable",
            )

        if not res.ok:
            logger.error(f"HTTP {res.status_code} from {url}: {res.text[:500]}")
            raise HTTPException(status_code=502, detail="LM Studio error")

        try:
            return res.json()
        except Exception as e:
            logger.error(f"Invalid JSON from {url}: {e}")
            raise HTTPException(
                status_code=502,
                detail="Invalid LM Studio response",
            )
