import json
import logging
import os
from dataclasses import dataclass
from datetime import timezone
from typing import Any


LOGGER = logging.getLogger(__name__)
MATCH_RESULTS_PREFIX = "match-results"


@dataclass(frozen=True)
class MatchResultBlobStatus:
    uploaded: bool
    path: str | None


def build_match_result_blob_path(match_id: int, completed_at) -> str:
    completed_at_utc = as_utc(completed_at)
    return (
        f"{MATCH_RESULTS_PREFIX}/"
        f"{completed_at_utc.date().isoformat()}/"
        f"{match_id}.json"
    )


def build_match_result_payload(match, room, rows, completed_at) -> dict[str, Any]:
    completed_at_utc = as_utc(completed_at)
    duration_seconds = max(
        0,
        int((as_utc(match.ends_at) - as_utc(match.started_at)).total_seconds()),
    )
    return {
        "match_id": match.id,
        "room_id": match.room_id,
        "room_code": room.room_code if room else "",
        "mode": match.mode,
        "status": match.status,
        "winner_user_id": match.winner_user_id,
        "winner_team": match.winner_team,
        "duration_seconds": duration_seconds,
        "completed_at": completed_at_utc.isoformat(),
        "players": [
            {
                "player_id": user.id,
                "username": user.username,
                "team": match_player.team,
                "score": match_player.score,
                "result": match_player.result,
            }
            for match_player, user in rows
        ],
    }


def upload_match_result_blob_from_rows(match, room, rows) -> MatchResultBlobStatus:
    if match.status != "finished":
        return MatchResultBlobStatus(uploaded=False, path=None)

    completed_at = as_utc(match.ends_at)
    blob_path = build_match_result_blob_path(match.id, completed_at)
    payload = build_match_result_payload(match, room, rows, completed_at)
    return upload_match_result_blob(blob_path, payload)


def upload_match_result_blob(
    blob_path: str,
    payload: dict[str, Any],
) -> MatchResultBlobStatus:
    account_url = (os.getenv("AZURE_STORAGE_ACCOUNT_URL") or "").strip()
    container_name = (os.getenv("MATCH_RESULTS_CONTAINER") or "").strip()
    if not account_url or not container_name:
        LOGGER.info(
            "Neko match result blob upload skipped: storage configuration is incomplete"
        )
        return MatchResultBlobStatus(uploaded=False, path=blob_path)

    try:
        blob_service_client = create_blob_service_client(account_url)
        upload_json_blob_once(blob_service_client, container_name, blob_path, payload)
        return MatchResultBlobStatus(uploaded=True, path=blob_path)
    except Exception as exc:
        if is_resource_exists_error(exc):
            return MatchResultBlobStatus(uploaded=True, path=blob_path)
        LOGGER.warning(
            "Neko match result blob upload failed: blob_path=%s error_type=%s",
            blob_path,
            type(exc).__name__,
        )
        return MatchResultBlobStatus(uploaded=False, path=blob_path)


def create_blob_service_client(account_url: str):
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    return BlobServiceClient(
        account_url=account_url,
        credential=DefaultAzureCredential(),
    )


def upload_json_blob_once(
    blob_service_client,
    container_name: str,
    blob_path: str,
    payload: dict[str, Any],
) -> None:
    blob_client = (
        blob_service_client.get_container_client(container_name)
        .get_blob_client(blob_path)
    )
    upload_options = {"overwrite": False}
    content_settings = create_json_content_settings()
    if content_settings is not None:
        upload_options["content_settings"] = content_settings
    blob_client.upload_blob(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        **upload_options,
    )


def create_json_content_settings():
    try:
        from azure.storage.blob import ContentSettings
    except ImportError:
        return None
    return ContentSettings(content_type="application/json")


def is_resource_exists_error(exc: Exception) -> bool:
    return exc.__class__.__name__ == "ResourceExistsError"


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
