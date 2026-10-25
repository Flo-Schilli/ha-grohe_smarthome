"""Recover from a rejected access token by logging in again once."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from weakref import WeakKeyDictionary

from grohe import GroheClient, GroheUnauthorizedError

_LOGGER = logging.getLogger(__name__)

# All coordinators of one config entry share a single GroheClient. When its token
# goes stale they all fail in the same polling round, and only one of them should
# log in again - the others just retry with the fresh token.
_login_locks: WeakKeyDictionary[GroheClient, asyncio.Lock] = WeakKeyDictionary()


async def fetch_with_relogin[T](
    api: GroheClient, fetch: Callable[[], Awaitable[T]]
) -> T:
    """Run fetch(); on a rejected token, log in again and retry exactly once.

    A 401 does not mean the credentials are wrong. The grohe library tracks token
    expiry with naive local datetime.now(), so when the clock falls back an hour at
    the end of daylight saving time it keeps sending an access token Grohe has
    already expired. Raising ConfigEntryAuthFailed straight away for that turned a
    stale token into a reauth flow and stopped all polling until the user acted.

    GroheUnauthorizedError still propagates when the new login itself is rejected
    or the retry fails with the fresh token, so a real credential problem is
    reported exactly as before.
    """
    token_before = api.access_token
    try:
        return await fetch()
    except GroheUnauthorizedError as err:
        lock = _login_locks.setdefault(api, asyncio.Lock())
        async with lock:
            if api.access_token == token_before:
                _LOGGER.warning(
                    "Grohe rejected the access token (%s), logging in again", err
                )
                await api.login()
    return await fetch()
