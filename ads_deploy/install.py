"""
`ads-deploy install` provisions an isolated, immutable pixi-managed
environment for a pinned version of a tool -- pytmc (PyPI), make
(conda-forge), or anything else registered in `ads_deploy/tool_registry.py`.
Once created, a given tool/version is never modified in place -- installing
the same spec again is a no-op; `--force` is the only way to rebuild it.

pixi is the install backend (not plain uv/pip) specifically so that adding a
future tool that only exists on conda-forge (a compiler, Qt, any
non-Python/non-PyPI dependency) never requires new install logic in this
file -- just one entry in tool_registry.py saying where it comes from. pixi
resolves both PyPI and conda-forge dependencies, with its own lockfile, in
one environment, which plain `uv pip install` could never do (pip only ever
reaches PyPI).

This is the provisioning half of the pathmunge story: `ads-deploy install`
builds a tool/version; `ads-deploy pathmunge` only resolves and exposes one
that has already been installed.

Usage::

    ads-deploy install pytmc/v2.22.2
    ads-deploy install make/4.4.1
    ads-deploy install                  # installs everything in pathmunge.toml
    ads-deploy pathmunge pytmc/v2.22.2
"""

import argparse
import logging
import pathlib
import shutil
import subprocess
import sys

from . import toolenv
from .tool_registry import get_source

logger = logging.getLogger(__name__)

DESCRIPTION = __doc__

_CONDA_MANIFEST = """\
[workspace]
name = "{name}"
platforms = ["{platform}"]
channels = ["{channel}"]

[dependencies]
{package} = "=={version}"
"""

_PYPI_MANIFEST = """\
[workspace]
name = "{name}"
platforms = ["{platform}"]
channels = ["conda-forge"]

[dependencies]
python = "*"

[pypi-dependencies]
{package} = "=={version}"
# ads-ioc's own Makefile.base calls `python3 -c "import distutils.version; ..."`
# for its own version check -- distutils was removed from the standard
# library in Python 3.12. We don't control that Makefile, so setuptools
# (whose vendored distutils keeps `import distutils` working on ANY Python
# version, confirmed directly even on 3.14 with zero stdlib distutils) is
# installed alongside, with SETUPTOOLS_USE_DISTUTILS=local set on the
# subprocess that invokes python3 (see build.py) to make it the one that's
# actually used. This is version-independent, unlike capping Python below
# 3.12 (the previous approach here) -- it keeps working no matter which
# Python pixi resolves in the future.
setuptools = "*"
{extra_pypi}\
"""


def _render_manifest(tool: str, version: str) -> str:
    source = get_source(tool)
    clean_version = version.lstrip("v")

    if source.ecosystem == "conda":
        return _CONDA_MANIFEST.format(
            name=f"{tool}-{version}",
            platform=toolenv.pixi_platform(),
            channel=source.channel,
            package=source.package,
            version=clean_version,
        )
    elif source.ecosystem == "pypi":
        extra_pypi = "".join(f'{dep} = "*"\n' for dep in source.extra_pypi)
        return _PYPI_MANIFEST.format(
            name=f"{tool}-{version}",
            platform=toolenv.pixi_platform(),
            package=source.package,
            version=clean_version,
            extra_pypi=extra_pypi,
        )
    else:
        raise ValueError(f"Unknown ecosystem {source.ecosystem!r} for tool {tool!r}")


def _is_valid_install(project) -> bool:
    """
    Whether ``project`` holds a real, finished pixi environment -- not just
    an existing directory. A directory can exist without this being true:
    a pre-pixi-migration install left a plain venv layout with no
    `.pixi/envs/default` at all, and an install interrupted partway through
    (killed, pixi failure) can leave `pixi.toml` written but no environment
    actually materialized. Either way, "the directory exists" is not the
    same guarantee as "this is installed" -- check for the thing pathmunge
    will actually need: at least one real executable directory inside it.
    """
    return bool(toolenv.bin_dirs(project))


