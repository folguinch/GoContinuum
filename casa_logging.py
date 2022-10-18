"""Setup the logging system for CASA scripts."""
from typing import TypeVar
import argparse

from casatasks import casalog

# Types
NameSpace = TypeVar('NameSpace')

def logging_parent() -> argparse.ArgumentParser:
    """Get `argparse` parent for logging file name."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--logfile', default=None, nargs=1, type=str,
                        help='Log file name')
    parser.set_defaults(log=casalog)

    return parser

def set_logging(args: NameSpace) -> None:
    """Set casalog log file from argument parser object."""
    # Logging
    if args.logfile is not None:
        args.log.setlogfile(args.logfile[0])
    args.log.showconsole(True)
