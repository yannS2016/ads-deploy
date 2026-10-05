"""
`ads-deploy vssettings` generates a Visual Studio (TwinCAT XAE) external
tools settings file. Every entry's Command is `ads-deploy` itself -- resolved
via `PATH` globally, exactly like `git`/`uv`/`pixi` already are -- so there is
no per-machine install-location path to template at all, unlike the old
`external-tools.vssettings`, which hardcoded `C:\\Repos\\ads-deploy`.
"""

import argparse
import logging
import pathlib

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
COMMAND = "ads-deploy"

TOOLS = [
    dict(command=COMMAND, title="&amp;1 Lint pragmas",
         arguments=f"lint {SOLUTION_ARGS}", initial_directory=SOLUTION_INITIAL_DIR,
         use_output_window=True, prompt_for_arguments=False),
    dict(command=COMMAND, title="&amp;2 Configure and build IOC(s)",
         arguments=f"build {SOLUTION_ARGS}", initial_directory=SOLUTION_INITIAL_DIR,
         use_output_window=True, prompt_for_arguments=False),
    dict(command=COMMAND, title="&amp;3 Record debugging",
         arguments=f"debug {SOLUTION_ARGS}", initial_directory=SOLUTION_INITIAL_DIR,
         use_output_window=False, prompt_for_arguments=False),
    dict(command=COMMAND, title="&amp;4 Project summary",
         arguments=f"summary {SOLUTION_ARGS}", initial_directory=SOLUTION_INITIAL_DIR,
         use_output_window=False, prompt_for_arguments=False),
    dict(command="designer", title="Qt Designer",
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

    contents = template.render(tools=TOOLS)

    output_path = pathlib.Path(output_path)
    output_path.write_text(contents)
    logger.info("Wrote %s", output_path)
