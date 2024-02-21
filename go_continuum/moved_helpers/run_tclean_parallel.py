"""Script to run tclean in parallel with mpicasa."""
from pathlib import Path
import argparse
import sys
import json

def main(args: list):
    """Run tclean."""
    # Argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', action='store_true')
    parser.add_argument('uvdata', nargs=1, type=str)
    parser.add_argument('imagename', nargs=1, type=str)
    parser.add_argument('paramsfile', nargs=1, type=str)
    args = parser.parse_args(args)

    # Load params
    # pylint: disable=W1514
    paramsfile = Path(args.paramsfile[0])
    tclean_params = json.loads(paramsfile.read_text())

    # Run tclean
    # pylint: disable=E0602
    tclean(vis=args.uvdata[0], imagename=args.imagename[0], **tclean_params)

if __name__ == '__main__':
    main(sys.argv[1:])
