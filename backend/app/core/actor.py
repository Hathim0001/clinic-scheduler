"""Who is making the current request, for the audit trail.

A context variable rather than a function argument: the HTTP layer sets it once per request and the
code that writes an audit row reads it, so no service method has to carry it. Without staff login
the actor is "anonymous"; code that runs outside a request (the offer sweep) is "system".
"""

from __future__ import annotations

from contextvars import ContextVar

current_actor: ContextVar[str] = ContextVar("current_actor", default="system")
