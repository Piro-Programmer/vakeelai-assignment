"""
Typed exceptions for the eCourts scraper.

Why typed exceptions instead of returning error dicts?
The portal reports nearly every failure as HTTP 200 with an `errormsg` field,
and "Invalid Captcha" (retryable) looks the same as "Record not found" (final).
Each failure mode gets its own class, so the service layer can choose:
retry the captcha, rebuild the session, or show the user a clean message.
The API layer then maps each class to one HTTP status in a single place.
"""


class EcourtsError(Exception):
    """Base class: something went wrong talking to the portal."""

    http_status = 502

    def __init__(self, message: str = "", *, detail: str | None = None):
        super().__init__(message or self.__class__.__doc__)
        self.message = message or (self.__class__.__doc__ or "").strip()
        self.detail = detail


class CaptchaError(EcourtsError):
    """The portal rejected the captcha answer."""

    http_status = 422


class SessionExpired(EcourtsError):
    """The portal session or app_token is no longer valid."""

    http_status = 440


class CaseNotFound(EcourtsError):
    """No case matches the given search parameters."""

    http_status = 404


class InvalidInput(EcourtsError):
    """User input failed validation before we touched the network."""

    http_status = 400


class PortalUnavailable(EcourtsError):
    """The portal is down, slow, or blocking us (network/5xx/non-JSON)."""

    http_status = 503
