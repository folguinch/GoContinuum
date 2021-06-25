"""Execute yclean."""
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar
import argparse
import os
import sys

from casatasks import exportfits
import casatools

import args_proc
import casa_logging
import casa_utils as utils
try:
    from yclean.yclean_parallel import yclean
except ImportError:
    raise ImportError('YCLEAN scripts not present')

Config = TypeVar('Config')

def split_option(cfg: Config,
                 option: str,
                 ignore_sep: Sequence[str] = (),
                 dtype: Optional[Callable] = None) -> List:
    """Split values from configuration option value.

    The program will use the `,` separator first to split the data, if
    unseccessful it will use space.

    Args:
      cfg: configuration parser.
      opt: option.
      ignore_sep: optional; ignore separator (use if "," is allowed in value).
      dtype: optional; map values to dtype.

    Returns:
      A list with the values under `section`, `option`.
    """
    # Original value
    val = cfg.get(option, fallback='')

    # Use coma first
    if ',' in val and ',' not in ignore_sep:
        vals = val.split(',')
    else:
        vals = val.split()

    # Map dtype
    if dtype is not None:
        vals = list(map(dtype, vals))

    return vals

def get_nchans(chanrange: str) -> int:
    """Determine the number of channels from a channel range.

    Args:
      chanrange: channel range.

    Returns:
      The number of channels in the range.
    """
    i, f = tuple(map(int, chanrange.split('~')))
    return abs(f - i) + 1

def fill_window(chanranges: Sequence[str], **kwargs) -> List[Dict[str, Any]]:
    """Fill information for each channel window/range.

    Each element of the list contains the information for each channel range.
    The are stored are:

      - `basename`: base name to keep track of results.
      - `name`: complete name.
      - `freq`: rest frequency.
      - `spw`: nominal spw value.
      - `spw_val`: `spw` value for `tclean`.
      - `width`: the `width` parameter for `tclean`.
      - `start`: the `start` parameter for `tclean`.
      - `nchan`: the `nchan` parameter for `tclean`.

    Args:
      chanranges: list with the channel ranges to split the spw.
      kwargs: additional window information.

    Returns:
      A list with the window information.
    """
    # Check basename
    basename = kwargs.setdefault('name', f"spw{kwargs['spw']}")
    if basename == '':
        kwargs['name'] = f"spw{kwargs['spw']}"

    # Fill information
    window = []
    for i, chanran in enumerate(chanranges):
        # Defaults
        info = {'width': kwargs.get('width', ''), 'basename': kwargs['name']}
        info.update(kwargs)

        # Fill info
        try:
            info['start'] = int(chanran.split('~')[0])
            info['nchan'] = get_nchans(chanran)
            # Update name
            if len(chanranges) > 1:
                info['name'] = info['name'] + f'_{i+1}'
        except ValueError:
            info['start'] = ''
            info['nchan'] = -1

        window.append(info)

    return window

def fill_names(basenames: Sequence[str], spws: Sequence,
               default: str = 'spw') -> List:
    """Create base names for spws.

    Args:
      basenames: base name list.
      spws: spw list.
      default: optional; default name.
    """
    if len(basenames)==0:
        base = [default] * len(spws)
    elif len(basenames) == len(spws):
        base = basenames
    else:
        base = [basenames[0]] * len(spws)

    return [f'{bs}{spw}' for bs, spw in zip(base, spws)]

def match_length(cfg: Config,
                 option: str,
                 match: Sequence,
                 filler: str = '',
                 fillerfn: Optional[Callable] = None,
                 log: Callable = print) -> List:
    """Read values from configuration and match the length to `len(match)`.

    The filler function `fillerfn` should receive 2 inputs: a value and
    `match`; and return a list with length equal to `len(match)`.

    Args:
      cfg: configuration parser.
      opt: option.
      match: sequence to match.
      filler: optional; value to fill empty values.
      fillerfn: optional; function to create filler values.
      log: optional; logging function.

    Returns:
      A list of values with the desired length.
    """
    # Fill function:
    def _fill(val):
        if fillerfn is not None:
            return fillerfn(val, match)
        else:
            return [filler] * len(match)

    # Original values
    vals = split_option(cfg, option)
    nvals = len(vals)

    # Match size
    nmatch = len(match)
    if nvals != nmatch and nvals == 0:
        # Value was not set
        vals = _fill(vals)
    elif nvals != nmatch:
        # Value was set but with incorrect value
        log(f'Length of {option} does not match with pattern', 'WARN')
        log(f'Ignoring {option}', 'WARN')
        vals = _fill(vals)
    else:
        # Match but check for none
        vals = [val if val.lower() != 'none' else filler for val in vals]

    # Double check
    if len(vals) != nmatch:
        raise ValueError((f'Number of elements in option {option} '
                          'does not match'))

    return vals

