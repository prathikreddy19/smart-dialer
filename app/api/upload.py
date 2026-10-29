from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..services.csv_import_service import (
    IMPORT_ORDER,
    ImportConflictError,
    ImportDatabaseError,
    ImportValidationError,
    import_csv,
)

router = APIRouter(prefix="/upload", tags=["Dataset Upload"])


@router.post("/dataset")
def upload_dataset(
    vendor_telephony: UploadFile = File(...),
    campaigns: UploadFile = File(...),
    borrowers: UploadFile = File(...),
    agents: UploadFile = File(...),
    calls: UploadFile = File(...),
    call_attempts: UploadFile = File(...),
    agent_sessions: UploadFile = File(...),
):
    uploads = {
        "vendor_telephony.csv": vendor_telephony,
        "campaigns.csv": campaigns,
        "borrowers.csv": borrowers,
        "agents.csv": agents,
        "calls.csv": calls,
        "call_attempts.csv": call_attempts,
        "agent_sessions.csv": agent_sessions,
    }
    completed = []
    current_file = None

    try:
        for dataset_name in IMPORT_ORDER:
            upload = uploads[dataset_name]
            if not upload.filename or Path(upload.filename).suffix.casefold() != ".csv":
                raise HTTPException(
                    status_code=400,
                    detail=f"{dataset_name} must be uploaded as a CSV file.",
                )

        with TemporaryDirectory(prefix="smart-dialer-upload-") as temp_dir:
            for dataset_name in IMPORT_ORDER:
                current_file = dataset_name
                upload = uploads[dataset_name]
                contents = upload.file.read()
                if not contents:
                    raise ImportValidationError(f"{dataset_name}: uploaded file is empty.")
                path = Path(temp_dir) / dataset_name
                path.write_bytes(contents)
                report = import_csv(path)
                completed.append(report.to_dict())

        return {
            "status": "success",
            "message": "All datasets imported successfully.",
            "files": completed,
        }
    except ImportConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "failed_file": current_file,
                "completed_files": completed,
            },
        ) from exc
    except ImportValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "failed_file": current_file,
                "completed_files": completed,
            },
        ) from exc
    except ImportDatabaseError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "failed_file": current_file,
                "completed_files": completed,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Dataset upload failed.",
                "failed_file": current_file,
                "completed_files": completed,
            },
        ) from exc
    finally:
        for upload in uploads.values():
            upload.file.close()
