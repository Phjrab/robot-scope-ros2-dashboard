"""Offline multimap numerical core; importing starts no workers or IO."""

from .solver import solve, source_key


def export(proposal, expected_revision, resolver, output_root):
    from .exporter import export as implementation

    return implementation(proposal, expected_revision, resolver, output_root)


__all__ = ["solve", "export", "source_key"]
