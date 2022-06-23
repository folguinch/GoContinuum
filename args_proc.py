from pathlib import Path
import configparser as cparser

import casa_utils as utils

def check_tclean_params(args: NameSpace, 
                        required: List[str] = ['cell', 'imsize']) -> None:
    """Check required config params."""
    # Check cell size and imsize are in the config
    for opt in required:
        if opt not in args.config:
            raise KeyError(f'Missing {opt} in configuration')

def set_config(args: NameSpace):
    """The the `config` value in `args`.

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
        configuration.read(parsefile)
    else:
        raise IOError(f'Config file does not exists: {parserfile}')

    # Update config value
    try:
        if args.section in args.config:
            args.config = configuration[args.section]
        else:
            raise cparser.NoSectionError(
                f'Section {args.section} does not exists'
            )
    except TypeError:
        if args.section[0] in args.config:
            args.config = configuration[args.section[0]]
        else:
            raise cparser.NoSectionError(
                f'Section {args.section[0]} does not exists'
            )

def get_tclean_params(args: NameSpace):
    """Store `tclean` parameters in args.

    It assumes that `tclean_params` and `config` arguments exist in the parser.
    """
    # Check parameters
    check_tclean_params(args)

    # Get parameters
    tclean_pars = utils.get_tclean_params(args.config)
    args.tclean_params = tclean_pars
    try:
        args.log.post(f'tclean non-default parameters: {tclean_pars}')
    except:
        pass
