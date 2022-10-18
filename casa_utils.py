"""Utilities for working with CASA."""
from inspect import signature
from typing import Optional, Sequence, List, TypeVar, Callable
from pathlib import Path
from configparser import ConfigParser
from collections import OrderedDict
import inspect

from casatasks import vishead, tclean

# Types
Logger = TypeVar('Logger')

def get_spws(vis: Path) -> List:
    """Retrieve the spws in a visibility ms."""
    return vishead(vis=str(vis), mode='get', hdkey='spw_name')[0]

def get_spws_indices(vis: 'Path',
                     spws: Optional[Sequence[str]] = None,
                     log: Callable = print) -> List:
    """Get the indices of the spws.

    This task search for duplicated spws (e.g. after measurement set
    concatenation) and groups the spws indices.

    Args:
      vis: measurement set.
      spws: optional; selected spectral windows.
      log: optional; logging function.

    Returns:
      A list with the spws in the vis ms.
    """
    # Spectral windows names
    # Extract name by BB_XX and subwin SW_YY
    names = [aux.split('#')[2]+'_'+aux.split('#')[3] for aux in get_spws(vis)]
    name_set = set(names)

    # Cases
    if len(name_set) != len(names):
        log('Data contains duplicated spectral windows')
        spwinfo = OrderedDict()
        for i, key in enumerate(names):
            if key not in spwinfo:
                spwinfo[key] = f'{i}'
            else:
                spwinfo[key] += f',{i}'
    else:
        spwinfo = OrderedDict(zip(names, map(str, range(len(names)))))

    # Spectral windows indices
    if spws is not None:
        spw_ind = list(map(int, spws))
    else:
        spw_ind = list(range(len(name_set)))

    return [spw for i, spw in enumerate(spwinfo.values()) if i in spw_ind]

def check_tclean_params(config: ConfigParser,
                        required: Sequence[str] = ('cell', 'imsize')) -> None:
    """Check required config params."""
    # Check required arguments are in config
    for opt in required:
        if opt not in config:
            raise KeyError(f'Missing {opt} in configuration')

def get_tclean_params(
    config: ConfigParser,
    ignore_keys: Sequence[str] = ('vis', 'imagename', 'spw'),
    float_keys: Sequence[str]  = ('robust', 'pblimit', 'pbmask'),
    int_keys: Sequence[str] = ('niter', 'chanchunks'),
    bool_keys: Sequence[str] = ('interactive', 'parallel', 'pbcor',
                                'perchanweightdensity'),
) -> dict:
    """Filter input parameters and convert values to the correct type.

    Args:
      config: ConfigParser proxy with input parameters to filter.
      ignore_keys: optional; tclean parameters to ignore.
      float_keys: optional; tclean parameters to convert to float.
      int_keys: optional; tclean parameters to convert to int.
      bool_keys: optional; tclean parameters to convert to bool.
    """
    # Check required parameters
    check_tclean_params(config)

    # Get paramters
    tclean_pars = {}
    for key in signature(tclean).parameters:
        if key not in config or key in ignore_keys:
            continue
        #Check for type:
        if key in float_keys:
            tclean_pars[key] = config.getfloat(key)
        elif key in int_keys:
            tclean_pars[key] = config.getint(key)
        elif key in bool_keys:
            tclean_pars[key] = config.getboolean(key)
        elif key == 'imsize':
            tclean_pars[key] = list(map(int, config.get(key).split()))
            if len(tclean_pars[key]) == 1:
                tclean_pars[key] = tclean_pars[key] * 2
        elif key == 'scales':
            tclean_pars[key] = list(map(int, config.get(key).split(',')))
        else:
            tclean_pars[key] = config.get(key)

    return tclean_pars

