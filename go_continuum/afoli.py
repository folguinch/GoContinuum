"""Functions to run and implement AFOLI.

AFOLI finds line-free channels from a given spectrum. To find these channels it
uses sigma clip to mask channels with lines. As default, the sigma clip is
assymetric in order to favor the identification of emission lines. This is,
however, customizable from the `afoli` function input.

For `GoContinuum`, where a configuration file is needed, the function
`afoli_iter_data` can use the configuration file to specify the parameters of
the `afoli` function. It also performs the following tasks (some optional
depending on the function input):

    1. Find the coordinate of where the spectra will be subtracted.
    2. Extract the spectrum for each SPW.
    3. Run AFOLI on the spectrum.
    4. Converts and saves the masked spectrum to frequency range flags.
    5. Join all the flags into one file.

The different parameters used for the masking in AFOLI allow more flexibility
in the line-free channel selection. The general procedure of AFOLI is:

    1. Generates a masked spectrum with a mask containing: the edges of the
    spectrum (`extremes` parameter), requested flagged channels (`flagchans`),
    and invalid values (`invalid_values`).
    2. Runs sigma-clip un the spectrum to filter out line emission/absorption
    (`sigma`, `censtat` and `niter` parameters).
    3. It dilates the mask by requested amount (`dilate`).
    4. Removes masked section below a minimum width (`min_width`).
    5. Masks small gaps between masked sections (`min_gap`).
    6. Saves statistics to a table if requested.
    7. Retrieve the masking levels by changing the number of iterations for
    sigma-clipping
    8. Finds and saves the masked channel ranges in CASA format.
    9. Plots the spectrum and step statistics.
    10. If requested, it writes channel range files for different levels
    factors of the real continuum from sigma-clip.
"""
from typing import (List, Optional, Sequence, Callable, Tuple, Union, TextIO,
                    Any, Dict)

from astropy.coordinates import SkyCoord
from astropy.stats import sigma_clip
from goco_helpers.image_tools import get_common_position, get_spectrum
from goco_helpers.utils import get_func_params
from scipy.interpolate import interp1d
from scipy.optimize import bisect
from scipy.stats import linregress
import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import scipy.ndimage as ndi

from .common_types import SectionProxy
#from .utils import iter_data

def group_chans(array: npt.ArrayLike) -> List[slice]:
    """Group contiguous channels from masked array."""
    return np.ma.clump_masked(array)

def chans_to_casa(chan_slices: Sequence[slice], sep: str = ';') -> str:
    """Create a string with in CASA format with the channel ranges."""
    ranges = []
    for slc in chan_slices:
        start = slc.start
        stop = slc.stop - 1
        if start == stop:
            ranges.append(f'{start}')
        else:
            ranges.append(f'{start}~{stop}')
    return sep.join(ranges)

def freqs_to_casa(freq_ranges: List[Tuple], sep: str = '\n') -> str:
    """Create a string with frequency ranges."""
    return sep.join(f'{freq1.value:.10f}~{freq2.value:.10f}{freq2.unit}'
                    for freq1, freq2 in freq_ranges)

def write_casa_chans(chan_slices: Sequence[slice],
                     filename: 'pathlib.Path') -> None:
    """Write masked channel slices to file in CASA format."""
    filename.write_text(chans_to_casa(chan_slices))

def write_casa_freqs(freq_ranges: List[Tuple],
                     filename: 'pathlib.Path') -> None:
    """Write flagged frequency ranges to CASA format."""
    filename.write_text(freqs_to_casa(freq_ranges))

def flags_from_file(filename: 'pathlib.Path',
                    flag_type: str = 'freq') -> List[Tuple]:
    """Load flags from file."""
    lines = filename.read_text()
    flags = []
    for line in lines.split('\n'):
        initial, final = line.split('~')
        final = u.Quantity(final)
        initial = float(initial) * final.unit
        flags.append((initial, final))

    return flags

