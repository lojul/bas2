"""Monitoring routes — LangSmith runs and permanent processing history."""

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.auth import get_current_user

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/runs")
def get_runs(
    hours: int = Query(72, ge=1, le=720),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Get LangSmith processing runs and aggregate token stats."""
    api_key = os.environ.get("LANGCHAIN_API_KEY")
    project_name = os.environ.get("LANGCHAIN_PROJECT", "document-processor")

    if not api_key:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LangSmith not configured (LANGCHAIN_API_KEY missing)",
        )

    from langsmith import Client

    client = Client(api_key=api_key)
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    def _table_storage_fallback(hours: int) -> dict:
        from src.utils.table_storage import list_runs as ts_list_runs
        ts_runs = ts_list_runs(months=1, top=200, hours=hours)
        parsed = [
            {
                "run_id": r.get("row_key", ""),
                "file_name": r["file_name"],
                "document_type": r["document_type"],
                "confidence": 0.0,
                "status": r["status"],
                "extracted_data": r.get("extracted_data", {}),
                "duration_ms": r.get("duration_ms", 0),
                "processed_at": r.get("processed_at"),
            }
            for r in ts_runs
        ]
        return {"runs": parsed, "token_stats": {"total": 0, "prompt": 0, "completion": 0}, "source": "table_storage"}

    try:
        runs_raw = list(
            client.list_runs(
                project_name=project_name,
                filter='eq(name, "process_file")',
                start_time=start_time,
                limit=100,
            )
        )
    except Exception:
        return _table_storage_fallback(hours)

    def _parse_run(run: dict) -> dict:
        from typing import Any
        inputs = run.get("inputs") or {}
        outputs = run.get("outputs") or {}
        file_name = inputs.get("file_name", "Unknown")
        doc_type = "unknown"
        run_status = "error" if run.get("error") else "success"
        extracted_data: dict[str, Any] = {}
        confidence = 0.0

        output = outputs.get("output")
        if output:
            doc_type = output.get("document_type", "unknown") or "unknown"
            confidence = output.get("classification_confidence", 0.0) or 0.0
            extracted = output.get("extracted")
            if extracted:
                extracted_data = extracted.get("raw", {}) or {}
            state_status = output.get("status")
            if state_status and state_status.lower() == "error":
                run_status = "error"
            elif output.get("error_message"):
                run_status = "error"

        start = run.get("start_time")
        end = run.get("end_time")
        duration_ms = 0
        if end and start:
            duration_ms = int((end - start).total_seconds() * 1000)

        return {
            "run_id": run.get("id", ""),
            "file_name": file_name,
            "document_type": doc_type,
            "confidence": confidence,
            "status": run_status,
            "extracted_data": extracted_data,
            "duration_ms": duration_ms,
            "processed_at": start.isoformat() if start and hasattr(start, "isoformat") else str(start) if start else None,
        }

    serializable = [
        {
            "inputs": r.inputs,
            "outputs": r.outputs,
            "error": r.error,
            "start_time": r.start_time,
            "end_time": r.end_time,
            "id": str(r.id),
        }
        for r in runs_raw
        if r.outputs is not None or r.error is not None
    ]

    parsed = [_parse_run(r) for r in serializable]

    if not parsed:
        return _table_storage_fallback(hours)

    try:
        llm_runs = list(
            client.list_runs(
                project_name=project_name,
                filter='eq(run_type, "llm")',
                start_time=start_time,
                limit=100,
            )
        )
    except Exception:
        llm_runs = []

    total_tokens = prompt_tokens = completion_tokens = 0
    for r in llm_runs:
        total = getattr(r, "total_tokens", 0) or 0
        prompt = getattr(r, "prompt_tokens", 0) or 0
        completion = getattr(r, "completion_tokens", 0) or 0
        extra = getattr(r, "extra", {}) or {}
        usage_meta = extra.get("usage_metadata", {})
        if usage_meta:
            total = total or usage_meta.get("total_tokens", 0)
            prompt = prompt or usage_meta.get("input_tokens", 0)
            completion = completion or usage_meta.get("output_tokens", 0)
        total_tokens += total
        prompt_tokens += prompt
        completion_tokens += completion

    return {
        "runs": parsed,
        "token_stats": {"total": total_tokens, "prompt": prompt_tokens, "completion": completion_tokens},
        "source": "langsmith",
    }


@router.get("/history")
def get_history(
    months: int = Query(3, ge=1, le=24),
    top: int = Query(500, ge=1, le=2000),
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """Get permanent processing history from Azure Table Storage."""
    from src.utils.table_storage import list_runs
    runs = list_runs(months=months, top=top)
    return {"runs": runs, "total": len(runs)}
