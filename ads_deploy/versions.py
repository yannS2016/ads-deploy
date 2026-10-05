"""
`ads-deploy versions` lists every version of a tool currently installed
locally by `ads-deploy pathmunge` (i.e. every immutable venv under the
toolenv root for that tool name).
"""

from .pathmunge import build_versions_arg_parser as build_arg_parser
from .pathmunge import versions_main as main

__all__ = ["build_arg_parser", "main"]