def get_freq_flags(freq: npt.ArrayLike, spectrum: npt.ArrayLike) -> List[Tuple]:
    """Convert spectrum mask indices to frequency range."""
    # Masked channel slices
    slices = group_chans(spectrum)

    # Convert to range
    # Add/subtract a delta (half the channel width) to account for rounding
    # errors when converting to mask
    ranges = []
    delta = np.abs(freq[0] - freq[1]) / 2
    for slc in slices:
        freq_ran = np.array([freq[slc.start].value,
                             freq[slc.stop - 1].value]) * freq.unit
        freq1 = np.min(freq_ran) - delta
        freq2 = np.max(freq_ran) + delta
        ranges.append((freq1, freq2))

    return ranges

def filter_min_width(mask: npt.ArrayLike, min_width: int) -> npt.ArrayLike:
    """Delete `mask` bands with a width less or equal than `min_width`."""
    if np.all(mask):
        return mask
    labels, *_ = ndi.label(mask)
    component_sizes = np.bincount(labels.ravel())
    small_mask = component_sizes <= min_width
    small_mask = small_mask[labels]
    mask[small_mask] = False

    return mask

def linreg_stat(x: Union['astropy.fits.PrimaryHDU', npt.ArrayLike]) -> float:
    """Statistic function for `sigmaclip` based on linear regression."""
    # Data arrays
    try:
        xnew = np.arange(x.data.size, dtype=float)[~x.mask]
        ynew = x.data[~x.mask]

        # At the center of the spw
        xnew = xnew - x.data.size/2

    except AttributeError:
        xnew = np.arange(x.size)
        ynew = x

        # At the center of the spw
        xnew = xnew - x.size/2

    # Regression
    #slope, intercept, r_value, p_value, std_err = linregress(xnew, ynew)
    intercept = linregress(xnew, ynew)[1]

    return intercept

def basic_masking(spectrum: npt.ArrayLike,
                  edges: int = 10,
                  flagchans: Optional[str] = None,
                  invalid_values: Optional[Sequence[float]] = None,
                  separator: str = ',',
                  log: Callable = print) -> npt.ArrayLike:
    """Apply a basic mask to the spectrum.

    Args:
      spectrum: Input spectrum.
      edges: Optional. Number of channels to mask in the borders.
      flagchans: Optional. Additional channels to flag in CASA format.
      invalid_values: Optional. Flag values that are not allowed.
      separator: Optional. Value separator.
      log: Optional. Logging function.
    """
    # Mask invalid
    spec = np.ma.masked_invalid(spectrum)

    # Basic check
    if edges >= spec.size:
        raise ValueError(f'Masking the entire spectrum: {edges}')

    # Filter edges
    if edges > 0:
        log(f'Masking {edges} channels at extremes')
        spec.mask[:edges] = True
        spec.mask[-edges:] = True

    # Flag channels
    if flagchans is not None:
        for flags in flagchans.split(separator):
            log(f'Masking channel range: {flags}')
            ch1, ch2 = map(lambda x: int(x.strip()), flags.split('~'))
            spec.mask[ch1:ch2+1] = True

    # Flag values
    if invalid_values is not None:
        for val in invalid_values:
            log(f'Masking invalid value: {val}')
            spec = np.ma.mask_where(spec == val, spec)

    return spec

