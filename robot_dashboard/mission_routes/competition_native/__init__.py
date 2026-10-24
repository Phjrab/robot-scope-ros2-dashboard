"""Disabled-by-default native action boundary; importing creates no owner."""
from .adapter import NativeActionAdapter
from .contracts import Activation, Scope, TimingPolicy

__all__ = ["Activation", "NativeActionAdapter", "Scope", "TimingPolicy"]
