"""Keep SQLite and documents together, independent of the code checkout."""
import os
from pathlib import Path


def data_root(code_root):
    configured = os.getenv('DMS_DATA_DIR', '').strip()
    if not configured:
        return Path(code_root).resolve()
    root = Path(configured).expanduser()
    if not root.is_absolute():
        raise ValueError('DMS_DATA_DIR must be an absolute persistent-disk path.')
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()
