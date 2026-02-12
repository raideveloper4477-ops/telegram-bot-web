import time
from collections import defaultdict
from flask import request, session

# Rate limiting
rate_limit_storage = defaultdict(list)
RATE_LIMIT = 5  # requests per 10 seconds
RATE_WINDOW = 10

def rate_limit(key_func=None):
    def decorator(f):
        def wrapped(*args, **kwargs):
            key = key_func() if key_func else request.remote_addr
            now = time.time()
            window = rate_limit_storage[key]
            # Keep only recent requests
            window[:] = [t for t in window if t > now - RATE_WINDOW]
            if len(window) >= RATE_LIMIT:
                return {'error': 'Rate limit exceeded'}, 429
            window.append(now)
            return f(*args, **kwargs)
        return wrapped
    return decorator

def sanitize_input(text):
    """Basic sanitization for command input."""
    if not text:
        return text
    # Remove dangerous characters
    dangerous = [';', '&', '|', '`', '$', '(', ')', '{', '}', '<', '>']
    for ch in dangerous:
        text = text.replace(ch, '')
    return text[:200]  # Limit length

def check_spam_logs(logs, threshold=100, window=60):
    """Detect if more than threshold lines in last window seconds."""
    now = time.time()
    recent = [ts for ts in logs if now - ts < window]
    return len(recent) > threshold