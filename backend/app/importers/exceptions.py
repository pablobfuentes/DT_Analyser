class ImporterError(Exception):
    """Base importer error."""

    error_code: str = "IMPORTER_ERROR"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        result = {"error": self.error_code, "message": self.message}
        result.update(self.details)
        return result


class UnknownCSVFormatError(ImporterError):
    error_code = "UNKNOWN_FORMAT"


class MissingRequiredColumnError(ImporterError):
    error_code = "MISSING_REQUIRED_COLUMN"


class AmbiguousColumnError(ImporterError):
    error_code = "AMBIGUOUS_COLUMN"


class TimezoneRequiredError(ImporterError):
    error_code = "TIMEZONE_REQUIRED"

    def __init__(self, message: str = "The CSV timestamps do not include timezone information."):
        super().__init__(
            message,
            options=["America/New_York", "America/Mexico_City", "UTC"],
        )


class TradeReconstructionError(ImporterError):
    error_code = "TRADE_RECONSTRUCTION_ERROR"


class InvalidExecutionError(ImporterError):
    error_code = "INVALID_EXECUTION"
