"""jobpilot - track job applications from raw posting text."""

from .extract import JobPosting, parse_heuristic, parse_with_llm

__all__ = ["JobPosting", "parse_heuristic", "parse_with_llm", "__version__"]
__version__ = "0.1.0"
