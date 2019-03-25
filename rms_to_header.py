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
    parser.add_argument('images', nargs='*', type=str,
            help='Image file names')
    args = parser.parse_args()

    for imagename in args.images:
        # Box
        box = get_box(imagename)

        # Put in header
        put_rms(imagename, box=box)

        # Convert to FITS
        exportfits(imagename=imagename, fitsimage=imagename+'.fits', 
                overwrite=True)

if __name__=="__main__":
    main()