def find_continuum(spectrum: npt.ArrayLike,
                   edges: int = 10,
                   dilate: int = 0,
                   min_width: int = 2,
                   min_gap: int = 0,
                   flagchans: Optional[str] = None,
                   invalid_values: Optional[Sequence[float]] = None,
                   table: Optional[TextIO] = None,
                   log: Callable = print,
                   **sigmaclip_pars) -> Tuple[Any]:
    """Calculate a line free spectrum.

    Args:
      spec: Input spectrum.
      edges: Optional. Number of channels to mask in the borders.
      dilate: Optional. Number of iterations of mask erosion.
      min_width: Optional. Minimum number of channels for a line.
      min_gap: Optional. Minimum space between masked bands.
      flagchans: Optional. Additional channels to flag in CASA format.
      invalid_values: Optional. Flag values that are not allowed.
      table: Optional. Table file to save results.
      log: Optional. Logging function.
      sigmaclip_pars: Optional. Parameters for `sigma_clip` function.

    Returns:
      A masked array of the spectrum.
      The continuum value.
      The standard deviation of the continuum value.
    """
    # Apply basic initial masking
    spec = basic_masking(spectrum, edges=edges, flagchans=flagchans,
                         invalid_values=invalid_values, log=log)

    # Filter data
    specfil = sigma_clip(spec, **sigmaclip_pars)
    nfil = np.ma.count_masked(specfil)
    ntot = specfil.data.size
    log(f'Initial number of masked channels = {nfil}/{ntot}')

    # Dilate mask
    if dilate >= specfil.data.size/2:
        raise ValueError('Dilating lines over all spectrum')
    if dilate > 0:
        log(f'Dilating the mask {dilate} times')
        specfil.mask = ndi.binary_dilation(specfil.mask, iterations=dilate)
        nfil = np.ma.count_masked(specfil)
        log(f'Number of masked channels after eroding = {nfil}/{ntot}')

    # Filter small bands
    if min_width > 0:
        log('Removing small masked bands')
        log(f'Minimum masked band width: {min_width}')
        specfil.mask = filter_min_width(specfil.mask, min_width)
        nfil = np.ma.count_masked(specfil)
        log(('Number of masked channels after unmasking small bands = '
             f'{nfil}/{ntot}'))

    # Filter consecutive
    if min_gap is not None and min_gap > 1:
        log('Masking small gaps between masked bands')
        ind = np.arange(specfil.mask.size)
        small_bands = np.where(np.diff(ind[specfil.mask]) > min_gap+1)[0] + 1
        groups = np.split(ind[specfil.mask], small_bands)
        for group in groups:
            if len(group) > 1:
                specfil.mask[group[0]:group[-1]] = True
        nfil = np.ma.count_masked(specfil)
        log(('Number of masked channels after masking consecutive = '
             f'{nfil}/{ntot}'))

    # Continuum
    cont = np.ma.mean(specfil)
    cstd = np.ma.std(specfil)
    nfil = np.ma.count_masked(specfil)
    log(f'Final number of masked channels = {nfil}/{ntot}')
    log(f'Continuum level = {cont} +/- {cstd}')

    # Write table
    if table is not None:
        table.write(f'{cont:10f}\t{cstd:10f}\t{nfil:10i}\n')

    return specfil, cont, cstd

def get_sigma_clip_steps(spec: npt.ArrayLike,
                         **sigmaclip_pars) -> Tuple[List]:
    """Calculate sigma-clip steps one-by-one.

    Args:
      spec: Initial spectrum.
      sigmaclip_pars: Parameters for `sigma_clip`.
    """
    # Initial values
    means = [np.ma.mean(spec)]
    medians = [np.ma.median(spec)]
    stds = [np.ma.std(spec)]
    npoints = [np.sum(~spec.mask)]

    # Increase number of iterations
    i = 1
    while True:
        sigmaclip_pars['maxiters'] = i
        filtered = sigma_clip(spec, **sigmaclip_pars)
        npoint = np.sum(~filtered.mask)
        if len(npoints) == 0 or npoints[-1] != npoint:
            npoints.append(npoint)
            means.append(np.ma.mean(filtered))
            medians.append(np.ma.median(spec[~filtered.mask]))
            stds.append(np.ma.std(filtered))
        else:
            break
        i += 1

    return (np.array(npoints), np.array(medians), np.array(means),
            np.array(stds))

