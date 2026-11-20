"""Django-facing adapter for the repository's DFS client."""
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class DfsUnavailable(Exception):
    """Raised when the DFS cannot complete a report operation."""


class DfsReportNotFound(DfsUnavailable):
    """Raised when no committed DFS report exists for an identifier."""


def store_report(file_id, content):
    """Store report bytes in DFS and return the committed file identifier."""
    try:
        from dfs_client import DfsClientError, store_bytes
    except ImportError as error:
        raise DfsUnavailable("Distributed report storage is unavailable.") from error

    try:
        return store_bytes(file_id, content)
    except DfsClientError as error:
        raise DfsUnavailable("Distributed report storage is unavailable.") from error


def read_report(file_id):
    """Retrieve report bytes from DFS after verifying their checksums."""
    try:
        from dfs_client import DfsClientError, DfsFileNotFound, fetch_bytes
    except ImportError as error:
        raise DfsUnavailable("Distributed report storage is unavailable.") from error

    try:
        return fetch_bytes(file_id)
    except DfsFileNotFound as error:
        raise DfsReportNotFound from error
    except DfsClientError as error:
        raise DfsUnavailable("Distributed report storage is unavailable.") from error
