"""
`ads-deploy pathmunge` resolves one or more already-installed, pinned tool
versions and prints a single PATH fragment -- all their executable
directories joined together -- to prepend to PATH, without activating any
environment or touching any other environment variable.

It does NOT install anything itself (see `ads-deploy install`); like
ctrlenv-pathmunge on Linux, it only resolves and exposes versions that have
already been provisioned. If a requested tool/version isn't installed yet,
it fails and tells you to run `ads-deploy install` first.

Multiple tools are accepted in one call (`ads-deploy pathmunge pytmc make`)
specifically so a caller only ever needs ONE invocation and ONE PATH
prepend -- looping over several pathmunge calls in a .cmd file and
accumulating PATH across iterations hits a classic cmd.exe gotcha (variables
set-and-read within the same parenthesized block/loop body are expanded
once, using their value from before the block started), so this is resolved
in Python instead of in batch.

Usage::

    ads-deploy install pytmc/v2.22.2      # provision, once
    ads-deploy pathmunge pytmc/v2.22.2    # resolve + print PATH entry
    ads-deploy pathmunge pytmc            # resolve version from pathmunge.toml
    ads-deploy pathmunge pytmc make       # resolve several tools in one line
    ads-deploy versions pytmc             # list what's installed locally
"""

import argparse
import logging
import pathlib
import sys

from . import toolenv

logger = logging.getLogger(__name__)

DESCRIPTION = __doc__

_PATH_SEP = ";" if sys.platform == "win32" else ":"


def resolve(tool: str, version: str) -> list:
    """Return the executable directories for an already-installed tool/version."""
    project = toolenv.project_dir(tool, version)
    if not project.exists():
        raise RuntimeError(
            f"{tool}/{version} is not installed. Run:\n"
            f"    ads-deploy install {tool}/{version}"
        )

    dirs = toolenv.bin_dirs(project)
    if not dirs:
        raise RuntimeError(
            f"{tool}/{version} is installed at {project}, but no executable "
            "directory was found inside its environment."
        )

    return dirs


def resolve_tool_spec(tool_spec: str) -> list:
    """Resolve one ``tool[/version]`` spec to its executable directories."""
    tool, version = toolenv.parse_tool_spec(tool_spec)
    if version is None:
        version = toolenv.resolve_pinned_version(tool, pathlib.Path.cwd())

    return resolve(tool, version)


def _emit(all_dirs: list, emit_format: str) -> None:
    joined = _PATH_SEP.join(str(d) for d in all_dirs)
    if emit_format == "path":
        print(joined)
    elif emit_format == "cmd":
        print(f'SET "PATH={joined};%PATH%"')
    elif emit_format == "powershell":
        print(f'$env:PATH = "{joined};" + $env:PATH')
    else:
        raise ValueError(f"Unknown emit format: {emit_format}")


def build_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "tool_specs",
        metavar="TOOL[/VERSION]",
        type=str,
        nargs="+",
        help="One or more tool names, optionally with a pinned version "
             "(e.g. pytmc/v2.22.2 make)",
    )
    parser.add_argument(
        "--emit",
        choices=("path", "cmd", "powershell"),
        default="path",
        help="Output format for the resolved PATH fragment (default: path)",
    )

    return parser


def main(tool_specs: list, emit: str = "path") -> None:
    all_dirs = []
    for tool_spec in tool_specs:
        all_dirs.extend(resolve_tool_spec(tool_spec))

    _emit(all_dirs, emit)


def build_versions_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = (
        "List every version of a tool currently installed locally by "
        "`ads-deploy install`."
    )
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "tool",
        type=str,
        help="Tool name (e.g. pytmc)",
    )

    return parser


def versions_main(tool: str) -> None:
    tool_root = toolenv.toolenv_root() / tool
    if not tool_root.exists():
        print(f"No versions of {tool!r} installed yet.")
        return

    installed = sorted(p.name for p in tool_root.iterdir() if p.is_dir())
    if not installed:
        print(f"No versions of {tool!r} installed yet.")
        return

    for version in installed:
        print(version)