def reverse_levels(spectrum: npt.ArrayLike,
                   levels: List[float],
                   means: List[float],
                   stds: List[float],
                   continuum: float,
                   sigma_lower: float,
                   sigma_upper: float,
                   level_mode: Union[int, str] = 'nearest',
                   edges: int = 10,
                   flagchans: Optional[str] = None,
                   invalid_values: Optional[Sequence[float]] = None,
                   plot_file: Optional['pathlib.Path'] = None,
                   chan_file: Optional['pathlib.Path'] = None,
                   log: Callable = print) -> None:
    """Determine the continuum value for different levels of contamination.

    It determines at which iteration the cleanest continuum has contamination
    equivalent to each level in levels, i.e. at which iteration 
    `continuum == real_continuum + real_continuum*level`.
    It then generates a masked spectrum with the new continuum level.
    Note that this is only an approximation as `sigma_clip` is performed in
    discrete steps, and in the case of AFOLI the filtering is asymmetric.

    Args:
      spectrum: The observed spectrum.
      levels: Levels of contamination to calculate.
      means: Continuum value for each iteration of `sigma_clip`.
      stds: Standard deviation of values at each `sigma_clip` iteration.
      continuum: Real continuum level.
      sigma_lower: Lower sigma level used in AFOLI.
      sigma_upper: Upper sigma level used in AFOLI.
      level_mode: Optional. Kind of interpolation.
      edges: Optional. Channels to ignore at the edges.
      flagchans: Optional. Additional channels to flag.
      invalid_values: Optional. Flag values that are not allowed.
      plot_file: Optional. Plotting file.
      chan_file: Optional. Channel file to store results in CASA format.
      log: Optional. Logging function.
    """
    for level in levels:
        log('-' * 80)
        log(f'Processing level: {level}')

        # Mask the spectrum
        spec = basic_masking(spectrum, edges=edges, flagchans=flagchans,
                             invalid_values=invalid_values, log=log)

        # Find ranges
        means_norm = means / continuum
        if np.min(means_norm) < (1. + level) < np.max(means_norm):
            # Interpolation functions
            niter = np.arange(means.size)
            means_norm_cent = means_norm - (1. + level)
            try:
                kind = int(level_mode)
            except ValueError:
                kind = level_mode
            fn1 = interp1d(niter, means_norm_cent, kind=kind,
                           bounds_error=False,
                           fill_value=(means_norm_cent[0], means_norm_cent[-1]))
            fn2 = interp1d(niter, stds, kind=kind, bounds_error=False,
                           fill_value=(stds[0], stds[-1]))

            # Find root
            niter0 = bisect(fn1, niter[0], niter[-1])
            lev_cont = (fn1(niter0) + (1. + level)) * continuum
            lev_std = fn2(niter0)
        else:
            # Step closer to the level
            log('Value outside range!')
            log('Using nearest value instead')
            ind = np.nanargmin(np.abs((1. + level) - means_norm))
            lev_cont = means[ind]
            lev_std = stds[ind]
        log(f'Value at {1+level}:')
        log(f'Continuum = {lev_cont}')
        log(f'Std dev = {lev_std}')
        spec.mask[spec < lev_cont - sigma_lower*lev_std] = True
        spec.mask[spec > lev_cont + sigma_upper*lev_std] = True
        chans = group_chans(spec)

        # Plot
        if plot_file is not None:
            # Plot
            filename = plot_file.with_suffix(f'.{level}{plot_file.suffix}')
            title = (f'Continuum = {lev_cont}; '
                     f'continuum channels = {np.sum(~spec.mask)}/{spec.size}')
            plot_spectrum(spec.data, filename=filename, continuum=lev_cont,
                          mask=chans, title=title)

        # Save file
        if chan_file is not None:
            filename = chan_file.with_suffix(f'.{level}{chan_file.suffix}')
            write_casa_chans(chans, filename)
        else:
            chans = chans_to_casa(chans)
            log(f'Flagged channels: {chans}')

