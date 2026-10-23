import httpx
import pytest

from gracedays.worker_client import WorkerAPIError, WorkerClient


def test_worker_client_adds_shared_secret_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["secret"] = request.headers.get("X-GraceDays-Secret")
        return httpx.Response(200, json={"purchases": []})

    client = WorkerClient("https://worker.example", "test-secret", transport=httpx.MockTransport(handler))
    assert client.list_purchases()["purchases"] == []
    assert seen["secret"] == "test-secret"


def test_worker_client_refuses_writes_when_secret_missing():
    client = WorkerClient("http://127.0.0.1:8787", None, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(WorkerAPIError, match="GRACEDAYS_SHARED_SECRET"):
        client.save_purchase({})


def test_worker_client_surfaces_http_status_and_message():
    client = WorkerClient("https://worker.example", "test-secret", transport=httpx.MockTransport(lambda r: httpx.Response(409, json={"error": "duplicate"})))
    with pytest.raises(WorkerAPIError, match="duplicate") as error:
        client.save_purchase({})
    assert error.value.status_code == 409