def put_rms(imagename: Path,
            box: str = '',
            log: Callable = print) -> None:
    """Put the rms value in the header."""
    rms = tasks.imhead(imagename=imagename, mode='get', hdkey='rms')
    if rms:
        log('rms already in header')
        log(f'Image rms: {rms*1000} mJy/beam')
        return

    # Get rms
    log(f'Computing rms for: {imagename}')
    for dummy in range(5):
        try:
            stats = tasks.imstat(imagename=imagename, box=box, stokes='I')
            if box == '':
                rms = 1.482602219 * stats['medabsdevmed'][0]
            else:
                rms = 1. * stats['rms'][0]
            break
        except TypeError:
            log(f'Imstat failed (try {dummy+1}), trying again ...')
            continue

    # Put in header
    tasks.imhead(imagename=imagename, mode='put', hdkey='rms', hdvalue=rms)
    log(f'Image rms: {rms*1000} mJy/beam')

def crop_spectral_axis(imagename: Path, chans: str, outfile: Path) -> None:
    """Crop spectral axis of input image.

    Args:
      imagename: image name.
      chans: channel range to keep.
      outfile: output file name.
    """
    header_sum = tasks.imhead(imagename=imagename)
    ind = np.where(header_sum['axisnames'] == 'Frequency')[0][0]

    img = casatools.image()
    img.open(imagename)
    aux = img.crop(outfile=outfile, axes=ind, chans=chans)
    aux.close()
    img.close()

