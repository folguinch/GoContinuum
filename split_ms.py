import argparse

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    #parser.add_argument('--concatvis', nargs=1, type=str, 
    #        help='Concatenated ms name')
    parser.add_argument('--widths_avg', default=[120,120,120,120], type=int,
            help='Channel width average')
    parser.add_argument('--spw', default=None, type=int, choices=[0,1,2,3],
            help='Spectral window')
    parser.add_argument('uvdata', nargs=1, type=str,
            help='uv data ms')
    parser.add_argument('chans', nargs='*', type=argparse.FileType('r'),
            help='Channel list files')
    args = parser.parse_args()
    
    # Obtain fitspws
    fitspws = []
    for i, chlist in enumerate(args.chans):
        fitspw = "%i:%s" % (i, chlist.readline())
        fitspws += [fitspw.strip()]
    fitspw = ','.join(fitspws)

    # If spw:
    if args.spw:
        spw = '%s' % spw
        outputvis1 = args.uvdata[0] + '.spw%s.cont_avg' % spw
        outputvis2 = args.uvdata[0] + '.spw%s.allchannels_avg' % spw
        width = args.widths_avg[args.spw]
    else:
        spw = '0,1,2,3'
        outputvis1 = args.uvdata[0] + '.cont_avg'
        outputvis2 = args.uvdata[0] + '.allchannels_avg' % spw
        width = args.widths_avg

    # Split flagged
    flagmanager(vis=args.uvdata[0], mode='save', 
            versionname='before_cont_flags')
    initweights(vis=args.uvdata[0], wtmode='weight', dowtsp=True)
    flagdata(vis=args.uvdata[0], mode='manual', spw=fitspw, flagbackup=False)
    split(vis=args.uvdata[0], spw=spw, outputvis=outputvis1,
            width=width, datacolumn='corrected')
    flagmanager(vis=args.uvdata[0], mode='restore', 
            versionname='before_cont_flags')
    
    # Split unflagged
    split(vis=args.uvdata[0], spw=spw, outputvis=outputvis2, 
            width=width, datacolumn='corrected')

if __name__=="__main__":
    main()
