"""Collection of actions to process diferent command line inputs."""
from glob import glob
from typing import List, Union
import argparse
import os
import pathlib

from astropy.io import fits
from configparseradv import configparser
from spectral_cube import SpectralCube
import astropy.coordinates as apycoord
import astropy.units as u
import astropy.wcs as apwcs
import numpy as np

#from ..array_utils import load_mixed_struct_array, load_struct_array
from .logger import get_stdout_logger, update_logger

def validate_path(path: pathlib.Path,
                  check_is_file: bool = False,
                  check_is_dir: bool = False,
                  mkdir: bool = False):
    """Performs several checks on input path.

    Args:
      path: path to check.
      check_is_file: optional; check whether is file and exists.
      check_is_dir: optional; check whther is a directory and exists.
      mkdir: optional; make directories if they do not exist.
    Returns:
      A validated resolved pathlib.Path object
    """
    path = path.expanduser().resolve()
    if check_is_file and not path.is_file():
        raise IOError(f'{path} does not exist')
    elif check_is_dir or mkdir:
        if not path.is_dir() and not mkdir:
            raise IOError(f'{path} directory does not exist')
        else:
            path.mkdir(parents=True, exist_ok=True)

    return path

def validate_paths(filenames: Union[str, List[str]],
                   check_is_file: bool = False,
                   check_is_dir: bool = False,
                   mkdir: bool = False):
    """Performs several checks on input list of file names.

    Args:
      filenames: list of filenames to check.
      check_is_file: optional; check whether is file and exists.
      check_is_dir: optional; check whther is a directory and exists.
      mkdir: optional; make directories if they do not exist.
    Returns:
      Validate path.Path from the input strings.
    """
    try:
        # Case single string file name
        validated = pathlib.Path(filenames)
        validated = validate_path(validated, check_is_file=check_is_file,
                                  check_is_dir=check_is_dir, mkdir=mkdir)
    except TypeError:
        # Case multiple file names
        validated = []
        for filename in filenames:
            aux = pathlib.Path(filename)
            aux = validate_path(aux, check_is_file=check_is_file,
                                check_is_dir=check_is_dir, mkdir=mkdir)
            validated.append(aux)

    return validated

def split_values(values: list):
    """Split the input values when quotations are used in `bash`.

    Args:
      values: list of values.
    """
    vals = []
    for val in values:
        vals += val.split()

    return vals

