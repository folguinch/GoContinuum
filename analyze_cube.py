import os, argparse

from astropy.stats import sigma_clip
import numpy as np
import matplotlib.pyplot as plt

from argparse_actions import LoadFITS
from continuum_iterative import group_chans, chans_to_casa, find_continuum, plot_mask
from logger import get_logger

logger = get_logger(__name__, filename='continuum_iterative.log')

def masked_cube(cube):
    logger.info('Cube shape: %r', cube.shape)
    newcube = np.ma.masked_invalid(np.squeeze(cube.data))
    #logger.info('Invalid values masked: %i/%i', np.ma.count_masked(newcube),
    #        newcube.size)
    return newcube

def plot_results(spec, chans, plotname, continuum=None):
    width = 9.0
    height = 3.5
    fig, ax = plt.subplots(figsize=(width,height))
    ax.set_xlabel('Channel number')
    ax.set_ylabel('Intensity')
    ax.plot(spec, 'k-')
    ax.set_xlim(0, len(spec))
    if continuum is not None:
        ax.axhline(continuum, color='b', linestyle='-')
    plot_mask(ax, chans)
    fig.savefig(plotname, bbox='tight')

def prep(args):
    logger.info('Preparing inputs')
    if args.rms:
        logger.info('Using input rms level: %f', args.rms[0])
        args.level = args.rms[0] * args.nrms[0]
    elif 'RMS' in args.cube.header.keys():
        logger.info('Using fits rms level: %f', args.cube.header['RMS'])
        args.level = args.cube.header['RMS'] * args.nrms[0]
    else:
        raise Exception('Could not define noise level')

    args.cube = masked_cube(args.cube)
    logger.info("Masking cube channel edges")
    args.cube.mask[0:11] = True
    args.cube.mask[-10:] = True

def proc(cube, level, xsrc=None, ysrc=None, radius=None, min_width=2,
        sigma_lower=1.8, sigma_upper=1.8, extremes=10):
    # Max image
    assert len(cube.shape)==3
    maximg = np.ma.max(cube, axis=0)
    maximg = np.ma.masked_less_equal(maximg, level)
    logger.info('Spectra below %f: %i/%i', level, np.ma.count_masked(maximg),
            maximg.size)

    # Central source mask
    if xsrc and ysrc and radius:
        logger.info('Central source position: %i, %i', xsrc, ysrc)
        Y, X = np.indices(maximg.shape)
        d = np.sqrt((X-xsrc)**2 + (Y-ysrc)**2)
        logger.info('Create mask for point outside source')
        logger.info('Source radius: %i pixels', radius)
        mask_src = d > radius
    else:
        mask_src = None
    
    # Iterate over unmasked spectra
    logger.info('Iterating over spectra')
    total = np.zeros(cube.shape[0], dtype=bool)
    if mask_src is not None:
        surrounding = np.zeros(cube.shape[0], dtype=bool)
        central = np.zeros(cube.shape[0], dtype=bool)
    else:
        surrounding = None
        central = None
    for i,j in zip(*np.where(~maximg.mask)):
        # Spectrum
        spec = cube[:,i,j]

        # Find continuum
        filspec, cont, cstd = find_continuum(spec, sigma_lower=sigma_lower, 
                sigma_upper=sigma_upper, edges=10, erode=0, min_width=min_width, 
                min_space=0, log=False)

        # Combine
        if np.all(filspec.mask):
            logger.warn('Problem with pixel: %i, %i', j, i)
        total = np.logical_or(total, filspec.mask)
        if surrounding is not None and mask_src[i,j]:
            surrounding = np.logical_or(surrounding, filspec.mask)
        if central is not None and not mask_src[i,j]:
            central = np.logical_or(central, filspec.mask)

    # Info
    nfil = np.sum(total)
    logger.info('Total number of channels filtered: %i/%i', nfil, total.size)
    if surrounding is not None:
        logger.info('Total number of channels filtered outside source: %i/%i', 
                np.sum(surrounding), surrounding.size)
        logger.info('Total number of channels filtered on source: %i/%i', 
                np.sum(central), central.size)

    return total, surrounding, central

def post(total1, total2=None, total3=None, chanfiles=None, xsrc=None, ysrc=None, 
        plotnames=None, specname=None, cube=None):
    
    # Contiguous channels
    ind = np.arange(total1.size)
    chans1 = group_chans(ind[total1])
    if total2 is not None:
        chans2 = group_chans(ind[total2])
        chans3 = group_chans(ind[total3])
    else:
        chans2 = None
        chans3 = None

    # Plot
    if plotnames:
        if specname:
            logger.info('Plotting over: %s', os.path.basename(specname))
            y = np.loadtxt(os.path.expanduser(specname), usecols=[1])
        elif xsrc and ysrc and cube is not None:
            logger.info('Plotting over spectra at source position')
            y = cube[:, ysrc, xsrc]
        else:
            raise Exception('Nothing to plot')
        cont1 = np.mean(y[~total1])
        logger.info('Continuum level total mask: %f', cont1)
        plot_results(y, chans1, plotnames[0], continuum=cont1)
        if total2 is not None:
            cont2 = np.mean(y[~total2])
            logger.info('Continuum level outside source mask: %f', cont2)
            plot_results(y, chans2, plotnames[1], continuum=cont2)
            cont3 = np.mean(y[~total3])
            logger.info('Continuum level on-source mask: %f', cont3)
            plot_results(y, chans3, plotnames[2], continuum=cont3)

    # Covert to CASA format
    chans1 = chans_to_casa(chans1)
    if total2 is not None:
        chans2 = chans_to_casa(chans2)
    if total3 is not None:
        chans3 = chans_to_casa(chans3)

    # Save files
    if chanfiles:
        for t, f in zip([chans1, chans2, chans3], chanfiles):
            logger.info('Writing: %s', os.path.basename(f))
            with open(os.path.expanduser(f), 'w') as out:
                out.write(t)

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('--plotnames', nargs='*', default=None,
            help='Plot file names')
    parser.add_argument('--specname', default=None,
            help='Reference spectra to plot')
    parser.add_argument('--rms', nargs=1, type=float, default=None,
            help='Image rms')
    parser.add_argument('--nrms', nargs=1, type=float, default=[3],
            help='Number of rms noise level')
    parser.add_argument('--sigma', nargs=2, type=float, default=[1.8,1.8],
            help='Sigma levels for sigma_clip')
    parser.add_argument('--position', nargs=2, type=float, default=[None]*2,
            help='Position of the source')
    parser.add_argument('--radius', nargs=1, type=float, default=[None],
            help='Radius of the source in pixels')
    parser.add_argument('--min_width', nargs=1, type=int, default=[2],
            help='Minimum mask band width')
    parser.add_argument('cube', action=LoadFITS, default=None,
            help='Data cube file name')
    parser.add_argument('filenames', default=None, nargs='*',
            help='File names to save the results')
    parser.set_defaults(prep=prep, main=proc, post=post, level=None)
    args = parser.parse_args()
    args.prep(args)
    totals = args.main(args.cube, args.level, xsrc=args.position[0],
            ysrc=args.position[1], radius=args.radius[0],
            sigma_lower=args.sigma[0], sigma_upper=args.sigma[1],
            min_width=args.min_width[0])
    args.post(totals[0], total2=totals[1], total3=totals[2], chanfiles=args.filenames,
            xsrc=args.position[0], ysrc=args.position[1],
            plotnames=args.plotnames, specname=args.specname, cube=args.cube)
if __name__=='__main__':
    main()
