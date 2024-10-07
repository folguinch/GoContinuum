"""Utilities for working with CASA."""
from typing import (Optional, Sequence, List, TypeVar, Callable, Mapping, Any,
                    Tuple, Dict)
from inspect import signature
from collections import OrderedDict

import astropy.units as u
import numpy.typling as npt
from casatasks import vishead

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

def iter_data(data: Sequence['data_handler.DataHandler']):
    """Generator to iterate over data and their spws properties."""
    for ebdata in data:
        for spw, stem in ebdata.spw_stems.items():
            yield ebdata, spw, stem

def get_func_params(func: Callable,
                    config: SectionProxy,
                    required_keys: Sequence[str] = (),
                    ignore_keys: Sequence[str] = (),
                    float_keys: Sequence[str] = (),
                    int_keys: Sequence[str] = (),
                    bool_keys: Sequence[str] = (),
                    int_list_keys: Sequence[str] = (),
                    float_list_keys: Sequence[str] = (),
                    sep: str = ',',
                    cfgvars: Optional[Dict] = None,
                    ) -> Dict:
    """Check the input parameters of a function and convert.
    
    Args:
      func: function to inspect.
      config: configuration parser section proxy.
      required_keys: optional; required keys.
      ignore_keys: optional; keys to ignore.
      float_keys: optional; keys required as float type.
      int_keys: optional; keys required as int type.
      bool_keys: optional; keys required as bool type.
      int_list_keys: optional; keys required as list of integers.
      float_list_keys: optional; keys required as list of floats.
      sep: optional; separator for the values in list keys.
      cfgvars: optional; values replacing those in config.
    """
    # Default values
    if cfgvars is None:
        cfgvars = dict()

    # Check required arguments are in config
    for opt in required:
        if opt not in config or opt not in cfgvars:
            raise KeyError(f'Missing {opt} in configuration')

    # Filter paramters
    pars = {}
    for key in signature(func).parameters:
        if (key not in config and key not in cfgvars) or key in ignore_keys:
            continue
        #Check for type:
        if key in float_keys:
            pars[key] = config.getfloat(key, vars=cfgvars)
        elif key in int_keys:
            pars[key] = config.getint(key, vars=cfgvars)
        elif key in bool_keys:
            pars[key] = config.getboolean(key, vars=cfgvars)
        else:
            val = config.get(key, vars=cfgvars)
            if key in int_list_keys:
                pars[key] = list(map(int, val.split(sep)))
            elif key in float_list_keys:
                pars[key] = list(map(float, val.split(sep)))
            else:
                pars[key] = config.get(val)

    return pars

