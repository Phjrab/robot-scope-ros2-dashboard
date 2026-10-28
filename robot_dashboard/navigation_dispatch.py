"""Internal final-consumer rejection receipt shared by navigation adapters."""


class OperatorDispatchRejected(ValueError):
    """The final consumer rejected a permission before action submission."""
