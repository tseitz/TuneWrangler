"""Stop the run when a gate sends the page to a sign-in or sign-up screen.

A login is the one thing this automation must never attempt. It holds no password, and
hunting for a way past one walks it off the gate entirely: a droploud run reached Google's
sign-in form, typed into it, and finished on a recaptcha. Stop instead and leave the tab
open. A human signs in once; the saved session makes every later run ordinary.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Matched against the path only. A gate's own page can legitimately contain the word
# "login" in a nav link, so the check never looks at page text — only at where we landed.
_LOGIN_PATHS: tuple[str, ...] = (
    "/login",
    "/log-in",
    "/signin",
    "/sign-in",
    "/signup",
    "/sign-up",
    "/register",
    "/auth/",
    "/oauth/authorize",
    "/account/login",
)

# Paths that are a sign-in only on one host. pl8list's email-code login lives at /verify,
# which elsewhere is as likely to be an ordinary gate step.
_HOST_LOGIN_PATHS: tuple[tuple[str, str], ...] = (("pl8list.com", "/verify"),)


class LoginWallEncountered(RuntimeError):  # noqa: N818
    """Raised when the driven page lands on a login, signup, or off-gate host."""

    def __init__(self, url: str, reason: str, gate_name: str) -> None:
        self.url = url
        self.reason = reason
        self.gate_name = gate_name
        super().__init__(f"[{gate_name}] {reason} — {url}")


def normalize_host(url: str) -> str:
    """Return the comparable host for a URL: lowercased, no port, no leading www."""
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def same_site(current_url: str, gate_host: str) -> bool:
    """True if the URL is on the gate's host or a subdomain of it (either direction)."""
    host = normalize_host(current_url)
    if not host or not gate_host:
        return True
    return host == gate_host or host.endswith("." + gate_host) or gate_host.endswith("." + host)


def detect_login_wall(current_url: str, gate_host: str) -> str | None:
    """Return why this URL is a stop, or None to carry on.

    Leaving the gate's host is itself the signal. Identity providers do not share a
    domain with the gate, so the host check catches a sign-in redirect without having to
    recognise each provider by name.
    """
    # No anchor means the run has not established where the gate lives, and every check
    # below would be measuring against nothing.
    if not gate_host or not current_url or current_url.startswith(("about:", "chrome:")):
        return None
    if not same_site(current_url, gate_host):
        return f"left the gate for {normalize_host(current_url)}"
    path = (urlparse(current_url).path or "").lower()
    host_paths = [p for host, p in _HOST_LOGIN_PATHS if same_site(current_url, host)]
    if any(path.startswith(p) or f"{p}/" in path for p in (*_LOGIN_PATHS, *host_paths)):
        return "the gate asked us to sign in"
    return None
