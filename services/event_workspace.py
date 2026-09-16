"""Disposable event files, isolated from application and historical data."""
from pathlib import Path
import shutil


def workspace_path(db_path, event_id):
    if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id <= 0:
        raise ValueError("Event ID must be a positive integer.")
    root = Path(db_path).resolve().parent / "runtime"
    # Do not follow redirected roots or workspaces (including Windows junctions).
    target = root / f"event_{event_id}"
    if root.resolve() != root or target.resolve() != target:
        raise ValueError("Runtime workspace must not be redirected.")
    if not target.resolve().is_relative_to(root):
        raise ValueError("Workspace is outside the runtime root.")
    return target


def create_workspace(db_path, event_id):
    workspace = workspace_path(db_path, event_id)
    for name in ("uploads", "outputs", "temp"):
        folder = workspace / name
        if folder.resolve() != folder:
            raise ValueError("Runtime folders must not be redirected.")
        folder.mkdir(parents=True, exist_ok=True)
    return workspace


def output_path(db_path, event_id, filename):
    if not filename or Path(filename).name != filename or filename in (".", "..") or ":" in filename or "\\" in filename:
        raise ValueError("Output filename must be a plain filename.")
    path = workspace_path(db_path, event_id) / "outputs" / filename
    if path.resolve() != path:
        raise ValueError("Output path must not be redirected.")
    return path


def save_output(db_path, event_id, filename, content):
    path = output_path(db_path, event_id, filename)
    create_workspace(db_path, event_id)
    if hasattr(content, "getvalue"):
        content = content.getvalue()
    if isinstance(content, str):
        content = content.encode("utf-8")
    path.write_bytes(content)
    return path


def cleanup_workspace(db_path, event_id):
    """Remove only this event's validated directory and invalidate downloads."""
    from database.db import get_conn
    workspace = workspace_path(db_path, event_id)
    # Refuse redirected descendants before recursive deletion as well.
    if workspace.exists():
        for path in workspace.rglob("*"):
            if path.resolve() != path:
                raise ValueError("Runtime files must not be redirected.")
        shutil.rmtree(workspace)
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM event_outputs WHERE event_id=?", (event_id,))
        conn.execute("UPDATE events SET exports_revision=NULL WHERE id=?", (event_id,))
