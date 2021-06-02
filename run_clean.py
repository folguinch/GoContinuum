from configparser import ConfigParser
from pathlib import Path
from typing import Sequence
import argparse
import sys

from casatasks import tclean, exportfits

# Local utils
#aux = os.path.dirname(sys.argv[2])
#sys.path.insert(0, aux)
import casa_logging
import casa_utils as utils

def run_tclean(log, **kwargs):
    """Run `tclean` with the input parameters."""
    # Run tclean
    log.post(f"Image name: {kwargs['imagename']}")
    log.post(f"Processing spw: {kwargs['spw']}")
    tclean(**kwargs)

    # Compute rms
    imagename = kwargs['imagename'].name + '.image'
    imagename = kwargs['imagename'].with_name(imagename)
    utils.put_rms(imagename, log=log)

    # Export FITS
    exportfits(imagename=imagename, 
               fitsimage=imagename.with_suffix('.image.fits'), 
               overwrite=True)

def _run_tclean(args: argparse.NameSpace) -> None:
    """Run `tclean` for all the uvdata in args."""
    # Output directory
    outputdir = Path(args.outputdir[0])

    # Robust shortcut
    robust = args.tclean_params['robust']

    # Iterate over visibilities
    for ms in args.uvdata:
        # Check uvdata
        vis = Path(ms)
        if not vis.is_dir():
            args.log.post(f'Visibility {vis} does not exists, skipping')
            continue

        # Number of spws
        nspws = len(vishead(vis=vis, mode='list')['spw_name'][0])
        args.log.post(f'Processing ms: {vis}')
        args.log.post(f'Number of spws in ms {vis}: {nspws}')

        # Extract properties from ms file name
        if vis.suffix == '.ms':
            msname = vis.stem
        elif '.ms.' in vis.name:
            msname = vis.name.replace('.ms.', '.')
        else:
            msname = vis.name

        # Cases:
        # Combine spws or compute just for specific spw
        if args.all_spws or 'spw' in args.config or args.spw is not None:
            spw = ','.join(map(str, range(nspws)))
            if args.spw:
                spw = args.spw[0]
                imagename = outputdir / f'{msname}.spw{spw}.robust{robust}'
            elif 'spw' in args.config and args.config['spw'] != spw:
                spw = args.config['spw'].replace(',', '_')
                imagename = outputdir / f'{msname}.spw{spw}.robust{robust}'
            else:
                imagename = outputdir / f'{msname}.robust{robust}'
            run_tclean(args.log, vis=vis, spw=spw, imagename=imagename,
                       **args.tclean_params)
        else:
            # All spectral windows one by one
            for spw in range(nspws):
                imagename = outputdir / f'{msname}.spw{spw}.robust{robust}'
                run_tclean(args.log, vis=ms, spw=f'{spw}', imagename=imagename,
                           **args.tclean_params)

def main(inpargs: Sequence[str]):
    """Run tclean from command line.

    Args:
      args: command line arguments.
    """
    # Defaults
    config_default = {
        'robust': '0.5',
        'deconvolver': 'hogbom',
        'specmode': 'cube',
        'outframe': 'LSRK',
        'gridder': 'standard',
        'interactive':'False',
        'weighting':'briggs',
        'niter':'0',
        'chancunks':'-1',
    }

    # Command line options
    parser = argparse.ArgumentParser(parents=[casa_logging.logging_parent()])
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--all_spws', action='store_true', 
                       help='Combine all spectral windows')
    group.add_argument('--spw', type=str, nargs=1, default=None,
                       help='Value for tclean spw')
    parser.add_argument('--section', nargs=1, type=str, default=['dirty'],
                        help='Configuration section name')
    parser.add_argument('configfile', nargs=1, type=str,
                        help='Configuration file name')
    parser.add_argument('outputdir', nargs=1, type=str,
                        help='Output directory')
    parser.add_argument('uvdata', nargs='*', type=str,
                        help='UV data to extract dirty images')
    parser.set_defaults(
        pipe=[
            casa_logging.set_logging,
            args_proc.set_config,
            args_proc.get_tclean_params,
            _run_tclean,
        ],
        config=config_default,
        tclean_params=None,
    )
    args = parser.parse_args(inpargs)

    # Run steps
    for step in args.pipe:
        step(args)

if __name__=='__main__':
    main(sys.argv[1:])
