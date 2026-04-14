#!/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""jsonc_sdict module entrypoint"""

import sys
from argparse import ArgumentParser
from importlib import import_module
from typing import Any, Sequence

MergeModule = import_module("jsonc_sdict.merge")


def argParser() -> ArgumentParser:
    ap = ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command")
    parent = MergeModule._argParser(add_help=False)
    sp = sub.add_parser(
        name="merge",
        parents=[parent],
        description=MergeModule.__doc__,
    )
    sp.set_defaults(_main=MergeModule._main_)
    return ap


def main(args: Sequence[str] | None = None) -> Any:
    args = list(sys.argv[1:] if args is None else args)
    parser = argParser()
    ns = parser.parse_args(args)
    entrypoint = getattr(ns, "_main", None)

    if entrypoint is None:
        parser.print_help()
        return 0

    return entrypoint(ns=ns)


if __name__ == "__main__":
    main()
