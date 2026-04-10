import os

from backend.database.supabase_client import get_client
from backend.utils.logger import db_logger
from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api", tags=["files"])

ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".csv", ".md"}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
SIGNED_URL_TTL_SECONDS = 60

MIME_TYPES = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".md": "text/markdown",
}


@router.post("/calls/{call_id}/files", status_code=201)
async def upload_file(call_id: str, file: UploadFile = File(...)):
    db_logger.info(f"📥 [Files] Received: upload_file call_id={call_id} filename={file.filename}")
    client = get_client()

    result = client.table("calls").select("id").eq("id", call_id).execute()
    if not result.data:
        db_logger.error(f"❌ [Files] Not found: call_id={call_id}")
        raise HTTPException(status_code=404, detail="Call not found")

    safe_filename = os.path.basename(file.filename or "")
    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"File exceeds 10MB limit ({len(content):,} bytes)",
        )

    storage_path = f"{call_id}/{safe_filename}"
    content_type = MIME_TYPES.get(ext, "application/octet-stream")
    db_logger.info(f"📤 [Storage] Uploading: {storage_path}")
    try:
        client.storage.from_("call-files").upload(
            path=storage_path,
            file=content,
            file_options={"content-type": content_type, "upsert": "false"},
        )
    except Exception as exc:
        db_logger.error(f"❌ [Storage] Upload failed: {storage_path} — {exc}")
        raise HTTPException(status_code=500, detail="Storage upload failed") from exc

    db_logger.info(f"🗄️ [DB] Creating file record for call: {call_id}")
    try:
        record = (
            client.table("call_files")
            .insert(
                {
                    "call_id": call_id,
                    "filename": safe_filename,
                    "storage_path": storage_path,
                    "size_bytes": len(content),
                }
            )
            .execute()
        )
    except Exception as exc:
        db_logger.error(f"❌ [DB] Insert failed, rolling back storage: {storage_path} — {exc}")
        try:
            client.storage.from_("call-files").remove([storage_path])
        except Exception as cleanup_exc:
            db_logger.error(f"❌ [Storage] Rollback failed: {storage_path} — {cleanup_exc}")
        raise HTTPException(status_code=500, detail="Database insert failed") from exc

    db_logger.info(f"✅ [DB] File record created: {record.data[0]['id']}")
    return record.data[0]


@router.get("/calls/{call_id}/files")
async def list_files(call_id: str):
    db_logger.info(f"📥 [Files] Received: list_files call_id={call_id}")
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching files for call: {call_id}")
    result = (
        client.table("call_files")
        .select("*")
        .eq("call_id", call_id)
        .order("created_at")
        .execute()
    )
    db_logger.info(f"✅ [DB] Retrieved {len(result.data)} files")
    return result.data


@router.delete("/calls/{call_id}/files/{file_id}", status_code=204)
async def delete_file(call_id: str, file_id: str):
    db_logger.info(f"📥 [Files] Received: delete_file call_id={call_id} file_id={file_id}")
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching file: {file_id}")
    result = (
        client.table("call_files")
        .select("storage_path")
        .eq("id", file_id)
        .eq("call_id", call_id)
        .execute()
    )
    if not result.data:
        db_logger.error(f"❌ [Files] Not found: file_id={file_id} call_id={call_id}")
        raise HTTPException(status_code=404, detail="File not found")

    storage_path = result.data[0]["storage_path"]
    db_logger.info(f"📤 [Storage] Deleting: {storage_path}")
    try:
        client.storage.from_("call-files").remove([storage_path])
    except Exception as exc:
        db_logger.error(f"❌ [Storage] Delete failed: {storage_path} — {exc}")
        raise HTTPException(status_code=500, detail="Storage delete failed") from exc

    db_logger.info(f"🗄️ [DB] Deleting file record: {file_id}")
    delete_result = client.table("call_files").delete().eq("id", file_id).execute()
    if not delete_result.data:
        db_logger.error(f"❌ [DB] Delete returned no rows: {file_id}")
        raise HTTPException(status_code=500, detail="Database delete failed")
    db_logger.info(f"✅ [DB] File deleted: {file_id}")


@router.get("/calls/{call_id}/files/{file_id}/download")
async def get_download_url(call_id: str, file_id: str):
    db_logger.info(f"📥 [Files] Received: get_download_url call_id={call_id} file_id={file_id}")
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching file for signed URL: {file_id}")
    result = (
        client.table("call_files")
        .select("storage_path")
        .eq("id", file_id)
        .eq("call_id", call_id)
        .execute()
    )
    if not result.data:
        db_logger.error(f"❌ [Files] Not found: file_id={file_id} call_id={call_id}")
        raise HTTPException(status_code=404, detail="File not found")

    storage_path = result.data[0]["storage_path"]
    db_logger.info(f"📤 [Storage] Creating signed URL for: {storage_path}")
    response = client.storage.from_("call-files").create_signed_url(
        path=storage_path, expires_in=SIGNED_URL_TTL_SECONDS
    )
    url = response.get("signedURL") or response.get("signedUrl", "")
    db_logger.info(f"✅ [Storage] Signed URL created")
    return {"url": url}
