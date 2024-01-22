"""Argument parser processing tools."""
from typing import List
from configparser import ConfigParser
from pathlib import Path

from goco_helpers.clean_tasks import compute_dirty, get_tclean_params
from .data_handler import DataManager
from .utils import get_spws_indices

#def set_casa_logging(args: 'argparse.Namespace') -> None:
#    """Set casalog log file from argument parser object."""
#    # Logging
#    if args.logfile is not None:
#        args.log.setlogfile(args.logfile[0])
#    args.log.showconsole(True)
#
#def set_config(args: 'argparse.Namespace'):
#    """Setup the `config` value in `args`.
#
#    It assumes:
#
#    - A `configfile` arguments exists in the parser.
#    - The initial value of `config` is a dictionary with default values for the
#      `configparser`, or None.
#    
#    An optional `section` value can be stored in the argument parser, in such
#    case a `section_proxy` is returned.
#    """
#    # Read configuration
#    args.log.info('Reading configuration: %s', args.configfile)
#    args.config = ConfigParser(defaults=args.config)
#    args.config.read(args.configfile)
#
#    # Update config value
#    try:
#        if args.section in args.config:
#            args.log.info('Setting section: %s', args.section)
#            args.config = args.config[args.section]
#        else:
#            raise cparser.NoSectionError(
#                f'Section {args.section} does not exists'
#            )
#    except TypeError as exc:
#        if args.section[0] in args.config:
#            args.log.info('Setting section: %s', args.section[0])
#            args.config = args.config[args.section[0]]
#        else:
#            raise cparser.NoSectionError(
#                f'Section {args.section[0]} does not exists') from exc
#    except AttributeError:
#        args.log.info('No specific section requested')
#
#def get_data(args: 'argparse.Namespace') -> List[DataHandler]:
#    """Get the data necessary for goco.
#    
#    Each element of the output list is a `DataHandler` storing information
#    regarding the uvdata information:
#
#    - The uvdata execution block `eb` value is determined by the order the
#      uvdata is input in the command line.
#    - The spws in the uvdata are also stored. If different `eb`s were
#      concatenated, then matching spws are stored together.
#
#    Note that whether the data is concatenated beforehand or not will have
#    different effects in following steps.
#    """
#    data = []
#    for i, uv in enumerate(args.uvdata):
#        args.log.info('Reading %s', uv)
#        if not uv.is_dir():
#            raise IOError(f'Cannot find uvdata: {uv}')
#        eb = None if len(uvdata) == 0 else i+1
#        info = DataHandler(name=uv.stem, uvdata=uv, eb=eb,
#                           spws=get_spws_indices(uv, log=args.log.info))
#        args.log.info('Found spectral windows: %s', info['spws'])
#        data.append(info)
#
#    return data
#
#def set_tclean_params(args: 'argparse.Namespace'):
#    """Store `tclean` parameters in args.
#
#    It assumes that `tclean_params` and `config` arguments exist in the parser.
#    """
#    # Get parameters
#    tclean_pars = get_tclean_params(args.config)
#    args.tclean_params = tclean_pars
#    args.log.info('tclean non-default parameters: %s', tclean_pars)

#def prep_data(args: 'argparse.Namespace') -> None:
#    """Prepare available data.
#    
#    - Read the configuration file.
#    - Check uvdata. If uvdata is not given then the steps requiring it will be
#      skipped.
#    """
#    # Read config
#    set_config(args)
#
#    # Read uvdata
#    if args.uvdata is None:
#        uvdata = args.config.get('DEFAULT', 'uvdata', fallback=None)
#        if uvdata is None:
#            args.uvdata = []
#        else:
#            args.uvdata = [Path(x.strip()) for x in uvdata.split(',')]
#            args.log.info('UV data from config: %s', args.uvdata)
#    if len(args.uvdata) == 0:
#        args.log.warning('UV data not found, will only run afoli')
#        skip = ['dirty', 'applycal', 'contsub', 'split', 'yclean', 'pbclean']
#        for step in skip:
#            args.steps[step] = False
#    else:
#        args.log.info('Found %i measurement sets', len(args.uvdata))

#def goco_pipe(args: 'argparse.Namespace'):
#    """Process data following the requested steps.
#    
#    - It reads the uvdata to get the number of spectral windows per uvdata, and
#      stores the information of each uvdata in a `DataHandler` object.
#    - It calculate the dirty files if requested. It updates the `DataHandler`
#      objects if there is no data information from uvdata, so only AFOLI is run
#      on whatever is available in `dirty_dir`.
#    - It runs AFOLI or the available channel files are stored.
#    """
    ## Get uvdata information
    #data = get_data(args)

    ## Dirty images
    #if args.steps['dirty']:
    #    data = compute_dirty(data, args.dirty_dir, args.config['dirty'],
    #                         nproc=args.nproc, redo=args.redo,
    #                         log=args.log.info)
    #else:
    #    # If data has handlers, then assume the dirty files are correctly named
    #    if len[data] == 0:
    #        content = list(dirty_dir.glob('*.fits'))
    #        data = [DataHandler(stems=[fname.stem for fname in content])]

    ## AFOLI
    #if args.steps['afoli']:
    #    run_afoli(data, args.config['afoli'], args.dirty_dir, redo=args.redo,
    #              log=args.log.info)
    #else:
    #    chan_files = args.dirty_dir.glob('*chan.txt')

    #if args.steps['applycal']:
    #    uvdata = apply_caltable(uvdata, args.config['applycal'])

    #if args.steps['contsub']:
    #    uvdata_contsub = compute_contsub(uvdata, chan_files)

