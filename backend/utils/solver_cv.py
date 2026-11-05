"""Resolve only existing CV files inside the configured private storage root."""
import os
from pathlib import Path


def available_cv_path(record, root=None):
    value = (record or {}).get('cv_path')
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        storage = Path(root or os.environ.get('CV_UPLOAD_ROOT', '/app/backend/uploads/solver_cvs')).resolve()
        path = Path(value).resolve()
        return path if path.is_relative_to(storage) and path.is_file() else None
    except (OSError, ValueError, RuntimeError):
        return None
