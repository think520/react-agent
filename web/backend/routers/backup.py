"""Full-library backup, verification, and restore endpoints (W4-RESTORE-01)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from service.backup_service import BackupService
from web.backend.deps import get_library_service, get_workspace, reset_dependency_caches
from web.backend.errors import APIError, unwrap_service_result

router = APIRouter()


class CreateBackupRequest(BaseModel):
    include_global: bool = True


def _resolve_backup_workspace(request: Request) -> str:
    """Resolve the library workspace for backup creation/planning strictly by header or active library."""
    service = get_library_service()
    registry = service.list_libraries()
    if not registry["libraries"]:
        return get_workspace()
    library_id = request.headers.get("X-Bobodan-Library-ID")
    try:
        record = service.resolve(library_id)
    except ValueError as exc:
        raise APIError(409, "library_unavailable", str(exc)) from exc
    if record is None:
        raise APIError(409, "library_required", "请先选择要备份的资料库。")
    return record["path"]


def _public_backup_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in result.items()
        if key not in {"ok", "archive_path"}
    }


async def _write_upload_to_temp(upload: UploadFile) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="bobodan-backup-upload-", suffix=".zip")
    os.close(fd)
    temp_path = Path(raw_path)
    try:
        with temp_path.open("wb") as handle:
            while True:
                chunk = await upload.read(65536)
                if not chunk:
                    break
                handle.write(chunk)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


@router.get("/plan")
def backup_plan(request: Request, include_global: bool = True) -> dict[str, Any]:
    workspace = _resolve_backup_workspace(request)
    result = unwrap_service_result(BackupService().plan(workspace, include_global=include_global))
    return {key: value for key, value in result.items() if key != "ok"}


@router.get("/list")
def list_backups() -> dict[str, Any]:
    result = unwrap_service_result(BackupService().list_backups())
    return {"backups": result["backups"]}


@router.post("/create")
def create_backup(request: Request, body: CreateBackupRequest) -> dict[str, Any]:
    workspace = _resolve_backup_workspace(request)
    result = unwrap_service_result(
        BackupService().create_backup(workspace, include_global=body.include_global)
    )
    return _public_backup_result(result)


@router.get("/download/{backup_id}")
def download_backup(backup_id: str) -> FileResponse:
    path = BackupService().resolve_backup_file(backup_id)
    if path is None:
        raise APIError(404, "backup_not_found", "找不到指定的备份文件。")
    return FileResponse(
        path=str(path),
        media_type="application/zip",
        filename=path.name,
    )


@router.post("/verify")
async def verify_backup(
    file: UploadFile | None = File(default=None),
    backup_id: str | None = Form(default=None),
) -> dict[str, Any]:
    service = BackupService()
    temp_path: Path | None = None
    try:
        if file is not None:
            temp_path = await _write_upload_to_temp(file)
            target_archive = temp_path
        elif backup_id:
            resolved = service.resolve_backup_file(backup_id)
            if resolved is None:
                raise APIError(404, "backup_not_found", "找不到指定的备份文件。")
            target_archive = resolved
        else:
            raise APIError(400, "invalid_request", "请上传备份文件或指定 backup_id。")

        result = unwrap_service_result(service.verify_backup(str(target_archive)))
        return {key: value for key, value in result.items() if key != "ok"}
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.post("/restore")
async def restore_backup(
    target_dir: str = Form(...),
    restore_global: bool = Form(default=False),
    activate: bool = Form(default=True),
    new_library_id: bool = Form(default=False),
    file: UploadFile | None = File(default=None),
    backup_id: str | None = Form(default=None),
) -> dict[str, Any]:
    service = BackupService()
    temp_path: Path | None = None
    try:
        if file is not None:
            temp_path = await _write_upload_to_temp(file)
            target_archive = temp_path
        elif backup_id:
            resolved = service.resolve_backup_file(backup_id)
            if resolved is None:
                raise APIError(404, "backup_not_found", "找不到指定的备份文件。")
            target_archive = resolved
        else:
            raise APIError(400, "invalid_request", "请上传备份文件或指定 backup_id。")

        result = unwrap_service_result(
            service.restore_backup(
                str(target_archive),
                target_dir,
                restore_global=restore_global,
                activate=activate,
                new_library_id=new_library_id,
            )
        )
        reset_dependency_caches()
        return {key: value for key, value in result.items() if key != "ok"}
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