def get_windows(vis: Path, config: Config, log: Callable = print) -> List:
    """Define parameters for each spw.

    Args:
      vis: visibility file.
      config: `configparser` proxy.
      log: optional; logging function.
    """

    # Spectral windows and frequencies
    spws = split_option(config, 'spws')
    freqs = match_length(config, 'restfreqs', spws, log=log)
    bnames = match_length(config, 'names', spws, fillerfn=fill_names, log=log)
    widths = match_length(config, 'widths', spws, log=log)

    # Spectral window real values after concat
    spws_val = utils.get_spws_indices(vis, spws=spws, log=log)

    # Iterate over spectral windows
    windows = []
    info0 = ['spw', 'spw_val', 'freq', 'name', 'width']
    for info in zip(spws, spws_val, freqs, bnames, widths):
        # Get channel ranges
        spw = info[0]
        if f'chanrange{spw}' in config:
            key = f'chanrange{spw}'
            chanrans = split_option(config, key)
        elif 'chanranges' in config:
            chanrans = split_option(config, 'chanranges')
        else:
            chanrans = split_option(config, 'chanrange')

        # Replace specific channel width
        kwargs = dict(zip(info0, info))
        if f'width{spw}' in  config:
            key = f'width{spw}'
            kwargs['width'] = config[key]

        # Fill the window information
        windows.append(fill_window(chanrans, **kwargs))

    return windows

def join_cubes(inputs: List[Path], output: Path, channels: List[str],
        resume: bool = False, log: Callable = print) -> bool:
    """Join cubes at specific channels.

    Args:
      inputs: input cubes to join.
      output: output cube.
      channels: joining channels.
      resume: optional; skip if `output` exists.
      log: optional; logging function.
    """
    # Check
    if len(channels) != len(inputs):
        raise ValueError((f'Joining channels {len(channels)} !='
                          f'input cubes {len(inputs)}'))

    # Concatenated image
    imagename = output.expanduser()

    # Join
    if resume and imagename.is_dir():
        log(f'Skipping concatenated image: {imagename}')
    else:
        if imagename.is_dir():
            os.system(f'rm -rf {imagename}')
        # Crop images
        filelist = []
        for i, (chans, inp) in enumerate(zip(channels, inputs)):
            # Crop and save temporal image
            img_name = f'temp{i}.image'
            if img_name.is_dir():
                os.system('rm -rf temp*.image')
            utils.crop_spectral_axis(inp, chans, img_name)

            # Store file name
            filelist.append(img_name)

        # Concatenate
        img = casatools.image()
        aux = img.imageconcat(outfile=imagename, infiles=' '.join(filelist))
        img.close()
        aux.close()

    # Put rms
    utils.put_rms(imagename, log=log)

    # Export fits
    fitsimage = imagename.with_suffix('.image.fits')
    if resume and fitsimage.is_file():
        log('Skipping FITS export')
    else:
        exportfits(imagename=imagename, fitsimage=fitsimage, overwrite=True)

    # Clean up
    log('Cleaning up')
    os.system('rm -rf temp*.image')

    return True

