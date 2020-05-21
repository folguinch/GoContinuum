import os, argparse
from ConfigParser import ConfigParser

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

def run_cal(cfg, vis, neb):
    sect = 'contapplycal'
    if neb is not None:
        aux = '%s%i' % (sect, neb)
        if cfg.has_section(aux):
            sect = aux
            ebind = None
        else:
            ebind = neb-1
    else:
        ebind = None

    if not cfg.has_section(sect):
        return
    else:
        # Back up flags
        flagmanager(vis=vis, mode='save', versionname='before_selfcal',
                merge='replace')

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

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    #parser.add_argument('--concatvis', nargs=1, type=str, 
    #        help='Concatenated ms name')
    parser.add_argument('--section', nargs=1, type=str, default=['split_ms'],
            help='Section in config file')
    parser.add_argument('--eb', nargs=1, type=int, default=[None],
            help='EB number')
    parser.add_argument('--widths_avg', default=None, type=str,
            help='Channel width average (coma separated)')
    parser.add_argument('configfile', nargs=1, action=NormalizePath,
            help='Configuration file name')
    parser.add_argument('uvdata', nargs=1, action=NormalizePath,
            help='uv data ms')
    parser.add_argument('chans', nargs='*', action=NormalizePath,
            help='Channel list files')
    args = parser.parse_args()

    # Verify arguments
    verify_args(args)

    # Config file
    config = ConfigParser({'spws':'0,1,2,3', 'datacolumn':'corrected', 
        'calwt':'false', 'interp':'linear', 'flagbackup':'false', 'spwmap':''})
    config.read(args.configfile[0])
    section = args.section[0]
    
    # Define width and validate
    if args.widths_avg is not None:
        width = map(int, args.widths_avg.split(','))
    elif 'width' in config.options(section):
        width = map(int, config.get(section,'width').split())
    else:
        casalog.post('width parameter is not defined', 'SEVERE')
        raise ValueError('width parameter is not defined')
    lenspw = len(config.get(section,'spws').split(','))
    if len(width)!=lenspw:
        if len(width)==1:
            casalog.post('Using the same width for all spws', 'WARN')
            width = width*lenspws
        else:
            msg = 'The number of spws does not match the number of widths'
            casalog.post(msg, 'SEVERE')
            raise ValueError(msg)
    
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

    # Split flagged
    flagmanager(vis=args.uvdata[0], mode='save', versionname='before_cont_flags')
    initweights(vis=args.uvdata[0], wtmode='weight', dowtsp=True)
    flagdata(vis=args.uvdata[0], mode='manual', spw=fitspw, flagbackup=False)
    outputvis = args.uvdata[0]+'.cont_avg'
    if os.path.isdir(outputvis):
        casalog.post('Deleting %s' % outputvis, 'WARN')
        os.system('rm -rf %s' % outputvis)
    split(vis=args.uvdata[0],
            spw=config.get(section,'spws'),
            outputvis=outputvis,
            width=width,
            datacolumn=config.get(section,'datacolumn'))
    flagmanager(vis=args.uvdata[0], mode='restore', versionname='before_cont_flags')
    run_cal(config, outputvis, args.eb[0])
    
    # Split unflagged
    outputvis = args.uvdata[0]+'.allchannels_avg'
    if os.path.isdir(outputvis):
        casalog.post('Deleting %s' % outputvis, 'WARN')
        os.system('rm -rf %s' % outputvis)
    split(vis=args.uvdata[0],
            spw=config.get(section,'spws'),
            outputvis=outputvis, 
            width=width,
            datacolumn=config.get(section,'datacolumn'))
    run_cal(config, outputvis, args.eb[0])

if __name__=="__main__":
    main()
