"""HTTP API and the host for the PWA: `create_app` builds it, `API_VERSION` is the
version the app compares with the one it was built for."""
from amonhen.api.app import create_app
from amonhen.api.version import API_VERSION

__all__ = ["API_VERSION", "create_app"]
