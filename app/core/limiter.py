from slowapi import Limiter
from slowapi.util import get_remote_address

# Keyed by client IP. Shared across the whole app — import this same
# `limiter` instance anywhere you want to rate-limit a route.
limiter = Limiter(key_func=get_remote_address)
