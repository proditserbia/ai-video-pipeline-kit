from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from app.config import settings
from worker.modules.base import UploadResult
from worker.modules.uploader.base import AbstractUploader

logger = structlog.get_logger(__name__)


class YouTubeUploader(AbstractUploader):
    """
    YouTube Data API v3 uploader.
    If client secrets are missing, marks the upload as skipped with a clear reason.
    """

    def upload(self, video_path: str, metadata: dict[str, Any]) -> UploadResult:
        secrets_file = settings.YOUTUBE_CLIENT_SECRETS_FILE
        if not secrets_file or not Path(secrets_file).exists():
            reason = (
                "YouTube upload skipped: YOUTUBE_CLIENT_SECRETS_FILE is not configured or the "
                "file does not exist. Set YOUTUBE_CLIENT_SECRETS_FILE in your .env to enable uploads."
            )
            logger.warning("youtube_upload_skipped", reason=reason)
            return UploadResult(url="", platform="youtube", skipped=True, skip_reason=reason)

        # TODO: Implement full OAuth2 + YouTube Data API v3 upload flow.
        #       Steps:
        #       1. Load credentials from secrets_file using google-auth-oauthlib.
        #       2. Refresh / obtain token (InstalledAppFlow or service account).
        #       3. Build resource: googleapiclient.discovery.build("youtube", "v3", credentials=...)
        #       4. Upload via youtube.videos().insert(..., media_body=MediaFileUpload(video_path)).
        #       5. Return the video ID / URL on success.
        raise NotImplementedError(
            "YouTubeUploader.upload TODO: full OAuth2 + Data API v3 implementation required. "
            "Install google-api-python-client and google-auth-oauthlib, then implement upload flow."
        )