def afoli(spectrum: npt.ArrayLike,
          sigma: Sequence[float] = (3.0, 1.3),
          chan_file: Optional['pathlib.Path'] = None,
          censtat: str = 'median',
          niter: Optional[int] = None,
          extremes: int = 10,
          min_width: int = 2,
          min_gap: Optional[int] = None,
          dilate: int = 0,
          flagchans: Optional[str] = None,
          invalid_values: Optional[Sequence[float]] = None,
          table: Optional[TextIO] = None,
          levels: Optional[Sequence[float]] = None,
          level_mode: str = 'nearest',
          plot_file: Optional['pathlib.Path'] = None,
          log: Callable = print) -> npt.ArrayLike:
    """Run asymmetric sigma-clipping for lines (AFOLI).

    The default value of `sigma` has been optimized for spectra dominated by
    line emission.

    Args:
      spectrum: Spectrum to mask.
      sigma: Optional. Sigma lower and upper limits for `sigma_clip`.
      chan_file: Optional. File where to write the selected channels in CASA
        format.
      censtat: Optional. Statistical function name.
      niter: Optional. Number of iterations of the `sigma_clip` function.
      extremes: Optional. Number of channels to mask in the borders.
      min_width: Optional. Minimum number of channels for a line.
      min_gap: Optional. Minimum space between masked bands.
      dilate: Optional. Number of channels to dilate on each side of a line.
      flagchans: Optional. Additional channels to flag in CASA format.
      invalid_values: Optional. Flag values that are not allowed.
      table: Optional. Table file to save results.
      levels: Optional. Compute masks at different levels from the continuum.
      level_mode: Optional. How to determine the iteration number for each
        level.
      plot_file: Optional. Plot results and save figure.
      log: Optional. Logging function.

    Returns:
      An array with the masked channels.
    """
    log('Using: sigma_clip')
    log(f'Sigma clip iters = {niter}')

    # Preporcess sigmaclip options
    sigmaclip_pars = {}
    if  censtat == 'median':
        sigmaclip_pars['cenfunc'] = np.ma.median
    elif censtat == 'linregress':
        sigmaclip_pars['cenfunc'] = linreg_stat
    elif censtat == 'mean':
        sigmaclip_pars['cenfunc'] = np.ma.mean
    else:
        raise NotImplementedError(f'Censtat {censtat} not implemented')
    if len(sigma)==1:
        sigmaclip_pars['sigma'] = sigma[0]
    elif len(sigma)==2:
        sigmaclip_pars['sigma_lower'] = sigma[0]
        sigmaclip_pars['sigma_upper'] = sigma[1]
    else:
        raise ValueError

    # Find continuum
    sigmaclip_pars['maxiters'] = niter
    basic_mask_pars = {'edges': extremes,
                       'flagchans': flagchans,
                       'invalid_values': invalid_values}
    filtered, cont, cstd = find_continuum(spectrum,
                                          dilate=dilate,
                                          min_width=min_width,
                                          min_gap=min_gap,
                                          table=table,
                                          log=log,
                                          **basic_mask_pars,
                                          **sigmaclip_pars)
    nfil = np.ma.count_masked(filtered)
    ntot = filtered.data.size

    # Get sigma_clip steps
    scpoints, scmedians, scmeans, scstds = get_sigma_clip_steps(
        basic_masking(spectrum, log=log, **basic_mask_pars),
        **sigmaclip_pars,
    )

    # Contiguous masked channels
    chan_slices = group_chans(filtered)

    # Save channel file
    if chan_file is not None:
        write_casa_chans(chan_slices, chan_file)

    # Plot
    if plot_file is not None:
        # Plot difference in steps
        scpoint_fractions = 100. * scpoints / ntot

        # Figure and axes
        fig, (ax1, ax1b, ax2) = get_plot(
            xlabel=f'% of channels (continuum = {ntot-nfil})',
            ylabel_left='Mean / Continuum',
            ylabel_right='Standard deviation',
        )

        # Iterations
        ax1.plot(100 * (ntot - nfil) / ntot, cont / cont, 'bo')
        ax1.plot(scpoint_fractions, scmeans/cont, 'b+', markersize=20)
        ax1b.plot(100 * (ntot - nfil) / ntot, np.ma.std(filtered), 'ro')
        ax1b.plot(scpoint_fractions, scstds, 'r+', markersize=20)
        for xl, xu, yl, yu in zip(scpoint_fractions[:-1],
                                  scpoint_fractions[1:],
                                  scmeans[:-1],
                                  scmeans[1:]):
            percent = 100 * np.abs(yl - yu) / np.max([yl , yu])
            ax1.annotate(f'{percent:.1f}', (0.5*(xl+xu), 0.5*(yl+yu)/cont),
                         xytext=(0.5*(xl+xu), 0.5*(yl+yu)/cont),
                         xycoords='data', horizontalalignment='center',
                         color='k')

        # Others
        ax1.annotate(f'Continuum intensity = {cont}', xy=(0.1, 0.9),
                     xytext=(0.1, 0.9), xycoords='axes fraction')

        # Spectrum
        plot_spectrum(filtered.data, fig=fig, ax=ax2, continuum=cont,
                      mask=chan_slices, filename=plot_file)

    if levels is not None:
        log('-' * 80)
        log('[OPTIONAL] Obtaining masked channels at each level')
        sigma_lower = sigmaclip_pars.get('sigma_lower',
                                         sigmaclip_pars.get('sigma'))
        sigma_upper = sigmaclip_pars.get('sigma_upper',
                                         sigmaclip_pars.get('sigma'))
        reverse_levels(spectrum, levels, scmeans, scstds, cont,
                       sigma_lower=sigma_lower, sigma_upper=sigma_upper,
                       level_mode=level_mode, chan_file=chan_file,
                       plot_file=plot_file, log=log, **basic_mask_pars)
        log('-'*80)

    return filtered

