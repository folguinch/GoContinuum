"""Execute yclean."""
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any, List, Optional, Sequence
import argparse
import configparser as cparser
import sys
import time

from casatasks import casalog
import numpy as np
import scipy
import scipy.ndimage

# Local utils
import casa_utils as utils

def split_option(cfg: cparser.ConfigParser, option: str,
                 ignore_sep: Sequence[str] = (),
                 dtype: Optional[Any] = None) -> List:
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
    val = cfg[option]

    # Use coma first
    if ',' in val and ',' not in ignore_sep:
        vals = val.split(',')
    else:
        vals = val.split()

    # Map dtype
    if dtype is not None:
        vals = map(dtype, vals)
 
    return vals

def get_nchans(chanrange: str) -> int:
    """Determine the number of channels from a channel range.

    Args:
      chanrange: channel range.

    Returns:
      The number of channels in the range.
    """
    i, f = map(int, chanrange.split('~'))
    return abs(f - i) + 1

def fill_window(chanranges: Sequence[str], **kwargs) -> List:
    """Fill window information for CLEANing.

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
      basenames: base name.
      spws: spw list.
      default: optional; default name.
    """
    if len(basenames)==0:
        base = default
    else:
        base = vals[0]

    return [f'{base}{spw[0]}' for spw in spws]

def match_length(cfg, sect, opt, match, filler='', fillerfn=None):
    """Read values from configuration and match the length to match
    """
    # Fill function:
    def _fill(val):
        if fillerfn is not None:
            return fillerfn(val, match)
        else:
            return [filler]*len(match)

    # Original values
    vals = split_option(cfg, sect, opt)
    nvals = len(vals)

    # Match size
    nmatch = len(match)
    if nvals!=nmatch and nvals==0:
        # Value was not set
        vals = _fill(vals)
    elif nvals!=nmatch:
        # Value was set but with incorrect value
        casalog.post('Length of %s does not match with pattern' % opt,
                'WARN')
        casalog.post('Ignoring %s' % opt, 'WARN')
        vals = _fill(vals)
    else:
        # Match but check for none
        vals = [val if val.lower()!='none' else filler for val in vals]
    assert len(vals) == nmatch

    return vals

def get_windows(vis, conf, section='yclean'):
    """Define parameters for each spw
    """

    # Spectral windows and frequencies
    spws = split_option(conf, section, 'spws')
    freqs = match_length(conf, section, 'restfreqs', spws)
    bnames = match_length(conf, section, 'names', spws, fillerfn=fill_names)
    widths = match_length(conf, section, 'widths', spws)

    # Spectral window real values after concat
    spws_val = utils.get_spws_indices(vis, spws=spws)

    # Iterate over spectral windows
    windows = []
    info0 = ['spw', 'spw_val', 'freq', 'name', 'width']
    for info in zip(spws, spws_val, freqs, bnames, widths):
        # Get channel ranges
        spw = info[0]
        if 'chanrange%s' % spw in conf.options(section):
            key = 'chanrange%s' % (spw,)
            chanrans = split_option(conf, section, key)
        elif 'chanranges' in conf.options('yclean'):
            chanrans = split_option(conf, section, 'chanranges')
        else:
            chanrans = split_option(conf, section, 'chanrange')

        # Replace specific channel width
        kwargs = dict(zip(info0,info))
        if conf.has_option(section, 'width%s' % spw):
            key = 'width%s' % spw
            kwargs['width'] = conf.get(section, key)
        
        # Fill the window information
        windows += fill_window(chanrans, **kwargs)

    return windows

def crop_spectral_axis(chans, outfile):
    s = ia.summary()
    ind = np.where(s['axisnames']=='Frequency')[0][0]

    aux = ia.crop(outfile=outfile, axes=ind, chans=chans)
    aux.close()

