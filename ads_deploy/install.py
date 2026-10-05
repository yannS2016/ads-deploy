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
    ads-deploy install pytmc            # installs the latest pytmc upstream
    ads-deploy install                  # installs everything in pathmunge.toml
    ads-deploy pathmunge pytmc/v2.22.2
"""

import argparse
import json
import logging
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from . import toolenv, util
from .tool_registry import get_source

logger = logging.getLogger(__name__)

DESCRIPTION = __doc__
MODULE_PATH = pathlib.Path(__file__).parent

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


def _resolve_latest_version(tool: str) -> str:
    """
    Query the tool's actual upstream ecosystem (PyPI or conda-forge) for its
    current latest version -- used when `ads-deploy install <tool>` is
    given no version at all. Deliberately distinct from
    `toolenv.latest_installed_version()`, which only ever looks at what's
    already installed locally and never touches the network; that one backs
    `pathmunge`/`build`'s own implicit resolution and must stay network-free.
    This one only runs for an explicit `ads-deploy install` with no version.
    """
    source = get_source(tool)

    try:
        if source.ecosystem == "pypi":
            url = f"https://pypi.org/pypi/{source.package}/json"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.load(response)
            raw_version = data["info"]["version"]
        elif source.ecosystem == "conda":
            url = f"https://api.anaconda.org/package/conda-forge/{source.package}"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.load(response)
            # anaconda.org's own ordering isn't guaranteed to be sorted --
            # same max()-over-parse_version_tag pattern
            # toolenv.latest_installed_version() already uses, rather than
            # trusting versions[-1].
            parsed = {v: util.parse_version_tag(v) for v in data["versions"]}
            parsed = {v: p for v, p in parsed.items() if p is not None}
            if not parsed:
                raise ValueError(f"No numeric versions found for {source.package!r}")
            raw_version = max(parsed, key=parsed.get)
        else:
            raise ValueError(
                f"Unknown ecosystem {source.ecosystem!r} for tool {tool!r}"
            )
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as ex:
        raise RuntimeError(
            f"Could not resolve the latest upstream version of {tool!r} "
            f"({ex.__class__.__name__}: {ex}). Specify a version explicitly "
            f"instead: ads-deploy install {tool}/<version>"
        ) from ex

    return f"{source.version_prefix}{raw_version}"


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
        logger.info(
            "Copied %s -> %s (ads-ioc's Makefile.base expects python3)",
            python_exe,
            python3_exe,
        )
    else:
        logger.info(
            "No python.exe found at %s; this environment has no Python to "
            "shim python3.exe from (expected for a tool with no python "
            "dependency, e.g. make).",
            python_exe,
        )


def _committed_lock_path(tool: str, version: str) -> pathlib.Path:
    """
    Where a committed, strict-reproducibility `pixi.lock` for ``tool/version``
    lives, if one has been generated and committed (see `--save-lock`).
    Lives *inside* the `ads_deploy` package itself (not e.g. a top-level
    directory) so it ships automatically in the built wheel with zero
    `pyproject.toml` changes -- hatchling already includes every non-`.py`
    file under `ads_deploy/` (confirmed: this is how `templates/*.jinja2`
    and `windows/*.cmd` already ship today).
    """
    return MODULE_PATH / "lockfiles" / tool / version / "pixi.lock"


def install(
    tool: str, version: str, force: bool = False, save_lock: bool = False
) -> None:
    """Create the isolated pixi environment for ``tool==version`` if it doesn't exist."""
    project = toolenv.project_dir(tool, version)
    manifest = _render_manifest(tool, version)
    manifest_path = project / "pixi.toml"

    # save_lock always forces a fresh resolve+install, same as `force` --
    # the whole point of --save-lock is regenerating an up-to-date lock to
    # commit, not silently no-op'ing because the environment already exists.
    if project.exists() and not force and not save_lock:
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
                tool,
                version,
                project,
            )
        else:
            logger.warning(
                "%s/%s exists at %s but isn't a valid pixi environment "
                "(stale pre-pixi install, or a previous install was "
                "interrupted) -- rebuilding it.",
                tool,
                version,
                project,
            )

    if project.exists():
        shutil.rmtree(project)

    project.mkdir(parents=True)
    manifest_path.write_text(manifest)

    pixi_args = ["pixi", "install", "--manifest-path", str(manifest_path)]
    committed_lock = _committed_lock_path(tool, version)
    if save_lock:
        # Always a fresh resolve when (re)generating a lock to commit --
        # never trust a possibly-stale previously-committed one here, that
        # would defeat the point of regenerating it.
        logger.info(
            "Resolving %s/%s fresh via pixi at %s (--save-lock)", tool, version, project
        )
    elif committed_lock.is_file():
        shutil.copy2(committed_lock, project / "pixi.lock")
        pixi_args.append("--locked")
        logger.info(
            "Installing %s/%s from the committed pixi.lock at %s (strict, --locked)",
            tool,
            version,
            committed_lock,
        )
    else:
        logger.warning(
            "%s/%s has no committed pixi.lock yet -- this install resolves "
            "transitive dependencies fresh and is NOT guaranteed bit-for-bit "
            "reproducible across machines. Run `ads-deploy install %s/%s "
            "--save-lock` from an ads-deploy git checkout to fix that.",
            tool,
            version,
            tool,
            version,
        )
        logger.info(
            "Resolving and installing %s/%s via pixi at %s", tool, version, project
        )

    try:
        subprocess.run(pixi_args, check=True)
    except subprocess.CalledProcessError:
        # Don't leave a broken, pixi.toml-only directory behind on failure
        # (e.g. a typo'd version that doesn't exist upstream, or -- with
        # --locked -- a committed lock that's drifted out of sync with the
        # manifest) -- confirmed directly: `toolenv.latest_installed_version()`
        # now skips installs with no real environment, but a leftover failed
        # directory still wastes disk and shows up (misleadingly) in
        # `ads-deploy versions`.
        shutil.rmtree(project, ignore_errors=True)
        raise
    _ensure_python3_shim(project)

    if save_lock:
        generated_lock = project / "pixi.lock"
        if generated_lock.is_file():
            committed_lock.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(generated_lock, committed_lock)
            logger.info(
                "Saved %s -- commit it: git add %s && git commit -m "
                '"Add/update pixi.lock for %s/%s"',
                committed_lock,
                committed_lock,
                tool,
                version,
            )
        else:
            logger.warning(
                "pixi did not write a pixi.lock at %s; nothing saved.",
                generated_lock,
            )


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
        "The version may be omitted (e.g. just `pytmc`) to install "
        "whatever's latest upstream right now -- a convenience for "
        "getting started, not a substitute for pinning a real "
        "deployment. If TOOL/VERSION is omitted entirely, installs "
        f"every entry in a {toolenv.PIN_FILENAME}'s [tool-versions] "
        "table (found by walking up from the current directory).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the environment(s) even if already installed",
    )
    parser.add_argument(
        "--save-lock",
        action="store_true",
        help="Resolve fresh and save the resulting pixi.lock to "
        "ads_deploy/lockfiles/<tool>/<version>/, for committing. "
        "Maintainer-only: run this from an actual ads-deploy git "
        "checkout (e.g. `uv run python -m ads_deploy install "
        "<tool>/<version> --save-lock`), not the shared/production "
        "install -- that copy lives in site-packages, not anywhere "
        "git tracks. Only needs to be run once per tool/version to "
        "pin; every later install of that exact tool/version then "
        "automatically uses the committed lock, no flag needed.",
    )

    return parser


def _install_from_pin_file(force: bool, save_lock: bool = False) -> None:
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
        install(tool, version, force=force, save_lock=save_lock)


def main(tool_spec: str = None, force: bool = False, save_lock: bool = False) -> None:
    if tool_spec is None:
        _install_from_pin_file(force=force, save_lock=save_lock)
        return

    tool, version = toolenv.parse_tool_spec(tool_spec)
    if version is None:
        version = _resolve_latest_version(tool)
        logger.info("No version given for %s; resolved latest: %s", tool, version)

    install(tool, version, force=force, save_lock=save_lock)
