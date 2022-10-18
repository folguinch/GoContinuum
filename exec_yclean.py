"""Execute yclean."""
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, TypeVar, Dict
import argparse
import sys
import os

from casatasks import exportfits
from casatools import image
import numpy as np

from go_continuum import args_proc
from go_continuum import casa_logging
import go_continuum.casa_utils as utils
#try:
from yclean.yclean_parallel import yclean
#except ModuleNotFoundError:
#    try:
#        from go_continuum.yclean_src.yclean_parallel import yclean
#    except ModuleNotFoundError as exc:
#        raise ModuleNotFoundError('YCLEAN is not available') from exc

# Types
Config = TypeVar('Config')
NameSpace = TypeVar('NameSpace')

def split_option(cfg: Config,
                 option: str,
                 ignore_sep: Sequence[str] = (),
                 dtype: Optional[Callable] = None) -> List:
    """Split values from configuration option value.

    The program will use the `,` separator first to split the data, if
    unseccessful it will use space.

    Args:
      cfg: configuration parser proxy.
      option: option.
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

    Returns:
      A list with names for each spw.
    """
    if len(basenames) == 0:
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
      cfg: configuration parser proxy.
      option: parser option.
      match: sequence to match the length to.
      filler: optional; filler value in case option was not set.
      fillerfn: optional; filling function in case option was not set.
      log: optional; logging function.
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

def get_windows(vis: Path, cfg: Config, log: Callable = print) -> List:
    """Define parameters for each spw.

    Args:
      vis: visibility file.
      cfg: configuration parser proxy.
      log: optional; logging function.

    Returns:
      A list with the information for cleaning each spw.
    """
    # Spectral windows and frequencies
    spws = split_option(cfg, 'spws')
    freqs = match_length(cfg, 'restfreqs', spws, log=log)
    bnames = match_length(cfg, 'names', spws, fillerfn=fill_names, log=log)
    widths = match_length(cfg, 'widths', spws, log=log)

    # Spectral window real values after concat
    spws_val = utils.get_spws_indices(vis, spws=spws, log=log)

    # Iterate over spectral windows
    windows = []
    info0 = ['spw', 'spw_val', 'freq', 'name', 'width']
    for info in zip(spws, spws_val, freqs, bnames, widths):
        # Get channel ranges
        spw = info[0]
        if f'chanrange{spw}' in cfg:
            chanrans = split_option(cfg, f'chanrange{spw}')
        elif 'chanranges' in cfg:
            chanrans = split_option(cfg, 'chanranges')
        else:
            chanrans = split_option(cfg, 'chanrange')

        # Replace specific channel width
        kwargs = dict(zip(info0, info))
        if f'width{spw}' in cfg:
            kwargs['width'] = cfg[f'width{spw}']

        # Fill the window information
        windows += fill_window(chanrans, **kwargs)

    return windows

def crop_spectral_axis(img: image,
                       chans: str,
                       outfile: Path):
    """Crop image along the spectral axis.

    Args:
      img: CASA image object.
      chans: channel range.
      outfile: output image file.
    """
    # Identify spectral axis
    summ = img.summary()
    ind = np.where(summ['axisnames'] == 'Frequency')[0][0]

    # Crop image
    aux = img.crop(outfile=str(outfile), axes=ind, chans=chans)
    aux.close()

def join_cubes(inputs: Sequence[Path],
               output: Path,
               channels: Sequence[str],
               resume: bool = False,
               log: Callable = print) -> None:
    """Join cubes at specific channels.

    Args:
      inputs: input cubes to join.
      output: file name.
      channels: channel ranges for spectral cropping.
      resume: optional; resume calculations?
      log: optional; logging function.
    """
    # Check
    if len(channels) != len(inputs):
        raise ValueError('Different length of input and channels')

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
            img = image()
            img = img.open(str(inp.expanduser()))
            img_name = Path(f'temp{i}.image')
            if img_name.is_dir():
                os.system('rm -rf temp*.image')
            crop_spectral_axis(img, chans, img_name)
            img.close()

            # Store filenames
            filelist.append(str(img_name))
        filelist = ' '.join(filelist)

        # Concatenate
        img.imageconcat(outfile=str(imagename), infiles=filelist)
        img.close()

    # Export fits
    imagefits = imagename.with_suffix('.image.fits')
    if resume and imagefits.exists():
        log('Skipping FITS export')
    else:
        exportfits(imagename=str(imagename), fitsimage=str(imagefits),
                   overwrite=True)

    # Clean up
    log('Cleaning up')
    os.system('rm -rf temp*.image')

