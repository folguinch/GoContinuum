import os, argparse, sys
from ConfigParser import ConfigParser
from ConfigParser import NoOptionError
from collections import Counter, OrderedDict
import time

import scipy
import scipy.ndimage
import numpy as np

# Local utils
aux = os.path.dirname(sys.argv[2])
sys.path.insert(0, aux)
import casa_utils as utils

def split_option(cfg, sect, opt, ignore_sep=[], dtype=None):
    """Split values from configuration option value

    The program will use the "," separator first to split the data, if
    unseccessful it will use space.

    Parameters:
        cfg (str): Configuration parser
        sect (str): Section
        opt (str): Option
    Optional:
        ignore_sep (list): Ignore separator (use if "," is allowed in value)
        dtype (function): Map values to dtype
    """
    # Original value
    val = cfg.get(sect, opt)

    # Use coma first
    if ',' in val:
        vals = val.split(',')
    else:
        vals = val.split()

    # Map dtype
    if dtype is not None:
        vals = map(dtype, vals)
    
    return vals

def get_nchans(chanrange):
    """Determine the number of channels from a channel range

    Parameters:
        chanrange (str): Channel range
    """
    i, f = map(int, chanrange.split('~'))
    return abs(f-i) + 1

def fill_window(chanranges, **kwargs):
    # Check basename
    basename = kwargs.setdefault('name', 'spw%s' % (kwargs['spw'],))
    if basename=='':
        kwargs['name'] = 'spw%s' % kwargs['spw']

    # Fill information
    window = []
    for i, chanran in enumerate(chanranges):
        info = {'width':'', 'basename':kwargs['name']}
        info.update(kwargs)
        
        # Fill info
        try:
            info['start'] = int(chanran.split('~')[0])
            info['nchan'] = get_nchans(chanran)
            # Update name
            if len(chanranges)>1:
                info['name'] = info['name'] + '_%i' % (i+1,)
        except ValueError:
            info['start'] = ''
            info['nchan'] = -1

        window += [info]

    return window

def fill_names(vals, spws, default='spw'):
    """Create name base
    """
    if len(vals)==0:
        base = default
    else:
        base = vals[0]

    return ['%s%s' % (base, spw[0]) for spw in spws]

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
    """
    """

    # Spectral windows and frequencies
    spws = split_option(conf, section, 'spws')
    freqs = match_length(conf, section, 'restfreqs', spws)
    bnames = match_length(conf, section, 'names', spws, fillerfn=fill_names)

    # Spectral window real values after concat
    spws_val = utils.get_spws_indices(vis, spws=spws)

    # Iterate over spectral windows
    nsplits = []
    windows = []
    info0 = ['spw', 'spw_val', 'freq', 'name']
    for info in zip(spws, spws_val, freqs, bnames):
        # Get channel ranges
        spw = info[0]
        if 'chanrange%s' % spw in conf.options(section):
            key = 'chanrange%s' % (spw,)
            chanrans = split_option(conf, section, key)
        elif 'chanranges' in conf.options('yclean'):
            chanrans = split_option(conf, section, 'chanranges')
        else:
            chanrans = split_option(conf, section, 'chanrange')
        nsplits += [len(chanrans)-1]
        
        # Fill the window information
        windows += fill_window(chanrans, **dict(zip(info0,info)))

    return windows, nsplits

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
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    parser.add_argument('--basedir', default='', type=str,
            help='Base directory')
    parser.add_argument('--resume', action='store_true',
            help='Resume if files are in yclean directory')
    parser.add_argument('uvdata', nargs=1, type=str,
            help='uv data ms')
    parser.add_argument('configfile', nargs=1, type=str,
            help='Configuration file name')
    args = parser.parse_args()

    # Configuration
    config_defaults = {'restfreqs':'', 'chanrange':'~', 'names':''}
    tclean_defaults = {'gridder':'standard', 'specmode':'cube', 'robust':'0.5',
            'outframe':'LSRK', 'interpolation':'linear', 'weighting':'briggs',
            'deconvolver':'multiscale', 'scales':'0,5,15', 'chanchunks':'1',
            'limitmasklevel':'4.0', 'pblimit':'0.2'}
    config_defaults.update(tclean_defaults)
    config = ConfigParser(config_defaults)
    config.read(args.configfile[0])
    section = 'yclean'

    # Global options
    RESUME = args.resume

    # Source data
    source = config.get(section, 'field')
    vlsrsource = config.getfloat(section, 'vlsr')
    phasecenter = ''
    uvtaper = ''

    # Directories
    dirvis = os.path.dirname(args.uvdata[0])
    diryclean = os.path.expanduser(config.get(section, 'dir'))
    execfile(os.path.join(diryclean, "def_domask_lines.py"))
    execfile(os.path.join(diryclean, 'secondMaxLocal.py'))

    # Spectral setup
    wins, nsplits = get_windows(args.uvdata[0], config)

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

    # Run YCLEAN
    finalcubes = OrderedDict()
    for win in wins:
        it = 0
        # Directory
        name = win['name']
        dirit = os.path.join(args.basedir, 'yclean', source+'_'+name)
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
    main()
    exit()
