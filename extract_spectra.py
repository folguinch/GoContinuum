#!/bin/python
import argparse
import os
import sys

from astropy.io import fits
from astropy.stats import sigma_clip
from astropy.wcs import WCS
from scipy.ndimage.filters import maximum_filter
from scipy.ndimage.morphology import binary_dilation
from scipy.stats import linregress
import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np

from argparse_actions import LoadFITS
from logger import get_logger

# Optional
try:
    from astroSource.source import LoadSourcefromConfig
    from myutils.spectralcube_utils import freq_axis
    from myutils.array_utils import save_struct_array
except ImportError:
    LoadSourcefromConfig = None

# Start settings
if os.path.isdir('logs'):
    logger = get_logger(__name__, file_name='logs/extract_spectra.log')
else:
    logger = get_logger(__name__, file_name='extract_spectra.log')

def new_fits(data, hdr=None, filename=None):
    hdu = fits.PrimaryHDU(data, header=hdr)
    hdul = fits.HDUList([hdu])
    if filename:
        hdul.writeto(filename, overwrite=True)

    return hdul[0]

def sum_collapse(cube, rms=None, filename=None):
    return _sum_collapse(cube, rms=rms, filename=filename)[0]

def _sum_collapse(cube, rms=None, filename=None, get_cubes=False):
    if rms is not None:
        logger.info('Summing all values over: %f', rms)
        masked = np.ma.masked_less(cube.data[0,10:-10,:,:], rms)
        imgsum = np.sum(masked, axis=0).data/cube.data.shape[1]
    else:
        logger.info('Summing along spectral axis')
        imgsum = func(cube.data[0,10:-10,:,:], axis=0)/cube.data.shape[1]

    # Header
    wcs = WCS(cube.header).sub(['longitude', 'latitude'])
    header = wcs.to_header()
    
    if get_cubes:
        return (new_fits(imgsum, hdr=header, filename=filename), [cube])
    else:
        return (new_fits(imgsum, hdr=header, filename=filename),)

def max_collapse(cubelist, rms=None, filename=None):
    return _max_collapse(cubelist, rms=rms, filename=filename, get_cubes=False)[0]

def _max_collapse(cubelist, rms=None, filename=None, get_cubes=True):
    # Find max map
    cummax = None
    cubes = []
    for cfile in cubelist:
        # Load cube
        logger.info('Finding max image for: %s', os.path.basename(cfile))
        cube = fits.open(os.path.expanduser(cfile))[0]
        if cube.data.ndim == 3:
            cube.data = np.expand_dims(cube.data, axis=0)
        if get_cubes:
            cubes += [cube]

        # Find max image
        aux = np.max(cube.data[0,10:-10,:,:], axis=0)

        # Update cumulative max
        if cummax is None:
            cummax = aux
        else:
            cummax = np.max(np.array([cummax, aux]), axis=0)
            assert cummax.shape == aux.shape

    # Replace values below rms
    if rms is not None:
        logger.info('Replacing values below %f by zero', rms)
        cummax[cummax<rms] = 0.
    else:
        pass

    # Header
    wcs = WCS(cube.header).sub(['longitude', 'latitude'])
    header = wcs.to_header()

    if get_cubes:
        return (new_fits(cummax, hdr=header, filename=filename), cubes)
    else:
        return (new_fits(cummax, hdr=header, filename=filename),)

def find_peak(cube=None, image=None, filename=None, rms=None, diff=None,
        func=sum_collapse):
    # Find peak
    if image is not None:
        logger.info('Looking for peak in input image')
        imgsum = image.data
    elif cube is not None:
        logger.info('Looking for peak in input cube')
        imgsum = func(cube, rms=rms, filename=filename)
        imgsum = imgsum.data

    if diff is None:
        ymax, xmax = np.unravel_index(np.nanargmax(imgsum), imgsum.shape)
    else:
        # Search for peaks
        xmax = np.diff((diff[1] > 0).view(np.int8), axis=1)
        ymax = np.diff((diff[0] > 0).view(np.int8), axis=0)
        indxy, indxx = np.where(xmax == -1)
        indyy, indyx = np.where(ymax == -1)
        indxx = indxx + 1
        indyy = indyy + 1

        # Select the one with the highest value
        vals = imgsum[indxy, indxx]
        ind = np.argsort(imgsum[indxy, indxx])[::-1]
        indxy = indxy[ind]
        indxx = indxx[ind]
        for p in zip(indxx, indxy):
            if p in zip(indyx, indyy):
                if rms and imgsum[p[1],p[0]]<=rms:
                    continue
                xmax, ymax = p
                break
    
    logger.info('Peak position: %i, %i', xmax, ymax) 

    return xmax, ymax 

def mask_image(img, x, y, r):
    Y, X = np.indices(img.data.shape)
    pixsize = np.abs(img.header['CDELT1'])*3600.
    dist = np.sqrt((x-X)**2 + (y-Y)**2)*pixsize

    img.data[dist<=r] = 0. #np.nan

    return img

def get_diff(img):
    newd = img.data*1.
    newd[np.isnan(img.data)] = 0.
    diffs = [np.diff(newd, axis=i) for i in range(2)]
    return diffs

def empty(args):
    pass

def prep(args):
    # Get image
    if args.image is None:
        args.image, args.cubes = args.collapse(args.cube, rms=args.rms[0],
                filename=args.image_file, get_cubes=True)
    else:
        pass

    # Changes in values
    args.diff = get_diff(args.image)

