import argparse

from casatasks import casalog

def logging_parent() -> argparse.ArgumentParser:
    """`argparse` parent for getting the logging file name."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--logfile', default=None, nargs=1, type=str,
                        help='Log file name')
    parser.set_defaults(log=casalog)

    return parser

def set_logging(args: argparse.NameSpace) -> None:
    """Set casalog log file."""
    # Logging
    if args.logfile is not None:
        args.log.setlogfile(args.logfile[0])
