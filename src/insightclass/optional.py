from __future__ import annotations

from importlib.util import find_spec

from insightclass.exceptions import DependencyMissingError


def has_package(package_name: str) -> bool:
    return find_spec(package_name) is not None


def require_package(package_name: str, feature: str) -> None:
    if not has_package(package_name):
        raise DependencyMissingError(
            f"{feature} requires optional dependency '{package_name}'. "
            f"Please install it in the active environment first."
        )
