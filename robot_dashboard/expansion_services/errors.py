"""Stable public service errors; exception text is always private.

Existing HTTP statuses and string detail remain compatible. Codes/messages are
fixed here, never derived from paths, solver output or resolver exceptions.
"""

from robot_dashboard.expansion_contracts import ContractError
from robot_dashboard.pcd_editing.geometry import PcdEditError


MESSAGES = {
    "ANCESTRY_OVERLAP": "Selected maps share original sources and cannot be merged together.",
    "INVALID_PROVENANCE": "Source ancestry is inconsistent. Refresh the source catalogue.",
    "STALE_SOURCE_REVISION": "A source revision changed. Refresh the sources and solve again.",
    "SOURCE_IDENTITY_MISMATCH": "Source identity does not match the pinned source.",
    "SOURCE_CONTENT_CHANGED": "Source content changed. Refresh the sources and solve again.",
    "SOURCE_DESCRIPTOR_CHANGED": "Source metadata changed. Refresh the sources and solve again.",
    "STALE_PROPOSAL_REVISION": "The proposal revision changed. Refresh the job before reviewing or saving.",
    "REQUEST_CONFLICT": "The request conflicts with the current job or saved result.",
    "SERVICE_BUSY": "Bounded worker capacity is unavailable. Try again later.",
    "NOT_FOUND": "The requested candidate was not found.",
    "INVALID_CONTRACT": "The candidate does not satisfy the bounded service contract.",
    "STORAGE_UNAVAILABLE": "Private candidate storage is unavailable. Try again later.",
    "JOB_FAILED": "The fusion job failed. No result was published.",
    "INTERNAL_ERROR": "The service could not complete the request.",
}


class Conflict(ContractError):
    def __init__(self, message, *, code="REQUEST_CONFLICT"):
        if code not in MESSAGES:
            raise ValueError("unknown service error code")
        super().__init__(message)
        self.code = code


class Busy(Conflict):
    pass


def public_error(exc, *, worker=False):
    if isinstance(exc, Busy):
        status, code = 429, "SERVICE_BUSY"
    elif isinstance(exc, Conflict):
        status, code = 409, exc.code
    elif isinstance(exc, (FileNotFoundError, KeyError)):
        status, code = 404, "NOT_FOUND"
    elif isinstance(exc, (ContractError, PcdEditError, TypeError)):
        status, code = 422, "INVALID_CONTRACT"
    elif isinstance(exc, OSError):
        status, code = 503, "STORAGE_UNAVAILABLE"
    else:
        status, code = 500, "JOB_FAILED" if worker else "INTERNAL_ERROR"
    return status, {"code": code, "message": MESSAGES[code]}