#def get_value(cfg, sect, opt, default=None, n=None, sep=','):
#    # Initial value
#    value = cfg.get(sect, opt)
#
#    # Split value
#    value = value.split(sep)
#
#    # Cases:
#    if len(value) == 0:
#        value = ''
#    elif len(value) == 1 and n is None:
#        value = value[0]
#    elif len(value) > 1 and n is None:
#        # Just in case someone used coma separated value for single eb
#        casalog.post('More than one value for %s, using all' % opt, 'WARN')
#        value = ' '.join(value)
#    elif n>=0:
#        value = value[n]
#    else:
#        value = default
#
#    return value
#
#def get_bool(values):
#    newval = []
#
#    for val in values:
#        if val.lower() in ['true', '1']:
#            newval += [True]
#        else:
#            newval += [False]
#
#    return newval
#
#def run_cal(cfg, section, vis, neb=None):
#    # Check for EB specific sections
#    if neb is not None:
#        aux = '%s%i' % (section, neb)
#        if cfg.has_section(aux):
#            sect = aux
#            ebind = None
#        else:
#            sect = section
#            ebind = neb - 1
#    else:
#        sect = section
#        ebind = None
#
#    # Calibrate
#    if not cfg.has_section(sect):
#        casalog.post('Apply (self-)calibration table not requested')
#        return
#    else:
#        # Back up flags
#        casalog.post('Using gaintable from section: %s' % sect)
#        flagmanager(vis=vis, mode='save', versionname='before_selfcal',
#                merge='replace', comment='before selfcal')
#
#        # Applycal
#        field = cfg.get(sect, 'field')
#        gaintable = get_value(cfg, sect, 'gaintable', n=ebind).split()
#        spwmap = map(int, get_value(cfg, sect, 'spwmap', n=ebind).split())
#        calwt = get_bool(get_value(cfg, sect, 'calwt', n=ebind).split())
#        flagbackup = cfg.getboolean(sect, 'flagbackup')
#        interp = get_value(cfg, sect, 'interp', n=ebind, sep=';').split()
#        applycal(vis=vis, field=field, spwmap=spwmap, gaintable=gaintable,
#                calwt=calwt, flagbackup=flagbackup, interp=interp)
#
#        # Split ms
#        outsplitvis = vis + '.selfcal'
#        split(vis=vis, outputvis=outsplitvis, datacolumn='corrected')
#
###################### Cube/image utils #####################
#def crop_spectral_axis(infile, outfile, chans, box=None):
#    ia.open(infile)
#    s = ia.summary()
#    ind = np.where(s['axisnames']=='Frequency')[0][0]
#
#    #if box is not None:
#    #    box = 'box [ [ %ipix , %ipix] , [%ipix, %ipix ] ]' % tuple(box)
#    #    ind = [0,1] + ind
#    #else:
#    #    box = ''
#    aux = ia.crop(outfile=outfile, axes=ind, chans=chans, stretch=True)
#    ia.close()
#
#    return aux
#
#def join_cubes(inputs, output, channels, resume=False, box=None):
#    """Join cubes at specific channels
#    """
#    if len(channels)!=len(inputs):
#        raise ValueError("Length of channels(%i)!=inputs(%i)" %
#                (len(channels),len(inputs)))
#
#    # Concatenated image
#    imagename = os.path.expanduser(output)
#
#    # Join
#    if resume and os.path.isdir(imagename):
#        casalog.post('Skipping concatenated image: %s' % imagename)
#    else:
#        if os.path.isdir(imagename):
#            os.system('rm -rf %s' % imagename)
#        # Crop images
#        for i,(chans,inp) in enumerate(zip(channels, inputs)):
#            infile = os.path.expanduser(inp)
#            img_name = 'temp%i.image' % i
#            if os.path.isdir(img_name):
#                os.system('rm -rf temp*.image')
#            aux = crop_spectral_axis(infile, img_name, chans, box=box)
#            aux.close()
#
#            if i==0:
#                filelist = img_name
#            else:
#                filelist += ' '+img_name
#
#        # Concatenate
#        ia.imageconcat(outfile=imagename, infiles=filelist)
#        ia.close()
#
#    # Put rms
#    put_rms(imagename)
#
#    # Export fits
#    if resume and os.path.isfile(imagename+'.fits'):
#        casalog.post('Skipping FITS export')
#    else:
#        exportfits(imagename=imagename, fitsimage=imagename+'.fits',
#                overwrite=True)
#
#    # Clean up
#    casalog.post('Cleaning up')
#    os.system('rm -rf temp*.image')
#
#    return True
#
###################### Argparse Processing #####################
#def verify_args(args):
#    # File existance
#    # Visibilities
#    vis = args.uvdata[0]
#    if not os.path.isdir(vis):
#        raise IOError('MS %s does not exist' % vis)
#    # Configuration file
#    config = args.configfile[0]
#    if not os.path.isfile(config):
#        raise IOError('Config file %s does not exist' % config)
#    # Channel files
#    for chanfile in args.chans:
#        if not os.path.isfile(chanfile):
#            raise IOError('Channel file %s does not exist' % chanfile)
#
#    # Number of spws
#    nspw = len(get_spws(vis))
#    if len(args.chans) != nspw:
#        raise ValueError('Number of spws does != number of channel files')
#
#def load_config(args):
#    # Initialize
#    if args.config is not None and hasattr(args.config, 'keys'):
#        args.config = ConfigParser(args.config)
#    else:
#        args.config = ConfigParser()
#
#    # Load file
#    args.config.read(args.configfile[0])
#
#def load_chan_list(args):
#    fitspws = []
#    for i, chfile in enumerate(args.chans):
#        casalog.post('SPW = %i' % i)
#        casalog.post('Channel file = %s' % chfile)
#        with open(chfile, 'r') as chlist:
#            lines = chlist.readlines()
#        if len(lines)!=1:
#            raise ValueError('Channel file needs only 1 line')
#        else:
#            fitspw = "%i:%s" % (i, lines[0])
#            fitspws += [fitspw.strip()]
#    args.fitspw = ','.join(fitspws)
#
#def _run_cal(args):
#    if not os.path.isdir(args.outvis):
#        raise IOError('MS %s does not exist' % args.outvis)
#    run_cal(args.config, args.calsect, args.outvis, neb=args.eb[0])
#
###################### Argparse actions #####################
#class NormalizePath(argparse.Action):
#    """Normalizes a path or filename"""
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        newval = []
#        for val in values:
#            newval += [os.path.realpath(os.path.expandvars(
#                                        os.path.expanduser(val)))]
#        setattr(namespace, self.dest, newval)
=======
>>>>>>> 89cfd72200ba9cf0d8c7f4a5ebb0a69a2b573807
