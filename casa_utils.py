import argparse
import os
from ConfigParser import ConfigParser
from collections import OrderedDict

#from applycal_cli import applycal
#from split_cli import split
from taskinit import casalog
from tasks import applycal, split
from flagmanager_cli import flagmanager
import vishead_cli as vcli

##################### General Functions #####################

def get_spws_indices(vis, spws=None):
    # Spectral windows names
    names = get_spws(vis)
    name_set = set(names)

    # Cases
    if len(name_set) != len(names):
        casalog.post('Data contains duplicated spectral windows')
        spwinfo = OrderedDict()
        for i, key in enumerate(names):
            if key not in spwinfo:
                spwinfo[key] = '%i' % i
            else:
                spwinfo[key] += ',%i' % i
    else:
        spwinfo = OrderedDict(zip(names, map(str, range(len(names)))))

    # Spectral windows indices
    if spws is not None:
        spw_ind = map(int, spws)
    else:
        spw_ind = range(len(name_set))

    return [spw for i,spw in enumerate(spwinfo.values()) if i in spw_ind]

def get_value(cfg, sect, opt, default=None, n=None, sep=','):
    # Initial value
    value = cfg.get(sect, opt)

    # Split value 
    value = value.split(sep)

    # Cases:
    if len(value) == 0:
        value = ''
    elif len(value) == 1 and n is None:
        value = value[0]
    elif len(value) > 1 and n is None:
        # Just in case someone used coma separated value for single eb
        casalog.post('More than one value for %s, using all' % opt, 'WARN')
        value = ' '.join(value)
    elif n>=0:
        value = value[n]
    else:
        value = default

    return value

def get_bool(values):
    newval = []

    for val in values:
        if val.lower() in ['true', '1']:
            newval += [True]
        else:
            newval += [False]

    return newval

def get_spws(vis):
    return vcli.vishead(vis=vis, mode='get', hdkey='spw_name')[0]

def run_cal(cfg, section, vis, neb=None):
    # Check for EB specific sections
    if neb is not None:
        aux = '%s%i' % (section, neb)
        if cfg.has_section(aux):
            sect = aux
            ebind = None
        else:
            sect = section
            ebind = neb - 1
    else:
        sect = section
        ebind = None

    # Calibrate
    if not cfg.has_section(sect):
        casalog.post('Apply (self-)calibration table not requested')
        return
    else:
        # Back up flags
        casalog.post('Using gaintable from section: %s' % sect)
        flagmanager(vis=vis, mode='save', versionname='before_selfcal',
                merge='replace', comment='before selfcal')

        # Applycal
        field = cfg.get(sect, 'field')
        gaintable = get_value(cfg, sect, 'gaintable', n=ebind).split()
        spwmap = map(int, get_value(cfg, sect, 'spwmap', n=ebind).split())
        calwt = get_bool(get_value(cfg, sect, 'calwt', n=ebind).split())
        flagbackup = cfg.getboolean(sect, 'flagbackup')
        interp = get_value(cfg, sect, 'interp', n=ebind, sep=';').split()
        applycal(vis=vis, field=field, spwmap=spwmap, gaintable=gaintable,
                calwt=calwt, flagbackup=flagbackup, interp=interp)

        # Split ms
        outsplitvis = vis + '.selfcal'
        split(vis=vis, outputvis=outsplitvis, datacolumn='corrected')

##################### Argparse Processing #####################

def verify_args(args):
    # File existance
    # Visibilities
    vis = args.uvdata[0]
    if not os.path.isdir(vis):
        raise IOError('MS %s does not exist' % vis)
    # Configuration file
    config = args.configfile[0]
    if not os.path.isfile(config):
        raise IOError('Config file %s does not exist' % config)
    # Channel files
    for chanfile in args.chans:
        if not os.path.isfile(chanfile):
            raise IOError('Channel file %s does not exist' % chanfile)

    # Number of spws
    nspw = len(get_spws(vis))
    if len(args.chans) != nspw:
        raise ValueError('Number of spws does != number of channel files')

def load_config(args):
    # Initialize
    if args.config is not None and hasattr(args.config, 'keys'):
        args.config = ConfigParser(args.config)
    else:
        args.config = ConfigParser()

    # Load file
    args.config.read(args.configfile[0])

def load_chan_list(args):
    fitspws = []
    for i, chfile in enumerate(args.chans):
        casalog.post('SPW = %i' % i)
        casalog.post('Channel file = %s' % chfile)
        with open(chfile, 'r') as chlist:
            lines = chlist.readlines()
        if len(lines)!=1:
            raise ValueError('Channel file needs only 1 line')
        else:
            fitspw = "%i:%s" % (i, lines[0])
            fitspws += [fitspw.strip()]
    args.fitspw = ','.join(fitspws)

def _run_cal(args):
    if not os.path.isdir(args.outvis):
        raise IOError('MS %s does not exist' % args.outvis)
    run_cal(args.config, args.calsect, args.outvis, neb=args.eb[0])

##################### Argparse actions #####################

class NormalizePath(argparse.Action):
    """Normalizes a path or filename"""

    def __call__(self, parser, namespace, values, option_string=None):
        newval = []
        for val in values:
            newval += [os.path.realpath(os.path.expandvars(os.path.expanduser(val)))]
        setattr(namespace, self.dest, newval)
