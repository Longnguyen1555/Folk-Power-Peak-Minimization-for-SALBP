"""Thin entry-point adapter; all argument parsing lives in cli.py."""

from .cli import main


def execute(default_method, argv=None):
    import sys

    return main(
        ["solve", *(sys.argv[1:] if argv is None else argv), "--method", default_method]
    )


def export_binary(argv=None):
    import sys

    return main(
        ["export", *(sys.argv[1:] if argv is None else argv), "--formulation", "paper"]
    )