def _run_yclean(args: NameSpace) -> None:
    """Run yclean."""
    # Resume?
    resume = args.resume
    if resume:
        args.log.post('Resume turned on')

    # Source data
    if 'field' in args.config:
        source = args.config['field']
    elif 'source' in args.config:
        source = args.config['source']
    else:
        raise ValueError('Required values field or source not in config')
    vis = Path(args.uvdata[0])

    # Spectral setup per channel window
    wins = get_windows(vis, args.config, log=args.log.post)

    # Compute common beam?
    if 'joinchans' not in args.config:
        common_beam = args.common_beam
    else:
        common_beam = False

    # Run YCLEAN
    for win in wins:
        # Directory
        name = win['name']
        directory = Path(args.basedir)
        directory = directory / 'yclean' /  f'{source}_{name}'
        args.log.post('-' * 80)
        args.log.post(f'Procesing {name}')

        # Some clean values
        restfreq = win['freq']
        width = win['width']
        start = win['start']
        nchan = int(win['nchan'])
        spw = win['spw_val']
        imagename = directory / f'auto{source}_{name}'

        # Log
        args.log.post(f'vis = {vis}')
        args.log.post(f'imagename = {imagename}')
        args.log.post(f'Spectral window options: {win}')

        # Run
        args.log.post('Running yclean')
        if not resume and directory.is_dir():
            args.log.post('Cleaning directories')
            args.log.post(f'Deleting: {directory}')
            os.system(f'rm -rf {directory}')
        directory.mkdir(exist_ok=True, parents=True)
        finalimage, _ = yclean(vis, imagename, nproc=args.nproc[0],
                               common_beam=common_beam, resume=resume,
                               full=args.full, log=args.log.post,
                               restfreq=restfreq, width=width,
                               start=start, nchan=nchan,
                               spw=spw, **args.tclean_params)

        # Store split filenames
        basename = win['basename']
        if basename not in args.finalcubes:
            args.finalcubes[basename] = [finalimage]
        else:
            args.finalcubes[basename].append(finalimage)

def _join_cubes(args: NameSpace) -> None:
    """Join the final cubes."""
    # Check if step is needed
    if 'joinchans' not in args.config:
        return

    # Source name for naming (reverse if for future source dependent
    # processing)
    if 'source' in args.config:
        source = args.config['source']
    elif 'field' in args.config:
        source = args.config['field']
    else:
        raise ValueError('Required values field or source not in config')

    # Join the cubes
    directory = Path(args.basedir) / 'yclean'
    for suff, val in args.finalcubes.items():
        # Output name
        if 'out_prefix' in args.config:
            prefix = args.config['out_prefix']
            output = directory / f'{prefix}.{suff}.image'
        else:
            output = directory / f'{source}.{suff}.image'

        # Check existance
        outputfits = output.with_suffix('.image.fits')
        if args.resume and outputfits.exists():
            args.log.post(f'Skipping: {output}')
        elif outputfits.exists():
            args.log.post(f'Overwriting: {output}')
            os.system(f'rm -rf {output} {outputfits}')

        # Concatenate
        if len(val) == 1:
            args.log.post(f'Copying cube: {val}')
            os.system(f'rsync -auvr {val[0]} {output}')
        else:
            args.log.post(f'Joining cubes: {val}')
            join_cubes(val, output,
                       split_option(args.config, 'joinchans'),
                       resume=args.resume, log=args.log.post)

def main(args: List) -> None:
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

    # Pipe
    pipe=[casa_logging.set_logging,
          args_proc.set_config,
          args_proc.get_tclean_params,
          _run_yclean,
    ]

    # Command line options
    parser = argparse.ArgumentParser(parents=[casa_logging.logging_parent()])
    parser.add_argument('--basedir', default='', type=str,
                        help='Base directory')
    parser.add_argument('--nproc', nargs=1, type=int, default=[5],
                        help='Number of processes for parallel processing')
    parser.add_argument('--resume', action='store_true',
                        help='Resume if files are in yclean directory')
    parser.add_argument('--common_beam', action='store_true',
                        help='Compute the common beam of the final cube')
    parser.add_argument('--full', action='store_true',
                        help='Store intermediate images and masks')
    parser.add_argument('uvdata', nargs=1, type=str,
                        help='uv data ms')
    parser.add_argument('configfile', nargs=1, type=str,
                        help='Configuration file name')
    parser.set_defaults(
        tclean_params=None,
        config=config_defaults,
        section='yclean',
        finalcubes=OrderedDict(),
    )
    args = parser.parse_args(args)

    # Run steps
    for step in pipe:
        step(args)

    return True

if __name__=='__main__':
    main(sys.argv[1:])