def get_plot(xlabel: str = 'Iteration number',
             ylabel_left: str = 'Average intensity',
             ylabel_right: str = 'Masked channels',
             naxes: int = 2
             ) -> Tuple['matplot.Figure', Tuple['matplotlib.Axes']]:
    """Initialize the stats and spectrum plot.

    Args:
      xlabel: Optional. Stats x-axis label.
      ylabel_left: Optional. Stats left y-axis label.
      ylabel_right: Optional. Stats right y-axis label.
      naxes: Optional. Number of axes to create.

    Returns:
      A figure and its axes.
    """
    # Initialize figure and axes
    plt.close()
    figsize = 17.2, 3.5
    if naxes == 2:
        width_ratios = [1/5, 4/5]
        fig, axs = plt.subplots(nrows=1, ncols=naxes, figsize=figsize,
                                width_ratios=width_ratios)

        # Stats left axis
        axs[0].set_xlabel(xlabel)
        axs[0].set_ylabel(ylabel_left)
        axs[0].tick_params('y', colors='b')

        # Stats right axis
        ax0b = axs[0].twinx()
        ax0b.set_ylabel(ylabel_right)
        ax0b.tick_params('y', colors='r')
        axs = (axs[0], ax0b, axs[-1])
    elif naxes == 1:
        fig, *axs = plt.subplots(1, naxes, figsize=figsize)
    else:
        raise NotImplementedError('Only 1 or 2 naxes accepted')
    #ax1 = fig.add_axes([0.8/width, 0.4/height, 5/width, 3/height])
    #ax2 = fig.add_axes([7/width, 0.4/height, 10/width, 3/height])

    # Plot spectrum
    axs[-1].set_xlabel('Channel number')
    axs[-1].set_ylabel('Intensity')

    return fig, axs

def plot_spectrum(spectrum: npt.ArrayLike,
                  fig: Optional['matplotlib.Figure'] = None,
                  ax: Optional['matplotlib.Axes'] = None,
                  filename: Optional['pathlib.Path'] = None,
                  continuum: Optional[float] = None,
                  mask: Optional[Sequence[slice]] = None,
                  title: Optional[str] = None) -> None:
    """Plot a spectrum.

    Args:
      spectrum: Spectrum data.
      fig: Optional. A `matplotlib` figure object.
      ax: Optional. A `matplotlib` axes object.
      filename: Optional. Figure file name.
      continuum: Optional. Plot horizontal line with the continuum level.
      mask: Optional. Plot masked regions.
      title: Optional. Plot title.
    """
    if ax is None:
        fig, axs = get_plot(naxes=1)
        ax = axs[-1]

    # Plot spectrum
    ax.plot(spectrum, 'k-', ds='steps-mid')
    ax.set_xlim(0, spectrum.size - 1)

    # Overplots
    if continuum is not None:
        ax.axhline(continuum, color='b', linestyle='-')
    if mask is not None:
        plot_mask(ax, mask)

    # Others
    if title is not None:
        ax.set_title(title)

    # Save
    if filename is not None and fig is not None:
        fig.savefig(filename, bbox_inches='tight')

