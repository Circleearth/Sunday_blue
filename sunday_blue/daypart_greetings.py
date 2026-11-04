"""Legacy API compatibility; application loads the external package at runtime."""
from .plugin_runtime import load
Greetings=load('daypart-greetings').Greetings
period_at=load('daypart-greetings').period_at
PERIODS=load('daypart-greetings').PERIODS
