import os, argparse
from ConfigParser import ConfigParser

def get_box(imagename, size=50):
    # Get image size
    imshape = imhead(imagename=imagename, mode='get', hdkey='shape')

    # Box
    xtrc = imshape[0]/4
    ytrc = imshape[0]/2
    xblc = xtrc - size
    ytrc = ytrc - size

    return "%i,%i,%i,%i" % (xblc, ytrc, xtrc, ytrc)

def put_rms(imagename, box=""):
    # Get rms
    stats = imstat(imagename=imagename, box=box, stokes='I')

    # Put in header
    imhead(imagename=imagename, mode='put', hdkey='rms',
            hdvalue=stats['rms'][0])

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    parser.add_argument('--dirtydir', nargs=1, type=str, default=['../dirty'],
            help='Directory of dirty images')
    parser.add_argument('--nrms', nargs=1, type=float, default=[2],
            help='Number of rms level')
    parser.add_argument('--nothreshold', action='store_true',
            help='Number of rms level')
    parser.add_argument('--continuum', action='store_true',
            help='Clean continuum image')
    parser.add_argument('--spw', nargs=1, type=str,
            help='Image file name')
    parser.add_argument('uvdata', nargs=1, type=str,
            help='uv data ms')
    parser.add_argument('imagename', nargs=1, type=str,
            help='Image file name')
    parser.add_argument('configfile', nargs=1, type=str,
            help='Configuration file name')
    args = parser.parse_args()

    config = ConfigParser()
    config.read(args.configfile[0])
    field = args.get('pbclean', 'field')
    imsize = map(int, config.get('pbclean', 'imsize').split())
    cellsize = str(config.get('pbclean', 'cellsize'))
    try:
        threshold = config.get('pbclean', 'threshold', None)
        threshold = str(threshold)
    except:
        threshold = ''

    # Setup
    spw = args.spw
    if args.nothreshold:
        threshold = ''
    elif threshold is None or threshold == '':
        dirty = os.path.basename(args.imagename[0] + '.image')
        dirty = os.path.join(args.dirtydir[0], dirty)
        rms = imhead(imagename=dirty, mode='get', hdkey='rms')
        threshold = '%fmJy' % (args.nrms[0]*rms*1.E3,)
    
    # Clean
    if args.continuum:
        tclean(vis=args.uvdata[0],
                imagename=args.imagename[0],
                field = field,
                spw = config.get('pbclean','spws', fallback='0,1,2,3'),
                outframe = 'LSRK',
                specmode = 'mfs',
                imsize = imsize,
                cell = cellsize,
                deconvolver = 'hogbom',
                niter = 10000,
                weighting = 'briggs', 
                robust = 0.5, 
                usemask = 'pb',
                pbmask = config.getfloat('pbclean', 'pbmask'), 
                gridder = 'standard', 
                pbcor = True,
                threshold=threshold,
                interactive = False,
                chanchunks=-1,
                parallel=True)
    else:
        tclean(vis=args.uvdata[0],
                imagename=args.imagename[0],
                field = field,
                spw = spw[0],
                outframe = 'LSRK',
                specmode = 'cube',
                imsize = imsize,
                cell = cellsize,
                deconvolver = 'hogbom',
                niter = 10000,
                weighting = 'briggs', 
                robust = 0.5, 
                usemask = 'pb',
                pbmask = config.getfloat('pbclean', 'pbmask'), 
                gridder = 'standard', 
                pbcor = True,
                threshold=threshold,
                interactive = False,
                chanchunks=-1,
                parallel=True)

    # Put RMS
    imagename = args.imagename[0] + '.image'
    box = get_box(imagename)
    put_rms(imagename, box=box)

    # Export fits
    exportfits(imagename=imagename, fitsimage=imagename + '.fits',
            overwrite=True)

if __name__=='__main__':
    main()
