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

from myutils.argparse_actions import LoadFITS
from myutils.logger import get_logger
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

def sum_collapse(cube: npt.ArrayLike,
                 rms: Optional[float] = None,
                 nsigma: float = 1.,
                 edge: int = 10,
                 log: Callable = print) -> npt.ArrayLike:
    """Collapse cube along the spectral axis.

    If `rms` is given, then all values over `nsigma*rms` are summed.

    Args:
      cube: cube array.
      rms: optional; the cube noise level.
      nsigma: optional; noise level to filter data.
      edge: optional; border channels to ignore.
      log: optional; logging function.
    """
    if rms is not None:
        log(f'Summing all values over: {nsigma * rms}')
        masked = np.ma.masked_less(cube[edge:-edge, :, :], nsigma * rms)
        imgsum = np.ma.sum(masked, axis=0)
    else:
        log('Summing along spectral axis')
        imgsum = np.sum(cube[edge:-edge, :, :], axis=0)

    return imgsum

def max_collapse(cube: npt.ArrayLike,
                 rms: Optional[float] = None,
                 nsigma: float = 1.,
                 edge: int = 10,
                 log: Callable: print) -> npt.ArrayLike:
    """Collapse cube along the spectral axis using `max` function.

    If `rms` is given, then all values below `nsigma*rms` are set to zero.

    Args:
      cubename: cube filename.
      rms: optional; the cube noise level.
      nsigma: optional; noise level to filter data.
      edge: optional; border channels to ignore.
      log: optional; logging function.
    """
    # Load cube
    imgmax = np.max(cube[edge:-edge,:,:], axis=0)

    # Replace values below rms
    if rms is not None:
        log('Replacing values below %f by zero', nsigma * rms)
        imgmax[imgmax < rms] = 0.

    return imgmax

def find_peak(image: Optional[npt.ArrayLike] = None,
              cube: Optional[u.Quantity] = None,
              rms: Optional[u.Quantity] = None,
              collapse_func: Callable = max_collapse,
              diff: Optional[Sequence[npt.ArrayLike]] = None
              log: Callable = print,
              **kwargs) -> Tuple[npt.ArrayLike, int, int]:
    """Find an emission peak.

    If `image` is given, then the position of the maximum is given. Else,
    if `cube` is given, then it is collapsed along the spectral axis using the
    `collapse_func`, and the location of the maximum is returned. Otherwise
    `ValueError` is raised.

    Args:
      image: 2-D image.
      cube: data cube.
      rms: optional; cube noise level.
      collapse_func: optional; collapse function.
      diff: optional; differentials of the image along each axis.
      log: optional; logging function.
      kwargs: additional arguments to `collapse_func`
    """
    # Collapsed image
    if image is not None:
        log('Looking peak of input image')
        collapsed = image
    elif cube is not None:
        log('Looking peak of collapsed cube')
        collapsed = collapse_func(cube.value, rms=rms.to(cube.unit).value,
                                  log=log, **kwargs)

    # Find peak
    if diff is None:
        ymax, xmax = np.unravel_index(np.nanargmax(collapsed), collapsed.shape)
    else:
        # Search for peaks
        xmax = np.diff((diff[1] > 0).view(np.int8), axis=1)
        ymax = np.diff((diff[0] > 0).view(np.int8), axis=0)
        indxy, indxx = np.where(xmax == -1)
        indyy, indyx = np.where(ymax == -1)
        indxx = indxx + 1
        indyy = indyy + 1

        # Select the one with the highest value
        vals = collapsed[indxy, indxx]
        ind = np.argsort(imgsum[indxy, indxx])[::-1]
        indxy = indxy[ind]
        indxx = indxx[ind]
        for p in zip(indxx, indxy):
            if p in zip(indyx, indyy):
                if (rms is not None and
                    collapsed[p[1], p[0]] <= rms.to(cube.unit).value):
                    continue
                xmax, ymax = p
                break
    
    return collapsed, xmax, ymax 

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

def load_data(filenames: Sequence['pathlib.Path']) -> :
    # Get image
    if args.image is None:
        args.image, args.cubes = args.collapse(args.cube, rms=args.rms[0],
                filename=args.image_file, get_cubes=True)
    else:
        pass

    # Changes in values
    args.diff = get_diff(args.image)

