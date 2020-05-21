#!casa -c
import argparse
import os
from ConfigParser import ConfigParser

"""Perform uvcontsub and apply calibration table if required

The input for applycal can be configured in the `lineapplycal` (default)
section of the configuration file. For observations with more than one EB, the 
command line argument `eb` can be used. To specify the table for each EB, 2 
methods are available:
    1. Define a section `lineapplycal<i>` with `i` the EB number
    2. Comma separated values for each EB. If multiple table are used per EB,
    space is used per EB, e.g `caltable = cal1EB1 cal2EB1, cal1EB2 ...`. With
    the exception of the `interp` parameter, which  uses semi-colon separated
    values.

"""

class NormalizePath(argparse.Action):
    """Normalizes a path or filename"""

    def __call__(self, parser, namespace, values, option_string=None):
        newval = []
        for val in values:
            newval += [os.path.realpath(os.path.expandvars(os.path.expanduser(val)))]
        setattr(namespace, self.dest, newval)

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
    nspw = len(vishead(vis=vis, mode='get', hdkey='spw_name')[0])
    if len(args.chans) != nspw:
        raise ValueError('Number of spws does != number of channel files')

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

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    #parser.add_argument('--concatvis', nargs=1, type=str, 
    #        help='Concatenated ms name')
    parser.add_argument('--section', nargs=1, type=str, default=['uvcontsub'],
            help='Section in config file')
    parser.add_argument('--eb', nargs=1, type=int, default=None,
            help='EB number')
    parser.add_argument('configfile', nargs=1, action=NormalizePath, 
            help='Configuration file')
    parser.add_argument('uvdata', nargs=1, action=NormalizePath,
            help='uv data ms')
    parser.add_argument('chans', nargs='*', action=NormalizePath, #type=str, #type=argparse.FileType('r'),
            help='Channel list files')
    args = parser.parse_args()

    # Verify arguments
    verify_args(args)

    # Config file
    config = ConfigParser({'calwt':'false', 'interp':'linear',
        'flagbackup':'false', 'spwmap':''})
    config.read(args.configfile[0])
    appsect = 'lineapplycal'
    if args.eb is not None:
        aux = '%s%i' % (appsect, args.eb[0])
        if config.has_section(aux):
            appsect = aux
            ebind = None
        else:
            ebind = args.eb-1
    else:
        ebind = None
    
    # Obtain fitspws
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
    fitspw = ','.join(fitspws)

    #vis = []
    #for uvdata in args.uvdata:
    # Run uvcontsub
    uvcontsub(vis=args.uvdata[0],
            fitspw=fitspw,
            want_cont=False,
            combine='spw',
            excludechans=True,
            fitorder=1)
        #vis += [uvdata+'.contsub']
    outvis = args.uvdata[0]+'.contsub'

    ## Concat
    #if args.concatvis
    #    concat(vis=vis, concatvis=args.concatvis[0])

    # Apply calibration table (mainly for selfcal)
    if not config.has_section(appsect):
        return
    else:
        # Back up flags
        flagmanager(vis=outvis, mode='save', versionname='before_selfcal',
                merge='replace')

        # Applycal
        field = config.get(appsect, 'field')
        gaintable = get_value(config, appsect, 'gaintable', n=ebind).split()
        spwmap = map(int, get_value(config, appsect, 'spwmap', n=ebind).split())
        calwt = get_bool(get_value(config, appsect, 'calwt', n=ebind).split())
        flagbackup = config.getboolean(appsect, 'flagbackup')
        interp = get_value(config, appsect, 'interp', n=ebind, sep=';').split()
        applycal(vis=outvis, field=field, spwmap=spwmap, gaintable=gaintable,
                calwt=calwt, flagbackup=flagbackup, interp=interp)

        # Split ms
        outsplitvis = outvis + '.selfcal'
        split(vis=outvis, outputvis=outsplitvis, datacolumn='corrected')

if __name__=="__main__":
    main()
