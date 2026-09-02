"""Validation for episode URIs relative to a runtime data root."""

from pathlib import PureWindowsPath
from posixpath import normpath
from typing import NewType

DataRootRelativeUri = NewType("DataRootRelativeUri", str)


def parse_data_root_relative_uri(uri: str) -> DataRootRelativeUri:
    """Trim and validate one URI before a runtime can resolve it.

    The returned value keeps safe internal segments such as ``a/../b``
    unchanged. Only surrounding whitespace is normalized; the parser rejects
    paths that are empty, anchored, or escape above the data root.
    """
    if not isinstance(uri, str):
        raise ValueError("ingest URI must be a string")

    candidate = uri.strip()
    if not candidate:
        raise ValueError("every uri must be a non-empty string")
    windows_path = PureWindowsPath(candidate)
    if candidate.startswith("/") or windows_path.anchor:
        raise ValueError(f"{candidate!r} is not relative to the data root")

    # URI separators are POSIX-style, but accepting a Windows spelling on one
    # machine must not turn into a parent escape on another. Preserve the
    # candidate itself; normalize only this containment check.
    normalized = normpath(candidate.replace("\\", "/"))
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError(f"{candidate!r} is not relative to the data root")

    return DataRootRelativeUri(candidate)