def extract_spectra(args):
    for i in range(args.niter):
        logger.info('Iteration number: %i', i+1)
        if i==0:
            xmax, ymax = find_peak(image=args.image)
        else:
            xmax, ymax = find_peak(image=args.image, diff=args.diff)

        for j, cube in enumerate(args.cubes):
            # Obtain spectrum
            spec = cube.data[0,:,ymax,xmax]
            
            # Save spectrum
            if len(args.cubes)>1:
                specfile = args.specname[0] % j + '.p%ispec.dat' % i
            else:
                specfile = args.specname[0] + '.p%ispec.dat' % i
            with open(os.path.expanduser(specfile), 'w') as out:
                out.write('\n'.join(['%f %f' % fnu for fnu in \
                        enumerate(spec)]))

        # Write positions
        if args.pos_file[0]:
            with open(os.path.expanduser(args.pos_file[0]), 'a') as out:
                out.write('%i %i\n' % (xmax, ymax))
        
        # Mask image
        if args.niter>1:
            args.image = mask_image(args.image, xmax, ymax, args.radius[0])

def extract_from_positions(args):
    for i,(x,y) in enumerate(zip(args.locations[::2], args.locations[1::2])):
        # Obtain spectrum
        logger.info('Extracting spectra at: %i,%i', x, y)
        spec = args.cube.data[0,:,y,x]

        # Save spectrum
        specfile = args.specname[0] + '.p%ispec.dat' % i
        logger.info('Writing spectrum file: %s', os.path.basename(specfile))
        with open(os.path.expanduser(specfile), 'w') as out:
            out.write('\n'.join(['%f %f' % fnu for fnu in \
                    enumerate(spec)]))

def extract_source_spec(args):
    # Iterate over data
    for key in args.src.data.keys():
        # Spectrum
        if key not in args.keys and args.keys[0]!='all':
            continue
        data = args.src[key]
        if args.beam_avg:
            spec = data.get_avg_spectrum(args.src.position)*data.data.unit
        else:
            spec = data.get_spectrum(coord=args.src.position)

        # Spectral axis
        chans = np.squeeze(np.indices(spec.shape))
        freq = freq_axis(data.data)
        comb = np.array(zip(chans,freq.value,spec.value),
                dtype=[('chan',chans.dtype),
                    ('freq',freq.value.dtype),
                    ('flux',spec.value.dtype)])
        units = {'chan':u.Unit(''), 'freq':freq.unit, 'flux':spec.unit}

        # File name
        dir_name = os.path.dirname(data.address)
        if args.beam_avg:
            file_name = '%s.%s.spec.beam_avg.dat' % (args.src.name, key)
        else:
            file_name = '%s.%s.spec.dat' % (args.src.name, key)
        file_name = os.path.join(dir_name, file_name)
        logger.info('Saving spectrum to: %s', file_name)

        # Save spectrum
        save_struct_array(file_name, comb, units, fmt='%10i\t%10.4f\t%10.4e')

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    parser.add_argument('--niter', default=2, type=int,
            help='Number of iterations/peaks')
    parser.add_argument('--plotname', default=None,
            help='Plot file name base (without extension)')
    parser.add_argument('--rms', nargs=1, type=float, default=[None],
            help='Image rms')
    parser.add_argument('--image_file', type=str, 
            help='file name for the collapsed image')
    parser.add_argument('--image', action=LoadFITS, default=None,
            help='File name of image to look for peaks')
    parser.add_argument('--beam_avg', action='store_true', 
            help='Compute a beam average spectrum')
    group1 = parser.add_mutually_exclusive_group(required=False)
    group1.add_argument('--beam_size', nargs=1, type=float,
            help='Beam size (sigma) in arcsec')
    group1.add_argument('--beam_fwhm', nargs=1, type=float,
            help='Beam FWHM in arcsec')
    group1.add_argument('--radius', nargs=1, type=float,
            help='Mask radius in arcsec')
    parser.set_defaults(diff=None, cubes=None)
    # Subparsers
    # Max
    pmax = subparsers.add_parser('max', 
            help="Use max of all input images")
    pmax.add_argument('--pos_file', nargs=1, type=str, default=[None],
            help='Position file')
    pmax.add_argument('specname', default=None, nargs=1,
            help='Spectrum file name base (without extension). ' + \
                    'If more than one cube include a \%i for the spectra of ' + \
                    'each cube.')
    pmax.add_argument('cube', nargs='*', default=None,
            help='Data cubes file names')
    pmax.set_defaults(main=extract_spectra, prep=prep, collapse=_max_collapse)
    # Sum
    psum = subparsers.add_parser('sum', 
            help="Use sum of input image")
    psum.add_argument('specname', default=None, nargs=1,
            help='Spectrum file name base (without extension)')
    psum.add_argument('cube', action=LoadFITS, default=None,
            help='Data cube file name')
    psum.set_defaults(main=extract_spectra, prep=prep, collapse=_sum_collapse)
    # Positions
    ppos = subparsers.add_parser('position',
            help = 'Extract the spectra from the given positions')
    ppos.add_argument('cube', action=LoadFITS, default=None,
            help='Data cube file name')
    ppos.add_argument('specname', default=None, nargs=1,
            help='Spectrum file name base (without extension)')
    ppos.add_argument('locations',  nargs='*', type=int,
            help='List of positions')
    ppos.set_defaults(prep=empty, main=extract_from_positions)
    # Source
    if LoadSourcefromConfig is not None:
        psrc = subparsers.add_parser('source',
                help='Extract spectra at source position')
        psrc.add_argument('--keys', nargs=1, type=str, default=['all'],
                help='Data keys to load')
        psrc.add_argument('src', metavar='SOURCE',
                action=LoadSourcefromConfig,
                help='Source configuration file')
        psrc.set_defaults(prep=empty, main=extract_source_spec)
    args = parser.parse_args()
    args.prep(args)
    args.main(args)

if __name__=='__main__':
    main()
