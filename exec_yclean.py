import os, argparse
from ConfigParser import ConfigParser

import scipy
import numpy as np

from join_cubes import join_cubes

def get_nchans(chanrange):
    i, f = map(int, ch.split('~'))
    return abs(f-i) + 1

def fill_molecules(s, j, freqs, chanranges, nchans):
    fmt1 = 'spw%i' 
    fmt2 = fmt1 + '_%i'
    fmt3 = '%i:%s'

    name = fmt2 % (s,j)
    freq = freqs[s]
    nchan = nchans[j]
    spw = fmt1 % s
    chran = fmt3 % (s, chanranges[j])

    return [name, freq, '', '', nchan, spw, chran]

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

    config = ConfigParser()
    config.read(args.configfile[0])

    source = config.get('yclean', 'field')
    vlsrsource = config.getfloat('yclean', 'vlsr')
    phasecenter = ''
    uvtaper = ''

    # INFO DIRECTORIES
    dirvis = os.path.dirname(args.uvdata)
    diryclean = os.path.expanduser(config.get('yclean', 'dir'))
    execfile(os.path.join(diryclean, "def_domask_lines.py"))
    execfile(os.path.join(diryclean, 'secondMaxLocal.py'))

    # Spectral setup
    freqs = config.get('yclean', 'freqs').split()
    chanranges = config.get('yclean', 'chanranges').split()
    nchans = map(get_nchans, chanranges)
    molecules = np.array([fill_molecules(s,j,freqs,chanranges,nchans) \
            for s in range(len(freqs)) \
            for j in range(len(chanranges))])

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
        dirmol = os.path.join(args.basedir, 'yclean', source+'_'+mol)
        os.system('rm -rf '+ dirmol)
        width = moldata[2]
        start = moldata[3]
        molvis = moldata[5]
        nchan = int(moldata[4])
        spwline = moldata[6]
        print "Procesing ", mol
        vis = args.uvdata[0]
        imagename = os.path.join(dirmol, 'auto'+source+'_'+mol+'.12m')
        print vis, imagename

        execfile(os.path.join(diryclean, 'yclean_parallel.py'))
        finalcubes += [imagename+'.tc_final.fits']

    # Join the cubes
    nsub = len(chanranges)
    for i in range(len(freqs)):
        output = os.path.join(args.basedir, 'clean',
                source+'.spw%i.cube' % i)
        j = i*nsub
        join_cubes(finalcubes[j:j+nsub], output, 
                config.get('yclean','joinchans').split)

        
