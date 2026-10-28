"""Log a streak of denied requests once when it starts and once when it ends."""

import logging


class DenyStreakLog:
    """Grohe denies requests for hours at a time, so log each streak, not each poll.

    Works like DataUpdateCoordinator's own logging of failed updates: the first
    denial is a warning, repeats only show up at debug level, and the first
    successful update afterwards logs that requests are accepted again.
    """

    def __init__(self, logger: logging.Logger, subject: str) -> None:
        self._logger = logger
        self._subject = subject
        self._denied = False

    def denied(self, err: Exception) -> None:
        if self._denied:
            self._logger.debug(
                "Grohe still denies the request for %s: %s", self._subject, err
            )
            return
        self._denied = True
        self._logger.warning(
            "Grohe denied the request for %s, keeping last known data: %s",
            self._subject,
            err,
        )

    def accepted(self) -> None:
        if self._denied:
            self._denied = False
            self._logger.info("Grohe accepts requests for %s again", self._subject)
