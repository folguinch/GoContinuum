#!python3
"""Script for continuum finding and data processing pipeline.

Available options:
```bash
python goco.py -h
```
"""
from typing import Optional, Sequence
from pathlib import Path
import argparse
import os
import sys

from go_continuum.environment import GoCoEnviron
from go_continuum.data_handler import DataManager
import goco_helpers.argparse_actions as actions
import goco_helpers.argparse_parents as parents

def _prep_steps(args: argparse.Namespace):
    """Set step flags."""
    if len(args.skip) > 0:
        args.log.info('These steps will be skipped:')
        for step in args.skip:
            args.log.info('\t%s', step)
            args.steps[step] = False

def _get_data_manager(args: 'argparse.Namespace') -> None:
    """Generate a data manager."""
    environ = GoCoEnviron(basedir=args.base)
    args.manager = DataManager(args.configfile[0], environ=environ,
                               log=args.log)

def _goco_pipe(args: 'argparse.Namespace') -> None:
    """Run the GoCo pipeline."""
    # Concatenate data
    args.manager.concat_data()

    # Dirty images
    if args.steps['dirty']:
        dirty_images = args.manager.get_imagenames('dirty')
        for spw, image in enumerate(dirty_images):
            if args.resume and image.exists():
                args.log.info('Skipping dirty for spw%i', spw)
                continue
            elif not args.resume and image.exists():
                target = image.with_suffix('.*')
                args.log.warning('Deleting dirty: %s', target)
                os.system(f'rm -rf {target}')
            args.manager.clean_cube('dirty', spw)

    # AFOLI
    if args.steps['afoli']:
        args.manager.afoli(resume=args.resume)

    # Continuum
    if args.steps['continuum']:
        args.manager.get_continuum_vis(pbclean=args.steps['pbclean'],
                                       nproc=args.nproc[0],
                                       resume=args.resume)

    # Contsub
    if args.steps['contsub']:
        args.manager.get_contsub_vis()

def goco(args: Optional[Sequence] = None) -> None:
    """GoContinuum main program.

    Args:
      args: optional; command line args.
    """
    # Pipe and steps
    pipe = [_prep_steps, _get_data_manager, _goco_pipe]
    steps = {
        'dirty': True,
        'selfcal': True,
        'afoli': True,
        'continuum': True,
        'pbclean': True,
        'contsub': True,
        'cubes': True,
    }

    # Argparse configuration
    args_parents = [parents.logger('debug_goco.log')]
    parser = argparse.ArgumentParser(
        description='Continuum finding and data processing pipeline.',
        add_help=True,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        parents=args_parents,
        conflict_handler='resolve',
    )
    parser.add_argument('-l', '--list_steps', action='store_true',
                        help='List available steps')
    parser.add_argument('--resume', dest='redo', action='store_true',
                        help='Resume unfinished steps')
    parser.add_argument('-b', '--base',
                        action=actions.NormalizePath,
                        default=Path('./'),
                        help='Base directory')
    parser.add_argument('-n', '--nproc', type=int, nargs=1,
                        help='Number of processes for parallel steps')
    parser.add_argument('--skip', nargs='+', choices=list(steps.keys()),
                        help='Skip these steps')
    parser.add_argument('--pos', metavar=('X', 'Y'), nargs=2, type=int,
                        help='Position of the representative spectrum')
    #parser.add_argument('--uvdata', action=actions.NormalizePath, nargs='*',
    #                    default=None,
    #                    help='Measurement sets')
    parser.add_argument('configfile', action=actions.CheckFile, nargs=1,
                        help='Configuration file name')
    parser.set_defaults(
        manager=None,
        steps=steps,
    )

    # Read and process
    if args is None:
        args = parser.parse_args(args)
    if args.list_steps:
        args.log('Available steps: %s', list(steps.keys()))
        sys.exit(0)
    for step in pipe:
        step(args)

if __name__ == '__main__':
    goco(sys.argv[1:])
