"""
Project-wide errors.
"""


class FirmsError(Exception):
    """
    Non-retryable FIRMS failure; `http_status` is set when a response was received.
    """

    def __init__(self, message: str, http_status: int | None = None) -> None:
        """
        Keep the message (never containing the MAP_KEY) and the HTTP status, if any.
        """
        super().__init__(message)
        self.http_status = http_status


class SchemaError(ValueError):
    """
    A dataframe does not match its table definition.
    """


class DataError(ValueError):
    """
    Input data breaks an expectation: an unknown label, a value that does not parse, an inconsistent row.
    """
