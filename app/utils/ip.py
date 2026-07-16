from fastapi import Request


def get_client_ip(request: Request) -> str:
    """
    Best-guess client IP. Render and Vercel both sit in front of the
    app as reverse proxies, so the real client IP arrives via the
    X-Forwarded-For header rather than request.client.host.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Can be a comma-separated chain (client, proxy1, proxy2...);
        # the first entry is the original client.
        return forwarded.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"
