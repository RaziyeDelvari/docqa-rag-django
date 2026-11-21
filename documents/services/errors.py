"""Domain errors. Each one carries the HTTP status the API should return."""


class ServiceError(Exception):
    status_code = 500


class DocxError(ServiceError):
    status_code = 400


class EmptyDocumentError(ServiceError):
    status_code = 400


class LLMConfigError(ServiceError):
    status_code = 503


class LLMCallError(ServiceError):
    status_code = 502


class RetrievalError(ServiceError):
    status_code = 502


class IndexingError(ServiceError):
    status_code = 502
