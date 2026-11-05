"""
Table definitions for every medallion layer.
"""

from firms_ua.datacatalog.base import Column, Table
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.errors import SchemaError

__all__ = ["Column", "FirmsBronze", "SchemaError", "Table"]
