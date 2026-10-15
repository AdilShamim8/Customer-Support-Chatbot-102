"""
Top-level source package for the customer support chatbot.

Exposes the version single-source-of-truth so any module (and the FastAPI
app factory) can do `from src import __version__`.
"""

from src.__version__ import (  # noqa: F401
    BUILD_INFO,
    __author__,
    __build_date__,
    __license__,
    __title__,
    __version__,
)

__all__ = [
    "__version__",
    "__title__",
    "__build_date__",
    "__license__",
    "__author__",
    "BUILD_INFO",
]