def get_spectrum(cube_file: Optional['pathlib.Path'] = None,
                 spec_file: Optional['pathlib.Path'] = None,
                 position: Tuple[int] = None,
                 rms: Optional[u.Quantity] = None,
                 beam_avg: bool = False,
                 beam_fwhm: Optional[u.Quantity] = None,
                 beam_size: Optional[u.Quantity] = None,
                 redo_collapse: bool = False,
                 log: Callable = print) -> Tuple[npt.ArrayLike, Tuple[int]]:
    """Load spectrum.

    At least one `cube_file` or `spec_file` must be specified. The file
    `cube_file` has priority.
    
    Args:
      cube_file: cube file name.
      spec_file: spectrum file.
      position: optional; position where to extract the spectrum from.
      rms: optional; noise level of the cube.
      beam_avg: optional; use a beam average?
      beam_fwhm: optional; beam FWHM of the data.
      beam_size: optional; beam size (sigma) of the data.
      redo_collapse: optional; recalculate collapsed image?
      log: optional; logging function.

    Returns:
      An array with the spectrum.
      A tuple with `(x,y)` coordinates of the spectrum position.
    """
    if cube_file is not None:
        # Check for collapsed image
        collapsed_file = cube_file.with_suffix('.collapsed.fits')
        if collapsed_file.is_file():
            collapsed = fits.open(collapsed_file)[0]
            collapsed = np.squeeze(collapsed.data)
        else:
            collapsed = None

        # Load cube
        cube = fits.open(cube_file)[0]
        header = cube.header
        wcs = WCS(header, naxis=2)

        # Remove dummy axes
        cube = np.squeeze(cube.data) * u.Unit(header['BUNIT'])
        log('Cube shape: %s', cube.shape)

        # Find peak
        if position is not None:
            # User value
            xmax, ymax = position
            log(f'Using input reference position: {xmax} {ymax}')
        else:
            # Peak value
            collapsed, xmax, ymax = find_peak(image=collapsed, cube=cube,
                                              rms=rms)
            log(f'Using peak position: {xmax} {ymax}')

            # Save collapsed image

        # Get spectrum at position
        if beam_avg:
            # Beam size
            log('Averaging over beam')
            pixsize = np.sqrt(wcs.proj_plane_pixel_area())
            if args.beam_fwhm is not None:
                beam_fwhm =gaussian_fwhm_to_sigma * args.beam_fwhm
            else:
                beam_fwhm = np.sqrt(header['BMIN'] * header['BMAJ'])
            if beam_size is not None:
                beam_sigma = beam_size
            else:
                beam_sigma = gaussian_fwhm_to_sigma * beam_fwhm
            beam_sigma = beam_sigma / pixsize.to(beam_sigma.unit)
            args.log.info('Beam size (sigma) = %f pix', beam_sigma)

            # Filter data
            Y, X = np.indices(cube.shape[-2:])
            dist = np.sqrt((X - xmax)**2. + (Y - ymax)**2.)
            mask = dist > beam_sigma
            masked = np.ma.array(cube.value,
                                 mask=np.tile(mask, (cube.shape[0], 1)))
            spectrum = np.ma.sum(masked, axis=(1, 2)) / np.sum(~mask)
        else:
            log('Using single pixel spectrum')
            spectrum = cube[:, ymax, xmax].value
        log(f'Number of channels: {spectrum.size}')

        # Save to file
        if spec_file is None:
            spec_file = cube_file.with_suffix(f'.x{xmax}_y{ymax}.spec.dat')
        with spec_file.open('w') as out:
            lines = ['%f %f' % fnu for fnu in enumerate(args.spectrum)]
            out.write('\n'.join(lines))

    elif spec_file is not None and spec_file.is_file():
        # Load from file
        spectrum = np.loadtxt(spec_file, dtype=float)
        log(f'Spectrum shape: {spectrum.shape}')
        if spectrum.ndim > 1:
            log('Selecting second column')
            spectrum = spectrum[:, 1]
        else:
            spectrum = spectrum

        xmax = ymax = '--'
    else:
        raise ValueError('Cannot find a valid spectrum')

    return spectrum, (xmax, ymax)

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
