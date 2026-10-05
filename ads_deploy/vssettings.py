"""
`ads-deploy vssettings` generates a Visual Studio (TwinCAT XAE) external
tools settings file. Every entry's Command is `ads-deploy`'s own resolved
absolute path -- there is no per-machine install-LOCATION to hand-edit the
way the old `external-tools.vssettings` needed (it hardcoded
`C:\\Repos\\ads-deploy`), since this is computed fresh each time
`ads-deploy vssettings` runs, via `shutil.which`.

Visual Studio's "Command" field does NOT do a PATH search the way cmd.exe
does -- confirmed directly: a bare `ads-deploy` (relying on PATH, same
convention as typing `git` or `uv` at a shell) fails with "The command is
not a valid executable." It needs the actual resolved path.
"""

import argparse
import logging
import os
import pathlib
import shutil

import jinja2

logger = logging.getLogger(__name__)

DESCRIPTION = __doc__
MODULE_PATH = pathlib.Path(__file__).parent
TEMPLATE_PATH = MODULE_PATH / "templates"
DEFAULT_OUTPUT = "external-tools.vssettings"

# No space between the two macros: a quoted Windows argument ending in a
# backslash (as $(SolutionDir) always does) has its closing quote escaped by
# standard argv parsing, merging it with whatever argument follows.
# Concatenating into a single $(SolutionDir)$(SolutionFileName) argument
# ends in `.sln` instead, which can't trigger that -- confirmed directly
# (see ads_deploy/vstools.py's resolve_solution docstring).
SOLUTION_ARGS = "$(SolutionDir)$(SolutionFileName)"
SOLUTION_INITIAL_DIR = "$(SolutionDir)"


def _resolve_command(name: str) -> str:
    """Resolve ``name`` to its full path via PATH; fall back to the bare
    name (with a warning) if it can't be found, rather than failing
    `vssettings` generation outright."""
    found = shutil.which(name)
    if found is None:
        logger.warning(
            "Could not resolve %r on PATH -- using the bare name, which "
            "Visual Studio's External Tools will likely reject as "
            "\"not a valid executable\". Make sure it's installed and on PATH.",
            name,
        )
        return name

    # On Windows, shutil.which() appends an extension from the PATHEXT env
    # var when `name` has none -- and PATHEXT's own casing (commonly
    # ".EXE", uppercase) is preserved verbatim, which varies by machine/
    # session for no functional reason (Windows path execution is
    # case-insensitive either way). Confirmed directly: regenerating this
    # file on different sessions flip-flopped between "ads-deploy.exe" and
    # "ads-deploy.EXE", producing pure-noise diffs in a file we want to stay
    # reproducible. Normalize just the extension to lowercase; leave the
    # rest of the path's casing untouched.
    root, ext = os.path.splitext(found)
    return root + ext.lower()


def _build_tools() -> list:
    ads_deploy = _resolve_command("ads-deploy")
    designer = _resolve_command("designer")

    return [
        dict(command=ads_deploy, title="&amp;1 Lint pragmas",
             arguments=f"lint {SOLUTION_ARGS}", initial_directory=SOLUTION_INITIAL_DIR,
             use_output_window=True, prompt_for_arguments=False),
        dict(command=ads_deploy, title="&amp;2 Configure and build IOC(s)",
             arguments=f"build {SOLUTION_ARGS}", initial_directory=SOLUTION_INITIAL_DIR,
             use_output_window=True, prompt_for_arguments=False),
        dict(command=ads_deploy, title="&amp;3 Record debugging",
             arguments=f"debug {SOLUTION_ARGS}", initial_directory=SOLUTION_INITIAL_DIR,
             use_output_window=False, prompt_for_arguments=False),
        dict(command=ads_deploy, title="&amp;4 Project summary",
             arguments=f"summary {SOLUTION_ARGS}", initial_directory=SOLUTION_INITIAL_DIR,
             use_output_window=False, prompt_for_arguments=False),
        dict(command=designer, title="Qt Designer",
             arguments="", initial_directory=SOLUTION_INITIAL_DIR,
             use_output_window=False, prompt_for_arguments=False),
    ]


def build_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "--output",
        dest="output_path",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"Where to write the .vssettings file (default: {DEFAULT_OUTPUT})",
    )

    return parser


def main(output_path: str) -> None:
    loader = jinja2.FileSystemLoader(str(TEMPLATE_PATH))
    env = jinja2.Environment(loader=loader, trim_blocks=True, lstrip_blocks=True)
    template = env.get_template("external-tools.vssettings.jinja2")

    contents = template.render(tools=_build_tools())

    output_path = pathlib.Path(output_path)
    output_path.write_text(contents)
    logger.info("Wrote %s", output_path)
