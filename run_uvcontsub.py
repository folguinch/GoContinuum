#!casa -c
import argparse

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    #parser.add_argument('--concatvis', nargs=1, type=str, 
    #        help='Concatenated ms name')
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

    ## Concat
    #if args.concatvis
    #    concat(vis=vis, concatvis=args.concatvis[0])

if __name__=="__main__":
    main()
