"""Argument parser processing tools."""
from configparser import ConfigParser
from pathlib import Path

from .data_handler import DataHandler

def set_casa_logging(args: 'argparse.Namespace') -> None:
    """Set casalog log file from argument parser object."""
    # Logging
    if args.logfile is not None:
        args.log.setlogfile(args.logfile[0])
    args.log.showconsole(True)

def set_config(args: 'argparse.Namespace'):
    """Setup the `config` value in `args`.

    It assumes:

    - A `configfile` arguments exists in the parser.
    - The initial value of `config` is a dictionary with default values for the
      `configparser`, or None.
    
    An optional `section` value can be stored in the argument parser, in such
    case a `section_proxy` is returned.
    """
    # Read configuration
    args.log.info('Reading configuration: %s', args.configfile)
    args.config = ConfigParser(defaults=args.config)
    args.config.read(args.configfile)

    # Update config value
    try:
        if args.section in configuration:
            args.log('Setting section: %s', args.section)
            args.config = configuration[args.section]
        else:
            raise cparser.NoSectionError(
                f'Section {args.section} does not exists'
            )
    except TypeError as exc:
        if args.section[0] in configuration:
            args.log('Setting section: %s', args.section[0])
            args.config = configuration[args.section[0]]
        else:
            raise cparser.NoSectionError(
                f'Section {args.section[0]} does not exists') from exc
    except AttributeError:
        args.log('No specific section requested')

def get_data(args: 'argparse.Namespace') -> List[DataHandler]:
    """Get the data necessary for goco."""
    data = []
    for i, uv in enumerate(args.uvdata):
        args.log.info('Reading %s', uv)
        if not uv.is_dir():
            raise IOError(f'Cannot find uvdata: {uv}')
        eb = None if len(uvdata) == 0 else i+1
        info = DataHandler(name=uv.stem, uvdata=uv, eb=eb,
                           spws=utils.get_spws_indices(uv, log=args.log.info))
        args.log.info('Found spectral windows: %s', info['spws'])
        uvdata.append(info)

    return data

def get_tclean_params(args: 'argparse.Namespace'):
    """Store `tclean` parameters in args.

    It assumes that `tclean_params` and `config` arguments exist in the parser.
    """
    # Get parameters
    tclean_pars = utils.get_tclean_params(args.config)
    args.tclean_params = tclean_pars
    args.log.post(f'tclean non-default parameters: {tclean_pars}')

def prep_data(args: 'argparse.Namespace'):
    """Prepare available data."""
    # Read config
    set_config(args)

    # Read uvdata
    if args.uvdata is None:
        uvdata = args.config.get('DEFAULT', 'uvdata', fallback=None)
        if uvdata is None:
            args.uvdata = []
        else:
            args.uvdata = [Path(x.strip()) for x in uvdata.split(',')]
            args.log.info('UV data from config: %s', args.uvdata)
    if len(args.uvdata) == 0:
        args.log.warning('UV data not found, will only run afoli')
        skip = ['dirty', 'applycal', 'contsub', 'split', 'yclean', 'pbclean']
        for step in skip:
            args.steps[step] = False
    else:
        args.log.info('Found %i measurement sets', len(args.uvdata))

def goco_pipe(args: 'argparse.Namespace'):
    """Process data following the requested steps."""
    # Get uvdata information
    data = get_data(args)

    # Dirty images
    if args.steps['dirty']:
        data = compute_dirty(data, args.dirty_dir, args.config['dirty'],
                             nproc=args.nproc, redo=args.redo,
                             log=args.log.info)
    else:
        # If data has handlers, then assume the dirty files are correctly named
        if len[data] == 0:
            content = list(dirty_dir.glob('*.fits'))
            data = [DataHandler(stems=[fname.stem for fname in content])]

    # AFOLI
    if args.steps['afoli']:
        run_afoli(data, args.config['afoli'], args.dirty_dir, redo=args.redo,
                  log=args.log.info)
    else:
        chan_files = args.dirty_dir.glob('*chan.txt')

    if args.steps['applycal']:
        uvdata = apply_caltable(uvdata, args.config['applycal'])

    if args.steps['contsub']:
        uvdata_contsub = compute_contsub(uvdata, chan_files)

