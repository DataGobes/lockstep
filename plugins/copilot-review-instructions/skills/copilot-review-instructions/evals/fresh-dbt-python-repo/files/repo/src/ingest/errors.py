class IngestError(Exception):
    """Base error for ingestion failures. Loaders raise subclasses, never bare Exception."""


class SourceUnavailableError(IngestError):
    """The upstream API could not be reached after retries."""


class SchemaDriftError(IngestError):
    """The payload no longer matches the expected landing schema."""
