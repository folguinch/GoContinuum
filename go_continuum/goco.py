#!python3
"""Script for continuum finding and data processing pipeline.

Available options:
```bash
python goco.py -h
```
"""
from typing import List
from pathlib import Path
import argparse
import sys

import go_continuum.argparse_actions as actions
import go_continuum.argparse_parents as parents
import go_continuum.argparse_process as process

def _check_environment(args: argparse.Namespace):
    """Check things are there."""
    # Set directories
    args.log.info('Setting environment')
    args.dirty_dir = args.base / 'dirty'
    args.dirty_dir.mkdir(exist_ok=True)
    args.pbclean_dir = args.base / 'pbclean'
    args.pbclean_dir.mkdir(exist_ok=True)
    args.plots_dir = args.base / 'pbclean'
    args.plots_dir.mkdir(exist_ok=True)
    args.yclean_dir = args.base / 'yclean'
    args.yclean_dir.mkdir(exist_ok=True)

    # Set step flags
    args.log.info('Will skip:')
    for step in args.skip:
        args.log.info('\t%s', step)
        args.steps[step] = False

def goco(args: List) -> None:
    """GoContinuum main program.

    Args:
      args: command line args.
    """
    # Pipe and steps
    pipe = [_check_environment, process.prep_data, process.goco_pipe]
    steps = {
        'dirty': True,
        'afoli': True,
        'applycal': True,
        'contsub': True,
        'split': True,
        'yclean': True,
        'pbclean': True,
    }

    # Argparse configuration
    args_parents = [parents.logger('debug_goco.log')]
    parser = argparse.ArgumentParser(
        description='Continuum finding and data processing pipeline.'
        add_help=True,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        parents=args_parents,
        conflict_handler='resolve',
    )
    parser.add_argument('-l', '--list_steps', action='store_true',
                        help='List available steps')
    parser.add_argument('--noredo', dest='redo', action='store_false',
                        help='Skip finished steps')
    parser.add_argument('-b', '--base', 
                        action=actions.NormalizePaths,
                        default=Path('./'),
                        help='Base directory')
    parser.add_argument('-n', '--nproc', type=int,
                        help='Number of processes for parallel steps')
    parser.add_argument('--skip', nargs='+', choices=list(steps.keys()),
                        help='Skip these steps')
    parser.add_argument('--pos', metavar=('X', 'Y'), nargs=2, type=int,
                        help='Position of the representative spectrum')
    parser.add_argument('--uvdata', action=actions.NormalizePaths, nargs='*',
                        default=None,
                        help='Measurement sets')
    parser.add_argument('configfile', action=actions.CheckFile, nargs=1,
                        help='Configuration file name')
    parser.set_defaults(
        dirty_dir=None,
        pbclean_dir=None,
        yclean_dir=None,
        plots_dir=None,
        steps=steps,
        config=None,
    )

    # Read and process
    args = parser.parse_args(args)
    if args.list_steps:
        args.log('Available steps: %s', list(steps.keys()))
        sys.exit(0)
    for step in pipe:
        step(args)

if __name__ == '__main__':
    goco(sys.argv[1:])
