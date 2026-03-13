"""Avogadro plugin for Psi4 cubeprop analysis (ELF, LOL, dual descriptor)."""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("feature")
    parser.add_argument("--lang", nargs="?", default="en")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    avo_input = json.load(sys.stdin)
    output = None

    match args.feature:
        case "cubeprop":
            from .cubeprop import run
            output = run(avo_input)

    if output is not None:
        print(json.dumps(output))
