import asyncio
import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jose import jwt

from common.core.config import settings

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass
class FcmResult:
    success: bool
    error_message: str | None = None


class FcmClient:
    def __init__(self) -> None:
        self._credentials = self._load_credentials()
        self._access_token: str | None = None
        self._access_token_exp: int = 0

    def is_configured(self) -> bool:
        return bool(self._credentials and self.project_id)

    @property
    def project_id(self) -> str | None:
        if settings.FCM_PROJECT_ID:
            return settings.FCM_PROJECT_ID
        if self._credentials:
            return self._credentials.get("project_id")
        return None

    def _load_credentials(self) -> dict[str, Any] | None:
        if settings.FCM_SERVICE_ACCOUNT_JSON:
            try:
                return json.loads(settings.FCM_SERVICE_ACCOUNT_JSON)
            except json.JSONDecodeError:
                logger.error("Invalid FCM_SERVICE_ACCOUNT_JSON")
                return None

        if settings.FCM_SERVICE_ACCOUNT_FILE:
            credential_path = Path(settings.FCM_SERVICE_ACCOUNT_FILE)
            if not credential_path.exists():
                logger.error("FCM service account file does not exist: %s", credential_path)
                return None
            if not credential_path.is_file():
                logger.error("FCM service account path is not a file: %s", credential_path)
                return None
            try:
                return json.loads(credential_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Failed to load FCM service account file %s: %s", credential_path, exc)
                return None

        logger.warning("FCM credentials are not configured; alert sends will be skipped")
        return None

    async def send_alert(
            self,
            *,
            token: str,
            title: str,
            body: str,
            data: dict[str, str],
    ) -> FcmResult:
        if not self.is_configured():
            return FcmResult(success=False, error_message="FCM credentials are not configured")

        try:
            access_token = await self._get_access_token()
            payload = {
                "message": {
                    "token": token,
                    "notification": {
                        "title": title,
                        "body": body,
                    },
                    "data": data,
                }
            }
            await asyncio.to_thread(self._post_fcm_message, access_token, payload)
            return FcmResult(success=True)
        except Exception as exc:
            logger.error("Failed to send FCM alert: %s", exc, exc_info=True)
            return FcmResult(success=False, error_message=str(exc))

    async def _get_access_token(self) -> str:
        now = int(time.time())
        if self._access_token and self._access_token_exp - 60 > now:
            return self._access_token

        assert self._credentials is not None
        token_response = await asyncio.to_thread(self._request_access_token)
        self._access_token = token_response["access_token"]
        self._access_token_exp = now + int(token_response.get("expires_in", 3600))
        return self._access_token

    def _request_access_token(self) -> dict[str, Any]:
        assert self._credentials is not None
        now = int(time.time())
        token_uri = self._credentials.get("token_uri") or DEFAULT_TOKEN_URI
        claims = {
            "iss": self._credentials["client_email"],
            "scope": FCM_SCOPE,
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        }
        assertion = jwt.encode(claims, self._credentials["private_key"], algorithm="RS256")
        body = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }).encode("utf-8")
        request = urllib.request.Request(
            token_uri,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_fcm_message(self, access_token: str, payload: dict[str, Any]) -> None:
        project_id = self.project_id
        if not project_id:
            raise ValueError("FCM project id is not configured")

        request = urllib.request.Request(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
