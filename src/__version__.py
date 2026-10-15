"""
Single source of truth for the application version.

Every layer (FastAPI metadata, Docker labels, CI release verification,
Prometheus build_info metric, health endpoints) reads from here.
Never hardcode version strings anywhere else.
"""

__title__ = "customer-support-chatbot"
__description__ = "Production RAG-based Customer Support Chatbot"
__version__ = "1.1.0"
__author__ = "Adil Shamim"
__author_email__ = "157037615+AdilShamim8@users.noreply.github.com"
__license__ = "MIT"
__url__ = "https://github.com/AdilShamim8/Customer-Support-Chatbot-102"
__build_date__ = "2026-10-15"

# Machine-readable build info surfaced by /health and Prometheus.
BUILD_INFO: dict[str, str] = {
    "version": __version__,
    "build_date": __build_date__,
    "title": __title__,
}
