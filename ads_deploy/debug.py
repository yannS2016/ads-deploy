"""
`ads-deploy debug` runs `pytmc debug` against every tsproj project found in a
TwinCAT solution. Replaces the old `debug_records.cmd`, called directly as a
Visual Studio External Tool (Command=ads-deploy, Arguments=
"debug $(SolutionDir)$(SolutionFileName)") with no `.cmd` wrapper needed.
"""

import argparse
import logging
import subprocess

from . import util, vstools

DESCRIPTION = __doc__
logger = logging.getLogger(__name__)


def build_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "solution",
        type=str,
        help="Full solution path, e.g. $(SolutionDir)$(SolutionFileName)",
    )

    return parser


def main(solution: str) -> None:
    solution = vstools.resolve_solution(solution)
    env = vstools.tool_env("pytmc")
    pytmc = vstools.resolve_executable("pytmc", env)

    _, projects = util.get_tsprojects_from_filename(solution)

    for project in projects:
        subprocess.run([pytmc, "debug", str(project)], env=env)

    logger.info("Done")
