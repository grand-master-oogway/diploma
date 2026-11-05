"""
Project-wide errors.
"""


class FirmsError(Exception):
    """
    Non-retryable FIRMS failure.
    """


class SchemaError(ValueError):
    """
    A dataframe does not match its table definition.
    """
