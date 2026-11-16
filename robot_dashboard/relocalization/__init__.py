"""Offline relocalization contracts; no ROS or HTTP ownership lives here."""

from .models import RegistrationRequest, RegistrationResultSet


def __getattr__(name):
    # Numerical consumers do not need POSIX process supervision or live adapters.
    if name == "StationaryRelocalizationManager":
        from .manager import StationaryRelocalizationManager

        return StationaryRelocalizationManager
    if name == "OfflineRegistrationProcess":
        from .process_adapter import OfflineRegistrationProcess

        return OfflineRegistrationProcess
    raise AttributeError(name)


__all__ = [
    "OfflineRegistrationProcess",
    "RegistrationRequest",
    "RegistrationResultSet",
    "StationaryRelocalizationManager",
]
