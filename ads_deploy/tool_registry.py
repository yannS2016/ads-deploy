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
    extra_pypi: tuple = ()  # extra, unpinned PyPI deps; only meaningful for ecosystem == "pypi"
    # Prepended to a version resolved from upstream (e.g. by `ads-deploy
    # install <tool>` with no version -- see install.py's
    # _resolve_latest_version) before it's used as a directory/pin name.
    # pytmc's own ecosystem (PyPI) never reports a "v" itself, but every
    # existing pytmc toolenv directory is named "v2.22.1"-style, matching
    # its GitHub release tags -- without this, an auto-resolved "latest"
    # would land in a second, differently-named directory ("2.22.1") next
    # to an existing "v2.22.1" install of the identical release.
    version_prefix: str = ""


REGISTRY = {
    # qtpy + PySide6: `pytmc debug` is a Qt GUI tool (pytmc/bin/debug.py
    # imports qtpy/QtWidgets) -- a plain `pip install pytmc` doesn't pull in
    # a Qt binding, so pytmc's own CLI dispatcher (pytmc/bin/pytmc.py)
    # silently drops the `debug` subcommand when the import fails
    # (confirmed directly: "invalid choice: 'debug'", not an import error --
    # it's swallowed). The old conda environment had a Qt binding present
    # as a side effect of its much larger dependency set; this restores
    # that, deliberately, for this one tool. PySide6 (not PyQt5/6) to avoid
    # GPL licensing -- qtpy supports either as a backend transparently.
    "pytmc": ToolSource(
        ecosystem="pypi",
        package="pytmc",
        extra_pypi=("qtpy", "PySide6"),
        version_prefix="v",
    ),
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
