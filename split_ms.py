import argparse
from ConfigParser import ConfigParser

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    #parser.add_argument('--concatvis', nargs=1, type=str, 
    #        help='Concatenated ms name')
    parser.add_argument('--widths_avg', default=None, type=str,
            help='Channel width average (coma separated)')
    parser.add_argument('configfile', nargs=1, type=str,
            help='Configuration file name')
    parser.add_argument('uvdata', nargs=1, type=str,
            help='uv data ms')
    parser.add_argument('chans', nargs='*', type=argparse.FileType('r'),
            help='Channel list files')
    args = parser.parse_args()

    # Config file
    config = ConfigParser({'spws':'0,1,2,3', 'datacolumn':'corrected'})
    config.read(args.configfile[0])
    
    # Define width and validate
    if args.widths_avg is not None:
        width = map(int, args.widths_avg.split(','))
    elif 'width' in config.options('split_ms'):
        width = map(int, config.get('split_ms','width').split())
    else:
        casalog.post('width parameter is not defined', 'SEVERE')
        raise ValueError('width parameter is not defined')
    lenspw = len(config.get('split_ms','spws').split(','))
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
    for i, chlist in enumerate(args.chans):
        fitspw = "%i:%s" % (i, chlist.readline())
        fitspws += [fitspw.strip()]
    fitspw = ','.join(fitspws)

    # Split flagged
    flagmanager(vis=args.uvdata[0], mode='save', versionname='before_cont_flags')
    initweights(vis=args.uvdata[0], wtmode='weight', dowtsp=True)
    flagdata(vis=args.uvdata[0], mode='manual', spw=fitspw, flagbackup=False)
    split(vis=args.uvdata[0],
            spw=config.get('split_ms','spws'),
            outputvis=args.uvdata[0]+'.cont_avg',
            width=width,
            datacolumn=config.get('split_ms','datacolumn'))
    flagmanager(vis=args.uvdata[0], mode='restore', versionname='before_cont_flags')
    
    # Split unflagged
    split(vis=args.uvdata[0],
            spw=config.get('split_ms','spws'),
            outputvis=args.uvdata[0]+'.allchannels_avg', 
            width=width,
            datacolumn=config.get('split_ms','datacolumn'))

if __name__=="__main__":
    main()
