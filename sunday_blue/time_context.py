"""Compatibility import for the independent time plugin."""
from .plugin_runtime import load
def time_context(moment=None):return load('time-context').time_context(moment)
