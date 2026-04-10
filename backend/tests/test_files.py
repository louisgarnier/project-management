from unittest.mock import MagicMock, patch

from backend.main import app
from starlette.testclient import TestClient

client = TestClient(app)

CALL_ID = "call-123"
FILE_ID = "file-abc"

MOCK_CALL = {"id": CALL_ID}
MOCK_FILE_RECORD = {
    "id": FILE_ID,
    "call_id": CALL_ID,
    "filename": "notes.txt",
    "storage_path": f"{CALL_ID}/notes.txt",
    "size_bytes": 11,
    "created_at": "2026-04-10T00:00:00Z",
}


def _mc():
    return MagicMock()


def test_upload_file_happy_path():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[MOCK_CALL]
    )
    mc.storage.from_.return_value.upload.return_value = MagicMock()
    mc.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[MOCK_FILE_RECORD]
    )
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.post(
            f"/api/calls/{CALL_ID}/files",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )
    assert r.status_code == 201
    assert r.json()["filename"] == "notes.txt"
    assert r.json()["call_id"] == CALL_ID


def test_upload_file_returns_404_when_call_missing():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.post(
            "/api/calls/nonexistent/files",
            files={"file": ("notes.txt", b"content", "text/plain")},
        )
    assert r.status_code == 404


def test_upload_file_rejects_wrong_extension():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[MOCK_CALL]
    )
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.post(
            f"/api/calls/{CALL_ID}/files",
            files={"file": ("photo.jpg", b"binary", "image/jpeg")},
        )
    assert r.status_code == 422
    assert ".jpg" in r.json()["detail"]


def test_upload_file_rejects_oversized_file():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[MOCK_CALL]
    )
    big = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.post(
            f"/api/calls/{CALL_ID}/files",
            files={"file": ("big.txt", big, "text/plain")},
        )
    assert r.status_code == 422
    assert "10MB" in r.json()["detail"]


def test_list_files_returns_files():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[MOCK_FILE_RECORD]
    )
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.get(f"/api/calls/{CALL_ID}/files")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["filename"] == "notes.txt"


def test_list_files_returns_empty_for_new_call():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[]
    )
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.get(f"/api/calls/{CALL_ID}/files")
    assert r.status_code == 200
    assert r.json() == []


def test_delete_file_happy_path():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[MOCK_FILE_RECORD]
    )
    mc.storage.from_.return_value.remove.return_value = MagicMock()
    mc.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.delete(f"/api/calls/{CALL_ID}/files/{FILE_ID}")
    assert r.status_code == 204


def test_delete_file_returns_404_when_missing():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.delete(f"/api/calls/{CALL_ID}/files/nonexistent")
    assert r.status_code == 404


def test_get_download_url_happy_path():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[MOCK_FILE_RECORD]
    )
    mc.storage.from_.return_value.create_signed_url.return_value = {
        "signedURL": "https://example.com/signed"
    }
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.get(f"/api/calls/{CALL_ID}/files/{FILE_ID}/download")
    assert r.status_code == 200
    assert r.json()["url"] == "https://example.com/signed"


def test_get_download_url_returns_404_when_missing():
    mc = _mc()
    mc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    with patch("backend.routers.files.get_client", return_value=mc):
        r = client.get(f"/api/calls/{CALL_ID}/files/nonexistent/download")
    assert r.status_code == 404