def plot_mask(ax: 'matplotlib.Axes',
              chans: List[slice],
              color: str = 'r') -> None:
    """Plot masked region.
    
    Args:
      ax: Plot axis.
      chans: List of channel slices.
      color: Optional. Color of the mask band.
    """
    for slc in chans:
        ax.axvspan(slc.start, slc.stop - 1, fc=color, alpha=0.5, ls='-')

def get_afoli_pars(config: SectionProxy,
                   required_keys: Sequence[str] = (),
                   ignore_keys: Sequence[str] = ('spectrum', 'chan_file',
                                                 'plot_file', 'table', 'log'),
                   int_keys: Sequence[str] = ('extremes', 'niter', 'min_width',
                                              'min_gap', 'dilate'),
                   float_list_keys: Sequence[str] = ('sigma', 'levels',
                                                     'invalid_values'),
                   **cfgvars: Dict) -> Dict[str, Any]:
    """Get AFOLI parameters from configuration parser.

    Uses config values with `cfgvars` taking precedence.
    """
    # Available parameters and fallback values
    pars = get_func_params(afoli, config, required_keys=required_keys,
                           ignore_keys=ignore_keys, int_keys=int_keys,
                           float_list_keys=float_list_keys, cfgvars=cfgvars)

    return pars

def afoli_iter_data(images: 'pathlib.Path',
                    config: SectionProxy,
                    plot_dir: Optional['pathlib.Path'] = None,
                    position: Optional[Tuple[int, int]] = None,
                    outfile: Optional['pathlib.Path'] = None,
                    resume: bool = False,
                    log: Callable = print) -> Dict['str', List[Tuple]]:
    """Run AFOLI by iterating over image data.

    Args:
      images: Image filenames.
      config: `ConfigParser` proxy with input for AFOLI.
      plot_dir: Optional. Plotting directory.
      position: Optional. Peak position to get the spectra from.
      outfile: Optional. File to record all the flags together.
      resume: Optional. Recalculate if channel files are detected?
      log: Optional. Logging function.

    Returns:
      A dictionary with each image file name associated with its frequency
      flags.
    """
    # Find position of spectra
    #if 'position' in config and position is None:
    #    position = tuple(map(int, config['position'].split(',')))
    if 'position' in config and position is None:
        ra, dec, frame = config['position'].split()
        position = SkyCoord(ra, dec, frame=frame)
    if position is None:
        log('Finding common peak position')
        method = config['collapse']
        save_collapsed = config.getboolean('save_collapse', fallback=True)
        log('Peak finding method: %s', method)
        position = get_common_position(images, method, resume=resume,
                                       save_collapsed=save_collapsed, log=log)
        log('Peak position: %s', position)
    else:
        log(f'Using input position: {position}')

    # Iterate cubes
    afoli_pars = get_afoli_pars(config)
    flux_unit = u.Unit(config['flux_unit'])
    line_flags = {}
    for imagename in images:
        # Output flags
        chan_flags_file = imagename.with_suffix('.line_chan_flags.txt')
        freq_flags_file = imagename.with_suffix('.line_freq_flags.txt')
        plot_file = plot_dir / imagename.with_suffix('.spec.afoli.png').name
        if freq_flags_file.exists() and resume:
            line_flags[freq_flags_file.name] = flags_from_file(freq_flags_file)
            continue

        # Get spectrum
        freq, spectrum = get_spectrum(cube_file=imagename, position=position,
                                      resume=resume, log=log)
        spectrum = spectrum.to(flux_unit)
        freq = freq.to(u.GHz)

        # Run AFOLI
        masked_spec = afoli(spectrum.value, log=log, chan_file=chan_flags_file,
                            plot_file=plot_file, **afoli_pars)
        line_flags[freq_flags_file.name] = get_freq_flags(freq, masked_spec)
        write_casa_freqs(line_flags[freq_flags_file.name], freq_flags_file)

    # Save all together?
    if outfile is not None:
        if outfile.is_file() and resume:
            pass
        else:
            lines = []
            for key, val in line_flags.items():
                lines.append(key + ':')
                lines.append(freqs_to_casa(val))
            outfile.write_text('\n'.join(lines))

    return line_flags
