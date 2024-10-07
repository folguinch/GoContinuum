"""Determine the continuum iteratively using AFOLI."""
#!/bin/python3
from typing import Any, Dict, Optional, TextIO, Sequence, List
from configparser.ConfigParser import ConfigParser
import argparse
import sys

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
import scipy.ndimage as ndi
from astropy.stats import gaussian_fwhm_to_sigma
from astropy.wcs import WCS
from scipy.stats import linregress
from scipy.interpolate import interp1d
from scipy.optimize import bisect
from astropy.stats import sigma_clip

from go_continuum.utils import get_spectrum
import go_continuum.argparse_actions as actions
import go_continuum.argparse_parents as parents

def _prep(args: argparse.Namespace):
    """Initialize parameters for AFOLI."""
    # Initialize table
    if args.table is not None:
        fmt = '%s\t' * len(args.tableinfo)
        args.table.write(fmt % tuple(args.tableinfo))

    # Open configuration file
    if args.config is not None:
        cfg = ConfigParser(defaults={'flagchans':None,
                                     'levels':None,
                                     'levelmode':args.levelmode})
        cfg.read(args.config)
        if cfg.has_section('afoli'):
            args.flagchans = cfg.get('afoli', 'flagchans')
            args.levels = cfg.get('afoli', 'levels')
            args.levelmode = cfg.get('afoli', 'level_mode')

    # Get spectrum
    args.spectrum, pix = get_spectrum(cube_file=args.cube,
                                      spec_file=args.spec,
                                      position=args.position,
                                      rms=args.rms,
                                      beam_avg=args.beam_avg,
                                      beam_fwhm=args.beam_fwhm,
                                      beam_size=args.beam_size,
                                      log=args.log.info)

    # Write table
    if args.table is not None:
        args.table.write(f'{pix[0]:5}\t{pix[1]:5}\t')

def _postprocess(mask_flagged, args, filename=None):
    # Group channels
    assert len(args.spectrum)==len(mask_flagged)
    ind = np.arange(len(args.spectrum)) 
    flagged = group_chans(ind[mask_flagged])

    # Covert to CASA format
    flagged = chans_to_casa(flagged)

    if filename or args.chanfile:
        chanfile = filename or args.chanfile
        logger.info('Writing: %s', os.path.basename(chanfile))
        with open(os.path.expanduser(chanfile), 'w') as out:
            out.write(flagged)
    logger.info('Channels flagged in CASA notation: %s', flagged)

def continuum_iterative(args):
    """Run AFOLI from command line options."""
    # Command line options
    args_parents = [parents.logger('debug_continuum_iterative.log'),
                    parents.spectrum_parent]
    parser = argparse.ArgumentParser(
        description="Determine the continuum iteratively using AFOLI.",
        add_help=True,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        parents=args_parents,
        conflict_handler='resolve',
    )
    subparsers = parser.add_subparsers()
    #parser.add_argument('--minsize', default=100,
    #        help='Minimum  number of continuum channels (default=10)')
    parser.add_argument(
        '--section',
        default='afoli',
        help='Config section')
    parser.add_argument(
        '--dilate',
        default=0,
        type=int,
        help='Number of channels to dilate on each side of a line')
    parser.add_argument(
        '--extremes',
        default=10,
        type=int,
        help='Number of channels to mask at the begining and end of spectrum')
    parser.add_argument(
        '--min_gap',
        default=None,
        type=int,
        help='Minimum space between masked bands')
    parser.add_argument(
        '--min_width',
        default=2,
        type=int,
        help='Minimum number of channels per masked band')
    parser.add_argument(
        '--niter',
        default=None,
        type=int,
        help='Number of iterations')
    parser.add_argument(
        '--plotname',
        default=None,
        help='Plot file name')
    parser.add_argument(
        '--position',
        metavar=('XPIX', 'YPIX'),
        nargs=2,
        type=int,
        default=None,
        help='Position of the spectrum in pixels')
    parser.add_argument(
        '--rms',
        actions=actions.ReadQuantity,
        default=None,
        help='Cube rms')
    parser.add_argument(
        '--chanfile',
        default=None,
        help='File to save the channels masked')
    parser.add_argument(
        '--table',
        default=None,
        type=argparse.FileType('a'),
        help='Table file to save results')
    parser.add_argument(
        '--tableinfo',
        default=[''],
        nargs='*',
        type=str,
        help='Data for the first columns of the table')
    parser.add_argument(
        '--config',
        default=None, 
        help='Specific setup options')
    parser.set_defaults(spectrum=None, ref_pix=None, flagchans=None)
    # Groups
    group1 = parser.add_mutually_exclusive_group(required=True)
    group1.add_argument(
        '--cube',
        action=actions.CheckFile, 
        help='Image file name')
    group1.add_argument(
        '--spec',
        action=actions.CheckFile,
        help='Spectrum file name')

    # Subparsers
    psigmaclip = subparsers.add_parser('sigmaclip', help="Use sigma clip")
    psigmaclip.add_argument(
        '--sigma',
        nargs='*',
        type=float,
        default=(3.0, 1.3),
        help="Sigma level(s)")
    #psigmaclip.add_argument(
    #    '--increment',
    #    type=float,
    #    default=10.,
    #    help="Percent of increment of std value")
    #psigmaclip.add_argument(
    #    '--limit',
    #    type=float,
    #    default=90.,
    #    help="Percent of the total number of masked points to include")
    #psigmaclip.add_argument(
    #    '--ref_pix',
    #    type=int,
    #    default=None,
    #    nargs=2,
    #    help="Off source pixel position")
    psigmaclip.add_argument(
        '--censtat',
        type=str,
        default='median',
        choices=['median', 'mean', 'linregress'],
        help="Statistic for sigma_clip cenfunc")
    psigmaclip.set_defaults(func=func_sigmaclip,
                            func_params={'levelmode': 'nearest'}
                            ref_spec=None)
    args = parser.parse_args(args)
    _prep(args)
    mask = args.func(args)
    _postprocess(mask, args)

if __name__=='__main__':
    continuum_iterative(sys.argv[1:])
