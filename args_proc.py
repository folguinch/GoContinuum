"""Tools for processing argument parser inputs."""
from typing import TypeVar
from pathlib import Path
import configparser as cparser

import casa_utils as utils

# Types
NameSpace = TypeVar('NameSpace')

def set_config(args: NameSpace):
    """The `config` value in `args`.

    It assumes:

    - A `configfile` arguments exists in the parser.
    - The initial value of `config` is a dictionary with default values for the
      `configparser`.
    - A `section` value is stored in the parser.
    """
    # Configuration file
    parserfile = Path(args.configfile[0])

    # Read configuration
    configuration = cparser.ConfigParser(args.config)
    if parserfile.exists():
        configuration.read(parserfile)
    else:
        raise IOError(f'Config file does not exists: {parserfile}')

    # Update config value
    try:
        if args.section in configuration:
            args.config = configuration[args.section]
        else:
            raise cparser.NoSectionError(
                f'Section {args.section} does not exists'
            )
    except TypeError as exc:
        if args.section[0] in configuration:
            args.config = configuration[args.section[0]]
        else:
            raise cparser.NoSectionError(
                f'Section {args.section[0]} does not exists') from exc

def get_tclean_params(args: NameSpace):
    """Store `tclean` parameters in args.

    It assumes that `tclean_params` and `config` arguments exist in the parser.
    """
    # Get parameters
    tclean_pars = utils.get_tclean_params(args.config)
    args.tclean_params = tclean_pars
    args.log.post(f'tclean non-default parameters: {tclean_pars}')
