class InsightClassError(Exception):
    """Base project exception."""


class DependencyMissingError(InsightClassError):
    """Raised when an optional dependency is required but unavailable."""


class ConfigError(InsightClassError):
    """Raised when a config file is invalid."""
