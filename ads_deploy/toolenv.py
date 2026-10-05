"""
Shared helpers for locating the isolated, immutable per-(tool, version)
pixi-managed environments that `ads-deploy install` creates and
`ads-deploy pathmunge` / `ads-deploy versions` read back.
"""

import logging
import os
import pathlib
import sys
import tomllib

from . import util

logger = logging.getLogger(__name__)

PIN_FILENAME = "pathmunge.toml"


def toolenv_root() -> pathlib.Path:
    """Root directory under which each (tool, version) gets its own pixi project.

    Priority: an explicit ADS_DEPLOY_TOOLENV_ROOT override, then -- on
    Windows -- the canonical shared location IF an admin has already
    bootstrapped one there, then the per-user default. Checking for the
    shared location on disk (rather than requiring a machine-wide
    environment variable) means every other user's `ads-deploy` picks it up
    automatically: no setx /M, no registry write, no admin rights needed by
    anyone but whoever first created that shared directory (which already
    needs admin rights anyway, to write under C:\\ProgramData at all -- see
    DESIGN.md). This is why ADS_DEPLOY_SHARED_DIR's documented, default
    value is specifically C:\\ProgramData\\ads-deploy: a different choice
    still works via the explicit override below, but loses this auto-detection.
    """
    override = os.environ.get("ADS_DEPLOY_TOOLENV_ROOT")
    if override:
        return pathlib.Path(override)

    if sys.platform == "win32":
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")
        shared = pathlib.Path(program_data) / "ads-deploy" / "toolenvs"
        if shared.is_dir():
            return shared
        base = os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME", pathlib.Path.home() / ".local" / "share")

    return pathlib.Path(base) / "ads-deploy" / "toolenvs"


def project_dir(tool: str, version: str) -> pathlib.Path:
    """The per-(tool, version) pixi project directory (holds pixi.toml + .pixi/)."""
    return toolenv_root() / tool / version


def pixi_platform() -> str:
    """The pixi/conda platform identifier for the current machine."""
    if sys.platform == "win32":
        return "win-64"
    if sys.platform == "darwin":
        import platform

        return "osx-arm64" if platform.machine() == "arm64" else "osx-64"
    return "linux-64"


def env_prefix(project: pathlib.Path) -> pathlib.Path:
    """The pixi-managed environment prefix for a provisioned tool/version."""
    return project / ".pixi" / "envs" / "default"


def bin_dirs(project: pathlib.Path) -> list:
    """
    Every executable directory actually present inside a provisioned
    tool/version's pixi environment, in PATH-prepend priority order.

    Generalized rather than tool- or ecosystem-specific: a PyPI console
    script lands in Scripts/ (Windows) or bin/ (POSIX); a conda-forge
    package's binaries can land in several different standard locations
    depending on how it's built (confirmed directly: conda-forge's `make`
    for win-64 lands in Library/bin, a PyPI package like pytmc lands in
    Scripts). Every known location is checked; only the ones that actually
    exist are returned, so this needs no per-tool special-casing.
    """
    prefix = env_prefix(project)
    if sys.platform == "win32":
        candidates = [
            prefix / "Scripts",
            prefix / "Library" / "bin",
            prefix / "Library" / "usr" / "bin",
            prefix / "Library" / "mingw-w64" / "bin",
            prefix,
        ]
    else:
        candidates = [prefix / "bin"]

    return [d for d in candidates if d.is_dir()]


def parse_tool_spec(spec: str) -> tuple:
    """Split a ``tool/version`` spec; version may be omitted."""
    if "/" in spec:
        tool, version = spec.split("/", 1)
    else:
        tool, version = spec, None

    if not tool:
        raise ValueError(f"Invalid tool spec: {spec!r}")

    return tool, version


def find_pin_file(start: pathlib.Path) -> pathlib.Path:
    for directory in [start, *start.parents]:
        candidate = directory / PIN_FILENAME
        if candidate.exists():
            return candidate

    return None


def read_tool_versions(pin_file: pathlib.Path) -> dict:
    """Read the `[tool-versions]` table of a `pathmunge.toml`-shaped file."""
    with open(pin_file, "rb") as fp:
        data = tomllib.load(fp)

    return data.get("tool-versions", {})


def latest_installed_version(tool: str) -> str:
    """
    Return the highest version of ``tool`` currently installed locally (see
    `ads-deploy versions`), or ``None`` if nothing is installed yet. Never
    touches the network -- this is "latest of what you already have", not
    "latest on PyPI".

    Only considers versions with a real, usable environment (a non-empty
    `bin_dirs()`) -- confirmed directly against a real failure: a version
    directory can exist with nothing but a `pixi.toml` inside if an earlier
    `ads-deploy install` attempt failed partway through (e.g. a typo'd
    version that doesn't actually exist upstream -- `project.mkdir()` +
    `manifest_path.write_text()` both run in `install.py` *before* the
    `pixi install` subprocess that can fail). Without this check, such a
    broken leftover with a numerically higher version string would always
    be preferred over the real, working installation.
    """
    tool_root = toolenv_root() / tool
    if not tool_root.exists():
        return None

    versioned = {
        path.name: util.parse_version_tag(path.name)
        for path in tool_root.iterdir()
        if path.is_dir() and bin_dirs(project_dir(tool, path.name))
    }
    versioned = {name: v for name, v in versioned.items() if v is not None}
    if not versioned:
        return None

    return max(versioned, key=versioned.get)


def resolve_pinned_version(tool: str, search_from: pathlib.Path) -> str:
    """
    Resolve the version of ``tool`` to use when none was given explicitly:

    1. A `pathmunge.toml` with a `[tool-versions]` entry, found by walking
       up from ``search_from``, wins if present.
    2. Otherwise, fall back to the latest version of ``tool`` already
       installed locally (no pin required for the common case).
    3. If neither exists, raise -- there's nothing to resolve to.
    """
    pin_file = find_pin_file(search_from)
    if pin_file is not None:
        pinned = read_tool_versions(pin_file).get(tool)
        if pinned:
            logger.info("Resolved %s version %s from %s", tool, pinned, pin_file)
            return pinned

    latest = latest_installed_version(tool)
    if latest is not None:
        logger.info(
            "No %s pin found above %s; using latest installed %s version: %s",
            PIN_FILENAME,
            search_from,
            tool,
            latest,
        )
        return latest

    raise RuntimeError(
        f"No version given for {tool!r}, no pin found in any "
        f"{PIN_FILENAME} above {search_from}, and no version of {tool!r} "
        f"is installed yet. Run: ads-deploy install {tool}/VERSION"
    )