def _ensure_python3_shim(project) -> None:
    """
    conda-forge's Python build for Windows ships `python.exe`/`pythonw.exe`
    but no `python3.exe` (that's a Unix convention it doesn't follow). Tools
    that probe `which python3 || which python` -- e.g. ads-ioc's
    Makefile.base -- only work if `python3` exists at all; without it,
    behavior falls back to whatever `python` happens to resolve to
    elsewhere on PATH (often a Windows Store app-execution-alias stub).

    This is not new: the pre-pixi, conda-based setup's old post_install.sh
    did exactly this copy for exactly this reason. It still applies with
    pixi, since pixi's Windows Python also comes from conda-forge.
    """
    if sys.platform != "win32":
        return

    prefix = toolenv.env_prefix(project)
    python_exe = prefix / "python.exe"
    python3_exe = prefix / "python3.exe"

    if python3_exe.exists():
        logger.info("python3.exe already present at %s", python3_exe)
    elif python_exe.is_file():
        shutil.copy2(python_exe, python3_exe)
        logger.info("Copied %s -> %s (ads-ioc's Makefile.base expects python3)",
                    python_exe, python3_exe)
    else:
        logger.info(
            "No python.exe found at %s; this environment has no Python to "
            "shim python3.exe from (expected for a tool with no python "
            "dependency, e.g. make).",
            python_exe,
        )


def install(tool: str, version: str, force: bool = False) -> None:
    """Create the isolated pixi environment for ``tool==version`` if it doesn't exist."""
    project = toolenv.project_dir(tool, version)
    manifest = _render_manifest(tool, version)
    manifest_path = project / "pixi.toml"

    if project.exists() and not force:
        on_disk = manifest_path.read_text() if manifest_path.exists() else None

        if on_disk == manifest and _is_valid_install(project):
            logger.info("%s/%s is already installed at %s", tool, version, project)
            _ensure_python3_shim(project)
            return

        if on_disk != manifest:
            logger.warning(
                "%s/%s exists at %s but was built from a different manifest "
                "than what ads-deploy would generate now (e.g. an earlier "
                "ads-deploy version pinned a different Python, or the "
                "registry entry changed) -- rebuilding it.",
                tool, version, project,
            )
        else:
            logger.warning(
                "%s/%s exists at %s but isn't a valid pixi environment "
                "(stale pre-pixi install, or a previous install was "
                "interrupted) -- rebuilding it.",
                tool, version, project,
            )

    if project.exists():
        shutil.rmtree(project)

    project.mkdir(parents=True)
    manifest_path.write_text(manifest)

    logger.info("Resolving and installing %s/%s via pixi at %s", tool, version, project)
    try:
        subprocess.run(
            ["pixi", "install", "--manifest-path", str(manifest_path)],
            check=True,
        )
    except subprocess.CalledProcessError:
        # Don't leave a broken, pixi.toml-only directory behind on failure
        # (e.g. a typo'd version that doesn't exist upstream) -- confirmed
        # directly: `toolenv.latest_installed_version()` now skips installs
        # with no real environment, but a leftover failed directory still
        # wastes disk and shows up (misleadingly) in `ads-deploy versions`.
        shutil.rmtree(project, ignore_errors=True)
        raise
    _ensure_python3_shim(project)


def build_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "tool_spec",
        metavar="TOOL/VERSION",
        type=str,
        nargs="?",
        default=None,
        help="Tool and pinned version, e.g. pytmc/v2.22.2 or make/4.4.1. "
             f"If omitted, installs every entry in a {toolenv.PIN_FILENAME}'s "
             "[tool-versions] table (found by walking up from the current "
             "directory).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the environment(s) even if already installed",
    )

    return parser


def _install_from_pin_file(force: bool) -> None:
    pin_file = toolenv.find_pin_file(pathlib.Path.cwd())
    if pin_file is None:
        raise RuntimeError(
            f"No TOOL/VERSION given, and no {toolenv.PIN_FILENAME} found "
            f"above {pathlib.Path.cwd()}. Pass TOOL/VERSION explicitly, or "
            f"add a [tool-versions] table to a {toolenv.PIN_FILENAME}."
        )

    tool_versions = toolenv.read_tool_versions(pin_file)
    if not tool_versions:
        raise RuntimeError(f"{pin_file} has no [tool-versions] entries to install.")

    logger.info("Installing every tool pinned in %s", pin_file)
    for tool, version in tool_versions.items():
        install(tool, version, force=force)


def main(tool_spec: str = None, force: bool = False) -> None:
    if tool_spec is None:
        _install_from_pin_file(force=force)
        return

    tool, version = toolenv.parse_tool_spec(tool_spec)
    if version is None:
        raise ValueError(
            f"ads-deploy install requires an explicit version: {tool}/VERSION "
            "(or omit TOOL/VERSION entirely to install everything pinned in "
            f"a {toolenv.PIN_FILENAME})"
        )

    install(tool, version, force=force)