# Loader actions
#class LoadConfig(argparse.Action):
#    """Action class for loading a configuration file in argparse."""
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        values = validate_paths(values, check_is_file=True)
#        config = configparser.ConfigParserAdv()
#        config.read(values)
#        setattr(namespace, self.dest, config)
#
#class LoadArray(argparse.Action):
#    """Action class for loading a np.array from command line."""
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        array = np.array(values, dtype=float)
#        setattr(namespace, self.dest, array)
#
#class ArrayFromRange(argparse.Action):
#    """Action class for creating a np.array with linspace from command line"""
#
#    def __init__(self, option_strings, dest, nargs=2, **kwargs):
#        if nargs not in range(2, 5):
#            raise ValueError('only 2, 3 or 4 nargs allowed')
#        super().__init__(option_strings, dest, nargs=nargs, **kwargs)
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        start, stop = float(values[0]), float(values[1])
#        if len(values) == 4:
#            n = int(values[2])
#            if values[-1] == 'linear':
#                fn = np.linspace
#            elif values[-1] == 'log':
#                fn = np.logspace
#                start = np.log10(start)
#                stop = np.log10(stop)
#            else:
#                raise NotImplementedError(f'{values[-1]} not implemented')
#        elif len(values) == 3:
#            fn = np.linspace
#            n = int(values[2])
#        else:
#            fn = np.linspace
#        value = fn(start, stop, n)
#        setattr(namespace, self.dest, value)
#
#class LoadStructArray(argparse.Action):
#    """Load an structured np.array from file."""
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        array = load_struct_array(validate_paths(values, check_is_file=True))
#        setattr(namespace, self.dest, array)
#
#class LoadMixedStructArray(argparse.Action):
#    """Load a mixed structured np.array from file."""
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        array = load_mixed_struct_array(
#            validate_paths(values, check_is_file=True))
#        setattr(namespace, self.dest, array)
#
class LoadTXTArray(argparse.Action):
    """Load an np.array from file."""

    def __call__(self, parser, namespace, values, option_string=None):
        array = np.loadtxt(validate_paths(values, check_is_file=True),
                           dtype=float)
        setattr(namespace, self.dest, array)

class LoadFITS(argparse.Action):
    """Action for loading a FITS file with astropy"""

    def __call__(self, parser, namespace, values, option_string=None):
        values = validate_paths(values, check_is_file=True)
        try:
            vals = fits.open(values.resolve())[0]
        except AttributeError:
            vals = []
            for val in values:
                vals += [fits.open(val)[0]]
        setattr(namespace, self.dest, vals)

#class LoadCube(argparse.Action):
#    """Action for loading an SpectralCube"""
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        values = validate_paths(values, check_is_file=True)
#        try:
#            vals = SpectralCube.read(values.resolve())
#        except AttributeError:
#            vals = []
#            for val in values:
#                vals += [SpectralCube.read(val)]
#        setattr(namespace, self.dest, vals)
#
#class LoadDust(argparse.Action):
#    """Action for loading dust files"""
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        dust = Dust(values)
#        setattr(namespace, self.dest, dust)

#class LoadTable(argparse.Action):
#    """Action for loading astropy Tables"""
#
#    def __call__(self, parser, namespace, values, option_string=None):
#        try:
#            tabname = ''+values
#            #table_id = os.path.splitext(os.path.basename(tabname))[0]
#            table = Table(tabname)
#        except TypeError as exc:
#            if len(values) == 2:
#                table = Table(values[0], table_id=values[1])
#            elif len(values) == 1:
#                tabname = values[0]
#                #table_id = os.path.splitext(os.path.basename(tabname))[0]
#                table = Table(tabname)
#            else:
#                raise ValueError('Number of values not allowed.') from exc
#
#        setattr(namespace, self.dest, table)

# Lists actions
class ListFromFile(argparse.Action):
    """Load a list of strings from file."""

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs is not None:
            raise ValueError('nargs not allowed')
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        with open(values, 'r', encoding='utf-8') as dat:
            flist = dat.readlines()

        setattr(namespace, self.dest, flist)

class ListFromRegex(argparse.Action):
    """Load a list of files from a regular expression."""

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs is not None:
            raise ValueError('nargs not allowed')
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        flist = sorted(glob(os.path.expanduser(values)))

        setattr(namespace, self.dest, flist)

# Quantity actions
class ReadQuantity(argparse.Action):
    """Read quantity or a quantity list from the cmd line."""

    def __init__(self, option_strings, dest, nargs=2, enforce_list=False,
                 **kwargs):
        metavar = kwargs.pop('metavar', None)
        try:
            if nargs < 2:
                raise ValueError('nargs cannot be < 2')
            elif metavar is None:
                metavar = ('VAL',) * (nargs - 1) + ('UNIT',)
        except TypeError:
            if metavar is None:
                metavar = ('VAL', 'VAL UNIT')
        self.enforce_list = enforce_list

        super().__init__(option_strings, dest, nargs=nargs, metavar=metavar,
                         **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) < 2:
            raise ValueError(f'Cannot read quantity from values: {values}')
        vals = np.array(values[:-1], dtype=float)
        unit = u.Unit(values[-1])
        if len(vals) == 1 and not self.enforce_list:
            vals = vals[0]
        vals = vals * unit
        setattr(namespace, self.dest, vals)

class ReadUnit(argparse.Action):
    """Read quantity or a quantity list from the cmd line."""

    def __call__(self, parser, namespace, values, option_string=None):
        vals = []
        try:
            for val in values:
                vals.append(u.Unit(val))
            if len(vals) == 1:
                vals = vals[0]
        except ValueError:
            vals = u.Unit(values)
        setattr(namespace, self.dest, vals)

# Advanced processing actions
class PeakPosition(argparse.Action):
    """Load FITS file and get peak position as `SkyCoord`."""

    def __init__(self, option_strings, dest, nargs='*', **kwargs):
        if nargs not in ['*', '?', '+']:
            raise ValueError(f'nargs={nargs} not accepted for PeakPosition')
        kwargs.setdefault('metavar', ('FITSFILE',)*2)
        super().__init__(option_strings, dest, nargs=nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        positions = []
        values = validate_paths(values, check_is_file=True)
        for val in values:
            # Data
            imgi = fits.open(val)[0]
            wcs = apwcs.WCS(imgi.header, naxis=['longitude', 'latitude'])

            # Maximum
            data = np.squeeze(imgi.data)
            ymax, xmax = np.unravel_index(np.nanargmax(data), data.shape)

            # Store as skycoord in case it is used in image with different size
            positions += [apwcs.utils.pixel_to_skycoord(xmax, ymax, wcs)]

        setattr(namespace, self.dest, positions)

class ReadSkyCoords(argparse.Action):
    """Read one or more sky coordinates."""

    def __init__(self, option_strings, dest, nargs=2, **kwargs):
        try:
            if nargs < 2:
                raise ValueError('Only nargs values >= 2 accepted')
            if nargs%2 == 0:
                kwargs.setdefault('metavar', ('RA Dec',)*nargs)
            else:
                kwargs.setdefault('metavar',
                                  ('RA Dec ',)*(nargs-1) + ('FRAME',))
        except TypeError:
            kwargs.setdefault('metavar', ('RA Dec', 'RA Dec [FRAME]'))
        super().__init__(option_strings, dest, nargs=nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        values = split_values(values)
        if len(values) == 1:
            values = values[0].split()
        if len(values) < 2:
            raise ValueError('Could not read sky coordinate')
        elif len(values)%2 == 0:
            frame = 'icrs'
        else:
            frame = values[-1]
            values = values[:-1]
        vals = []
        for ra, dec in zip(values[::2], values[1::2]):
            vals.append(apycoord.SkyCoord(ra, dec, frame=frame))

        setattr(namespace, self.dest, vals)

# Path actions
class NormalizePath(argparse.Action):
    """Normalizes a path or filename."""

    def __call__(self, parser, namespace, values, option_string=None):
        values = validate_paths(values)
        setattr(namespace, self.dest, values)

class MakePath(argparse.Action):
    """Check and create directory if needed."""

    def __call__(self, parser, namespace, values, option_string=None):
        values = validate_paths(values, mkdir=True)
        setattr(namespace, self.dest, values)

class CheckFile(argparse.Action):
    """Validates files and check if they exist."""

    def __call__(self, parser, namespace, values, option_string=None):
        values = validate_paths(values, check_is_file=True)
        setattr(namespace, self.dest, values)

# Logger actions
class StartLogger(argparse.Action):
    """Create a logger.

    If nargs=? (default), log to default or const if provided and flag used
    else log only to stdout.
    For verbose levels, the standard option_string values are:
      -v, --vv, --vvv, --log, --info, --debug, --fulldebug
    With: -v = --log = --info
          --vv = --debug
          --vvv = --fulldebug
    Other values will create a normal logger.
    """

    def __init__(self, option_strings, dest, nargs='?', metavar='LOGFILE',
                 const=None, default=None, **kwargs):
        # Cases from nargs
        if nargs not in ['?']:
            raise ValueError('nargs value not allowed')

        # Default dest and default log file
        dest = 'log'
        self._logfile = const or default

        # Set default to stdout
        const = None
        default = get_stdout_logger('__main__', verbose='v')

        super().__init__(option_strings, dest, nargs=nargs, metavar=metavar,
                         const=const, default=default, **kwargs)

    def __call__(self, parser, namespace, value, option_string=None):
        if value is None:
            value = self._logfile

        # Determine verbose
        if option_string in ['-v', '--log', '--info']:
            verbose = 'v'
        elif option_string in ['--vv', '--debug']:
            verbose = 'vv'
        elif option_string in ['--vvv', '--fulldebug']:
            verbose = 'vvv'
        else:
            verbose = None

        logger = update_logger(self.default, filename=value, verbose=verbose)
        setattr(namespace, self.dest, logger)

