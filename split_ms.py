import argparse
from ConfigParser import ConfigParser

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    #parser.add_argument('--concatvis', nargs=1, type=str, 
    #        help='Concatenated ms name')
    parser.add_argument('--widths_avg', default=[120,120,120,120], type=int,
            help='Channel width average')
    parser.add_argument('configfile', nargs=1, type=str,
            help='Configuration file name')
    parser.add_argument('uvdata', nargs=1, type=str,
            help='uv data ms')
    parser.add_argument('chans', nargs='*', type=argparse.FileType('r'),
            help='Channel list files')
    args = parser.parse_args()

    # Config file
    config = ConfigParser()
    config.read(args.configfile[0])
    
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
            spw=config.get('split_ms','spw',fallback='0,1,2,3'),
            outputvis=args.uvdata[0]+'.cont_avg',
            width=args.widths_avg,
            datacolumn=config.get('split_ms','datacolumn',fallback='corrected'))
    flagmanager(vis=args.uvdata[0], mode='restore', versionname='before_cont_flags')
    
    # Split unflagged
    split(vis=args.uvdata[0],
            spw=config.get('split_ms','spw',fallback='0,1,2,3'),
            outputvis=args.uvdata[0]+'.allchannels_avg', width=args.widths_avg,
            datacolumn=config.get('split_ms','datacolumn',fallback='corrected'))

if __name__=="__main__":
    main()
