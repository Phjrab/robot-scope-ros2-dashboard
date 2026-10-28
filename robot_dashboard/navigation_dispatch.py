"""Internal final-consumer rejection receipt shared by navigation adapters."""


class OperatorDispatchRejected(ValueError):
    """A guarded goal was proven rejected before action submission."""
