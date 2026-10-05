"""
Declarative registry of where each tool `ads-deploy install`/`pathmunge`
can provision actually comes from.

Both ecosystems are resolved by the *same* pixi-backed mechanism in
install.py -- adding a tool that only exists on conda-forge (a compiler,
Qt, any non-Python dependency) is a one-line entry here, never new install
logic. This is the whole point of using pixi as the backend instead of
uv/pip directly: pip can only ever reach PyPI.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSource:
    ecosystem: str  # "pypi" or "conda"
    package: str  # the package name as published in that ecosystem
    channel: str = "conda-forge"  # only meaningful for ecosystem == "conda"


REGISTRY = {
    "pytmc": ToolSource(ecosystem="pypi", package="pytmc"),
    "make": ToolSource(ecosystem="conda", package="make"),
}


def get_source(tool: str) -> ToolSource:
    try:
        return REGISTRY[tool]
    except KeyError:
        raise ValueError(
            f"Unknown tool {tool!r}. Add it to ads_deploy/tool_registry.py's "
            "REGISTRY with its ecosystem ('pypi' or 'conda') and package name."
        ) from None
