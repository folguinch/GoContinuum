"""Utilities for working with CASA."""
from typing import Optional, Sequence, List, TypeVar, Callable, Mapping, Any
from inspect import signature
from collections import OrderedDict

from casatasks import vishead, tclean

from .common_types import SectionProxy

def get_spws(vis: 'pathlib.Path') -> List:
    """Retrieve the spws in a visibility ms."""
    return vishead(vis=str(vis), mode='get', hdkey='spw_name')[0]

def get_spws_indices(vis: 'pathlib.Path',
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

def check_tclean_params(config: SectionProxy,
                        required: Sequence[str] = ('cell', 'imsize')) -> None:
    """Check required config params."""
    # Check required arguments are in config
    for opt in required:
        if opt not in config:
            raise KeyError(f'Missing {opt} in configuration')

def get_tclean_params(
    config: SectionProxy,
    ignore_keys: Sequence[str] = ('vis', 'imagename', 'spw'),
    float_keys: Sequence[str]  = ('robust', 'pblimit', 'pbmask'),
    int_keys: Sequence[str] = ('niter', 'chanchunks'),
    bool_keys: Sequence[str] = ('interactive', 'parallel', 'pbcor',
                                'perchanweightdensity'),
) -> dict:
    """Filter input parameters and convert values to the correct type.

    Args:
      config: `ConfigParser` section proxy with input parameters to filter.
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
