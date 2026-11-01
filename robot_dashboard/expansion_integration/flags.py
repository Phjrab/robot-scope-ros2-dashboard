"""Server-owned opt-ins; absent or unrecognized values stay disabled."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ExpansionFlags:
    multimap: bool = False
    scene: bool = False
    replay: bool = False
    usability: bool = False
    runtime: bool = False

    @classmethod
    def from_environ(cls, environ):
        return cls(**{name: environ.get(f"ROBOT_SCOPE_EXPANSION_{name.upper()}") == "1"
                      for name in cls.__dataclass_fields__})

    @property
    def enabled(self):
        return self.multimap or self.scene or self.replay

    def public(self):
        return {**asdict(self), "native": False, "protection_mode": "ADVISORY_ONLY"}
