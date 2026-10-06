"""Prodigy loads this object entry point only when a DB connection is requested.

Its database registry expects an instance, unlike its recipe factory registry.
Keep connection setup out of the reusable adapter module.
"""

from .database import connect_existing

database = connect_existing()
