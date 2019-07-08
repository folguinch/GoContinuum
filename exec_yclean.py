import os, argparse
from ConfigParser import ConfigParser
from ConfigParser import NoOptionError

import scipy
import numpy as np

def get_nchans(chanrange):
    i, f = map(int, chanrange.split('~'))
    return abs(f-i) + 1

def fill_molecules(s, j, freq, chanrange):
    spw = 'spw%s' % s
    try:
        start = int(chanrange.split('~')[0])
        name = 'spw%s_%i' % (s, j+1)
        nchan = get_nchans(chanrange)
    except ValueError:
        start = ''
        name = spw
        nchan = -1

    return [name, freq, '', start, nchan, spw, s]

def get_windows(conf):
    spws = conf.get('yclean', 'spws').split(',')
    freqs = conf.get('yclean', 'restfreqs').split()
    if len(spws)!=len(freqs) and conf.get('yclean', 'restfreqs')=='':
        freqs = ['']*len(spws)
    elif len(spws)!=len(freqs):
        print 'WARN: length of frequencies does not match length of spws'
        print 'WARN: ignoring frequencies'
        freqs = ['']*len(spws)
    exclude_opts = ['chanranges', 'chanrange']
    filter_opts = ['chanrange' in opt and opt not in exclude_opts \
            for opt in conf.options('yclean')]
    if any(filter_opts):
        molecules = []
        nsplits = []
        for spw in spws:
            try:
                chanranges = conf.get('yclean', 'chanrange%s' % spw).split()
            except NoOptionError:
                chanranges = conf.get('yclean', 'chanrange').split()
            molecules += [fill_molecules(spw, j, freqs[int(spw)], chran) \
                    for j,chran in enumerate(chanranges)]
            nsplits += [len(chanranges)-1]
    else:
        if 'chanranges' in conf.options('yclean'):
            chanranges = conf.get('yclean', 'chanranges').split()
        else:
            chanranges = conf.get('yclean', 'chanrange').split()
        molecules = [fill_molecules(spw, j, frq, chran) \
                for spw, frq in zip(spws, freqs) \
                for j,chran in enumerate(chanranges)]
        nsplits = [len(chanranges)-1]*len(spws)
            
    return molecules, nsplits

def crop_spectral_axis(chans, outfile):
    s = ia.summary()
    ind = np.where(s['axisnames']=='Frequency')[0][0]

    aux = ia.crop(outfile=outfile, axes=ind, chans=chans)
    aux.close()

def join_cubes(inputs, output, channels):
    assert len(channels)==len(inputs)
    # Crop images
    for i,(chans,inp) in enumerate(zip(channels, inputs)):
        ia.open(os.path.expanduser(inp))
        img_name = 'temp%i.image' % i
        aux = crop_spectral_axis(chans, img_name)
        ia.close()

        if i==0:
            filelist = img_name
        else:
            filelist += ' '+img_name 

    # Concatenate
    imagename = os.path.expanduser(output)+'.image'
    ia.imageconcat(outfile=imagename, infiles=filelist)
    exportfits(imagename=imagename, 
            fitsimage=imagename.replace('.image','.fits'))
    ia.close()

    print 'Cleaning up'
    os.system('rm -rf temp*.image')

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    parser.add_argument('--basedir', default='./', type=str,
            help='Base directory')
    parser.add_argument('uvdata', nargs=1, type=str,
            help='uv data ms')
    parser.add_argument('configfile', nargs=1, type=str,
            help='Configuration file name')
    args = parser.parse_args()

    config = ConfigParser({'restfreqs':[''], 'chanrange':'~'})
    config.read(args.configfile[0])
    section = 'yclean'

    source = config.get('yclean', 'field')
    vlsrsource = config.getfloat('yclean', 'vlsr')
    phasecenter = ''
    uvtaper = ''

    # INFO DIRECTORIES
    dirvis = os.path.dirname(args.uvdata[0])
    diryclean = os.path.expanduser(config.get(section, 'dir'))
    execfile(os.path.join(diryclean, "def_domask_lines.py"))
    execfile(os.path.join(diryclean, 'secondMaxLocal.py'))

    # Spectral setup
    molecules, nsplits = get_windows(config)

    # Clean options
    gridder = 'standard'
    wprojplanes = None 
    specmode = 'cube'
    outframe = 'LSRK'
    interpolation = 'linear'
    interactive = False
    imsize = map(int, config.get(section, 'imsize').split())
    cell = str(config.get(section, 'cellsize'))
    weighting = 'briggs'
    robust = 0.5
    deconvolver = 'multiscale' 
    scales = [0,5,15]
    #rms = 5.7e-3
    #peak_int = 0.136# these variables are not used apparently
    #SN_ratio =  26 # these variables are not used apparently
    chanchunks = 2
    limitMaskLevel = 4.0
    pblimit = .2

    # Run YCLEAN
    finalcubes = []
    for moldata in molecules:
        it = 0
        mol = moldata[0]
        restfreq = moldata[1]
        dirmol = os.path.realpath(os.path.join(args.basedir, 'yclean',
            source+'_'+mol))
        os.system('rm -rf '+ dirmol)
        width = moldata[2]
        start = moldata[3]
        molvis = moldata[5]
        nchan = int(moldata[4])
        spwline = moldata[6]
        print "Procesing ", mol
        vis = args.uvdata[0]
        imagename = os.path.realpath(os.path.join(dirmol,
            'auto'+source+'_'+mol+'.12m'))
        print vis, imagename

        execfile(os.path.join(diryclean, 'yclean_parallel.py'))
        finalcubes += [imagename+'.tc_final.fits']

    # Join the cubes
    j = 0
    spws = conf.get('yclean', 'spws').split(',')
    for spw, ns in zip(spws, nsplits):
        output = os.path.join(args.basedir, 'clean',
                source+'.spw%i.cube' % spw)
        nsub = ns + 1
        if ns==0:
            os.system('cp finalcubes[j] output')
        else:
            join_cubes(finalcubes[j:j+nsub], output, 
                    config.get('yclean','joinchans').split)
        j += nsub
        
if __name__=='__main__':
    main()
