import logging
from datetime import datetime, timezone

import azure.functions as func

from azure_functions.neko_monitor.function_app import blob_upload_eventgrid


def make_event(
    *,
    event_id="event-1",
    event_type="Microsoft.Storage.BlobCreated",
    subject="/blobServices/default/containers/eventgrid-demo/blobs/demo.txt",
    data=None,
):
    return func.EventGridEvent(
        id=event_id,
        data=data or {},
        topic="/subscriptions/test/resourceGroups/test/providers/Microsoft.Storage/storageAccounts/nekoblockblastnhom2",
        subject=subject,
        event_type=event_type,
        event_time=datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc),
        data_version="1",
    )


def test_blob_created_event_logs_sanitized_blob_details(caplog):
    event = make_event(
        event_id="blob-event-1",
        data={
            "url": (
                "https://nekoblockblastnhom2.blob.core.windows.net/"
                "eventgrid-demo/demo.txt?sig=secret-signature&token=secret-token"
            ),
            "api": "PutBlob",
            "contentType": "text/plain",
            "contentLength": 42,
        },
    )

    with caplog.at_level(logging.INFO):
        blob_upload_eventgrid(event)

    assert "Neko Event Grid blob created: event_id=blob-event-1" in caplog.text
    assert (
        "blob_url=https://nekoblockblastnhom2.blob.core.windows.net/"
        "eventgrid-demo/demo.txt"
    ) in caplog.text
    assert "content_type=text/plain" in caplog.text
    assert "content_length=42" in caplog.text
    assert "secret-signature" not in caplog.text
    assert "secret-token" not in caplog.text


def test_non_blob_created_event_is_ignored(caplog):
    event = make_event(
        event_id="ignored-event-1",
        event_type="Microsoft.Storage.BlobDeleted",
        data={
            "url": (
                "https://nekoblockblastnhom2.blob.core.windows.net/"
                "eventgrid-demo/deleted.txt"
            ),
        },
    )

    with caplog.at_level(logging.INFO):
        blob_upload_eventgrid(event)

    assert "Neko Event Grid ignored: event_id=ignored-event-1" in caplog.text
    assert "Neko Event Grid blob created" not in caplog.text


def test_blob_created_event_with_missing_payload_fields_does_not_crash(caplog):
    event = make_event(event_id="missing-payload-event", data={})

    with caplog.at_level(logging.INFO):
        blob_upload_eventgrid(event)

    assert "Neko Event Grid blob created: event_id=missing-payload-event" in caplog.text
    assert "blob_url=" in caplog.text
    assert "content_type=" in caplog.text
    assert "content_length=None" in caplog.text
