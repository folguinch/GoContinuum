#!/bin/python3
import argparse
import sys

from astropy.io import fits
from astropy.stats import sigma_clip
import astropy.units as u
from astropy.wcs import WCS
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage.filters import maximum_filter
from scipy.ndimage.morphology import binary_dilation
from scipy.stats import linregress

from go_continuum.argparse_parents import verify_files, paths, source_position

from myutils.argparse_actions import LoadFITS
from myutils.logger import get_logger

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

def _sum_collapse(args: argparse.Namespace) -> None:
    """Call the function."""
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

def _max_collapse(args: argparse.Namespace) -> None:
    """Call the function"""
    return max_collapse()

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

def _prep(cube: 'pathlib.Path', args: argparse.Namespace):
    """Prepare the data."""
    # Get image
    if args.peaks_image is None:
        args.peaks_image, args.cube = args.collapse(args)
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

def extract_spectra(args: List):
    """Extract spectrum/spectra from input files."""
    # Command line options
    args_parents = [parents.logger('debug_extract_spectra.log'),
                    spectrum_parent,
                    paths(plotdir={'help': 'Plot directory'},
                          specdir={'help': 'Spectrum directory'})]
    parser = argparse.ArgumentParser(
        description="Extract spectrum/spectra from cube.",
        add_help=True,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        parents=args_parents,
        conflict_handler='resolve',
    )
    parser.add_argument('--niter', default=1, type=int,
                        help='Number of iterations/peaks')
    parser.add_argument('--rms', actions=actions.ReadQuantity,
                        help='Cube rms')
    parser.add_argument('--collapsed_file', type=str,
                        actions=actions.NormalizePath,
                        help='File name of the collapsed image')
    parser.add_argument('--peaks_image', action=actions.LoadFITS,
                        help='File name of image to look for peaks')
    parser.add_argument('--beam_avg', action='store_true', 
                        help='Compute a beam average spectrum')
    parser.set_defaults(diff=None, cube=None)
    # Subparsers
    subparsers = parser.add_subparsers()
    subparser_cube_parent = [verify_files('cubefiles',
                                          cubefiles={
                                              'help': 'Data cubes file names',
                                              'nargs': '*'})]
    # Max
    pmax = subparsers.add_parser('max', parents=subparser_cube_parent,
                                 help='Use max of all input images')
    pmax.add_argument('--pos_file', actions=actions.NormalizePath,
                      help='Position file')
    pmax.set_defaults(pipe=[_prep, extract_spectra], collapse=_max_collapse)
    # Sum
    psum = subparsers.add_parser('sum', parents=subparser_cube_parent,
                                 help='Use sum of input image')
    psum.set_defaults(pipe=[_prep, extract_spectra], collapse=_sum_collapse)
    # Positions
    ppos = subparsers.add_parser(
        'position',
        parents=subparser_cube_parent + [source_position(required=True)],
        help='Extract the spectra from the given position',
    )
    ppos.set_defaults(pipe=[extract_from_positions])

    args = parser.parse_args(args)
    for cube in args.cubefiles:
        args.log.info('Working on cube: %s', cube)
        for step in args.pipe:
            step(cube, args)

if __name__ == '__main__':
    extract_spectra(sys.argv[1:])