def put_rms(imagename, box=''):
    rms = imhead(imagename=imagename, mode='get', hdkey='rms')
    if rms is not False:
        casalog.post('rms already in header')
        casalog.post('Image rms: %f mJy/beam' % (rms*1E3,))
        return

    # Get rms
    casalog.post('Computing rms for: ' + imagename)
    stats = imstat(imagename=imagename, box=box, stokes='I')
    if box=='':
        rms = 1.482602219*stats['medabsdevmed'][0]
    else:
        rms = stats['rms'][0]

    # Put in header
    imhead(imagename=imagename, mode='put', hdkey='rms',
            hdvalue=rms)
    casalog.post('Image rms: %f mJy/beam' % (rms*1E3,))

def join_cubes(inputs, output, channels, resume=False):
    """Join cubes at specific channels
    """
    assert len(channels)==len(inputs)

    # Concatenated image
    imagename = os.path.expanduser(output)

    # Join
    if resume and os.path.isdir(imagename):
        casalog.post('Skipping concatenated image: %s' % imagename)
    else:
        if os.path.isdir(imagename):
            os.system('rm -rf %s' % imagename)
        # Crop images
        for i,(chans,inp) in enumerate(zip(channels, inputs)):
            ia.open(os.path.expanduser(inp))
            img_name = 'temp%i.image' % i
            if os.path.isdir(img_name):
                os.system('rm -rf temp*.image')
            aux = crop_spectral_axis(chans, img_name)
            ia.close()

            if i==0:
                filelist = img_name
            else:
                filelist += ' '+img_name 

        # Concatenate
        ia.imageconcat(outfile=imagename, infiles=filelist)
        ia.close()

    # Put rms
    put_rms(imagename)

    # Export fits
    if resume and os.path.isfile(imagename+'.fits'):
        casalog.post('Skipping FITS export')
    else:
        exportfits(imagename=imagename, fitsimage=imagename+'.fits',
                overwrite=True)

    # Clean up
    casalog.post('Cleaning up')
    os.system('rm -rf temp*.image')

    return True

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('--basedir', default='', type=str,
                        help='Base directory')
    parser.add_argument('--logfile', default=None, nargs=1, type=str,
                        help='Log file name')
    parser.add_argument('--resume', action='store_true',
                        help='Resume if files are in yclean directory')
    parser.add_argument('--test', action='store_true',
                        help='Just print options used per spw')
    parser.add_argument('uvdata', nargs=1, type=str,
                        help='uv data ms')
    parser.add_argument('configfile', nargs=1, type=str,
                        help='Configuration file name')
    args = parser.parse_args()

    # Logging
    if args.logfile is not None:
        casalog.setlogfile(args.logfile[0])

    # Configuration
    parserfile = os.Path(args.configfile[0])
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
    configuration = cparser.ConfigParser(config_defaults)
    if parserfile.exists():
        configuration.read(args.configfile[0])
    else:
        raise IOError(f'Config file does not exists: {parserfile}')
    section = 'yclean'
    cfg = configuration[section]

    # Resume?
    resume = args.resume
    if resume:
        casalog.post('Resume turned on')

    # Source data
    source = cfg['field']
    if cfg['phasecenter'] != '':
        casalog.post(f"Phase center = {cfg['phasecenter']}")

    # Directories
    dirvis = os.path.dirname(args.uvdata[0])
    diryclean = os.path.expanduser(config.get(section, 'dir'))
    if not os.path.isdir(diryclean):
        raise ValueError('YCLEAN directory does not exist: %s' % diryclean)
    execfile(os.path.join(diryclean, "def_domask_lines.py"))
    execfile(os.path.join(diryclean, 'secondMaxLocal.py'))

    # Spectral setup
    wins = get_windows(args.uvdata[0], config)

    # Clean options
    gridder = config.get(section, 'gridder')
    casalog.post('Gridder = %s' % gridder)
    wprojplanes = None 
    specmode = config.get(section, 'specmode')
    casalog.post('Specmode = %s' % specmode)
    outframe = config.get(section, 'outframe')
    casalog.post('Outframe = %s' % outframe)
    interpolation = config.get(section, 'interpolation')
    interactive = False
    imsize = map(int, config.get(section, 'imsize').split())
    casalog.post('Imsize = %r' % imsize)
    cell = config.get(section, 'cell')
    casalog.post('Cell size = %s' % cell)
    weighting = config.get(section, 'weighting')
    robust = config.getfloat(section, 'robust')
    casalog.post('Robust = %s' % robust)
    deconvolver = config.get(section, 'deconvolver')
    casalog.post('Deconvolver = %s' % deconvolver)
    if deconvolver == 'multiscale':
        scales = map(int, split_option(config, section, 'scales'))
        casalog.post('Scales = %r' % scales)
    else:
        scales = []
    #rms = 5.7e-3
    #peak_int = 0.136# these variables are not used apparently
    #SN_ratio =  26 # these variables are not used apparently
    chanchunks = config.getint(section, 'chanchunks')
    limitMaskLevel = config.getfloat(section, 'limitmasklevel')
    pblimit = config.getfloat(section, 'pblimit')
    #pbmask = config.getfloat(section, 'pbmask')
    perchanweightdensity = config.getboolean(section, 'perchanweightdensity')

    # Run YCLEAN
    finalcubes = OrderedDict()
    for win in wins:
        it = 0
        # Directory
        name = win['name']
        dirit = os.path.join(args.basedir, 'yclean', source+'_'+name)
        casalog.post("-"*80)
        casalog.post("Procesing %s" % name)

        # Other clean values
        #molvis = moldata[5]
        vis = args.uvdata[0]
        restfreq = win['freq']
        width = win['width']
        start = win['start']
        nchan = int(win['nchan'])
        spwline = win['spw_val']
        imagename = os.path.join(dirit, 'auto'+source+'_'+name+'.12m')

        # Log
        casalog.post('vis = %s' % vis)
        casalog.post('imagename = %s' % imagename)
        casalog.post('Spectral window options: %r' % win)
        if args.test:
            continue
        
        # Run
        finalimage = imagename+'.tc_final.fits'
        if os.path.isfile(finalimage) and RESUME:
            casalog.post('Skipping: %s' % finalimage)
        else:
            casalog.post('Running yclean parallel')
            if not RESUME:
                casalog.post('Cleaning directories')
                if os.path.isdir(dirit):
                    casalog.post('Deleting: %s' % dirit)
                    os.system('rm -rf '+ dirit)
                if os.path.isdir(source+'MASCARA.tc0.m'):
                    casalog.post('Deleting: %sMASCARA.tc*.m' % source)
                    os.system('rm -rf '+source+'MASCARA.tc*.m')
            execfile(os.path.join(diryclean, 'yclean_parallel.py'))

        # Store split filenames
        basename = win['basename']
        if basename not in finalcubes:
            finalcubes[basename] = [finalimage]
        else:
            finalcubes[basename] += [finalimage]

    # Join the cubes
    if args.test:
        return True
    for suff, val in finalcubes.items():
        # Output name
        if config.has_option(section, 'out_prefix'):
            prefix = config.get(section, 'out_prefix')
            output = os.path.join(args.basedir, 'clean', 
                    prefix+'.%s.cube.image' % suff)
        else:
            output = os.path.join(args.basedir, 'clean', 
                    source+'.%s.cube.image' % suff)
        output = os.path.expanduser(output)

        # Check existance
        outputfits = output + '.fits'
        if RESUME and os.path.isfile(outputfits):
            casalog.post('Skipping: %s' % output)
            continue
        elif os.path.exists(outputfits):
            casalog.post('Overwriting: %s' % output)
            os.system('rm -rf %s %s' % (output, outputfits))

        # Concatenate
        if len(val)==1:
            casalog.post('Copying cube: %r' % val)
            os.system('rsync -auvr $s $s' % (val[0], output))
        else:
            casalog.post('Joining cubes: %r' % val)
            join_cubes(val, output, split_option(config, section, 'joinchans'),
                    resume=RESUME)

    return True
        
if __name__=='__main__':
    main(sys.argv[1:])
    exit()