def _run_yclean(args: argparse.NameSpace) -> None:
    """Run yclean."""
    # Resume?
    resume = args.resume
    if resume:
        args.log.post('Resume turned on')

    # Source data
    source = args.config['field']
    vis = Path(args.uvdata[0])

    # Spectral setup per channel window
    wins = get_windows(vis, args.config, log=args.log.post)
    #limit_mask_level = args.config.getfloat(section, 'limit_mask_level')

    # Run YCLEAN
    for win in wins:
        #it = 0
        # Directory
        name = win['name']
        directory = Path(args.basedir)
        directory = directory / 'yclean' /  f'{source}_{name}'
        args.log.post('-' * 80)
        args.log.post(f'Procesing {name}')

        # Some clean values
        vis = args.uvdata[0]
        restfreq = win['freq']
        width = win['width']
        start = win['start']
        nchan = int(win['nchan'])
        spw = win['spw_val']
        imagename = directory / f'auto{source}_{name}.12m'

        # Log
        args.log.post(f'vis = {vis}')
        args.log.post(f'imagename = {imagename}')
        args.log.post(f'Spectral window options: {win}')
        if args.test:
            continue

        # Run
        finalimage = imagename.with_suffix('12m.tc_final.fits')
        if os.path.isfile(finalimage) and resume:
            args.log.post(f'Skipping: {finalimage}')
        else:
            args.log.post('Running yclean parallel')
            if not resume:
                args.log.post('Cleaning directories')
                maski =  Path(f'{source}MASCARA.tc0.m')
                if directory.is_dir():
                    args.log.post(f'Deleting: {directory}')
                    os.system(f'rm -rf {directory}')
                if maski.is_dir():
                    args.log.post(f'Deleting mask: {source}MASCARA.tc*.m')
                    os.system(f'rm -rf {source}MASCARA.tc*.m')
            yclean(vis, imagename, restfreq=restfreq, width=width, start=start,
                   nchan=nchan, spw=spw, **args.tclean_params)

        # Store split filenames
        basename = win['basename']
        if basename not in args.finalcubes:
            args.finalcubes[basename] = [finalimage]
        else:
            args.finalcubes[basename].append(finalimage)

def _join_cubes(args: argparse.NameSpace) -> None:
    """Join cubes."""
    # Test?
    if args.test:
        return

    # Join the cubes
    for suff, val in args.finalcubes.items():
        # Output name
        if 'out_prefix' in args.config:
            prefix = args.config['out_prefix']
            output = (Path(args.basedir) / 'clean' /
                      f'{prefix}.{suff}.cube.image')
        else:
            output = (Path(args.basedir) / 'clean' /
                      f"{args.config['field']}.{suff}.cube.image")
        output = output.expanduser()

        # Check existance
        outputfits = output.with_suffix('.image.fits')
        if args.resume and outputfits.is_file():
            args.log.post(f'Skipping: {output}')
            continue
        elif outputfits.is_file():
            args.log.post(f'Overwriting: {output}')
            os.system(f'rm -rf {output} {outputfits}')

        # Concatenate
        if len(val)==1:
            args.log.post(f'Copying cube: {val}')
            os.system(f'rsync -auvr {val[0]} {output}')
        else:
            args.log.post(f'Joining cubes: {val}')
            join_cubes(val, output, split_option(args.config, 'joinchans'),
                       resume=args.resume, log=args.log.post)

def main(args: argparse.NameSpace) -> None:
    """Program main.

    Args:
      args: command line args.
    """
    # Defaults
    config_defaults = {
        'restfreqs': '',
        'chanrange': '~',
        'names': '',
        'widths': '',
    }
    tclean_defaults = {
        'gridder': 'standard',
        'specmode': 'cube',
        'robust': '0.5',
        'outframe': 'LSRK',
        'interpolation': 'linear',
        'weighting': 'briggs',
        'deconvolver': 'multiscale',
        'scales': '0,5,15',
        'chanchunks': '-1',
        'pblimit': '0.2',
        'perchanweightdensity': 'true',
        'phasecenter': '',
        'uvtaper': '',
    }
    config_defaults.update(tclean_defaults)

    # Command line options
    parser = argparse.ArgumentParser(parents=[casa_logging.logging_parent()])
    parser.add_argument('--basedir', default='', type=str,
                        help='Base directory')
    parser.add_argument('--resume', action='store_true',
                        help='Resume if files are in yclean directory')
    parser.add_argument('--test', action='store_true',
                        help='Just print options used per spw')
    parser.add_argument('uvdata', nargs=1, type=str,
                        help='uv data ms')
    parser.add_argument('configfile', nargs=1, type=str,
                        help='Configuration file name')
    parser.set_defaults(
        pipe=[
            casa_logging.set_logging,
            args_proc.set_config,
            args_proc.get_tclean_params,
            _run_yclean,
            _join_cubes,
        ],
        config=config_defaults,
        section='yclean',
        finalcubes=OrderedDict(),
    )
    args = parser.parse_args(args)

    # Run steps
    for step in args.pipe:
        step(args)

if __name__=='__main__':
    main(sys.argv[1:])
    sys.exit()
