#!casa -c
import argparse

def get_box(imagename, size=50):
    # Get image size
    imshape = imhead(imagename=imagename, mode='get', hdkey='shape')

    # Box
    xtrc = imshape[0]/4
    ytrc = imshape[0]/2
    xblc = xtrc - size
    ytrc = ytrc - size

    return "%i,%i,%i,%i" % (xblc, ytrc, xtrc, ytrc)

def put_rms(imagename, box=''):
    # Get rms
    casalog.post('Compute rms for: ' + imagename)
    stats = imstat(imagename=imagename, box=box, stokes='I')
    if box=='':
        rms = 1.482602219*stats['medabsdevmed'][0]
    else:
        rms = stats['rms'][0]

    # Put in header
    imhead(imagename=imagename, mode='put', hdkey='rms',
            hdvalue=rms)
    casalog.post('Image rms: %f mJy/beam' % (rms*1E3,))

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter')
    parser.add_argument('--use_box', action='store_true',
            help='Use the default box ')
    parser.add_argument('images', nargs='*', type=str,
            help='Image file names')
    args = parser.parse_args()

    for imagename in args.images:
        # Box
        if args.use_box:
            box = get_box(imagename)
        else:
            box = '' 

        # Put in header
        put_rms(imagename, box=box)

        # Convert to FITS
        exportfits(imagename=imagename, fitsimage=imagename+'.fits', 
                overwrite=True)

if __name__=="__main__":
    main()
