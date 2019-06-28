#!casa -c
import argparse

import numpy as np

def crop_spectral_axis(chans, outfile):
    s = ia.summary()
    ind = np.where(s['axisnames']=='Frequency')[0][0]

    aux = ia.crop(outfile=outfile, axes=ind, chans=chans)
    aux.close()

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    parser.add_argument('--overlap', type=int,
            help='Size of the overlap')
    parser.add_argument('--channels', type=str, nargs='*',
            help='Total number of channels')
    parser.add_argument('--output', type=str, 
            help='Final cube file name')
    parser.add_argument('inputs', nargs='*', type=str, 
            help='Input images')
    args = parser.parse_args()
    
    if args.channels:
        assert len(args.channels)==len(args.inputs)

    # Crop images
    for i,(chans,inp) in enumerate(zip(args.channels, args.inputs)):
        ia.open(os.path.expanduser(inp))
        img_name = 'temp%i.image' % i
        aux = crop_spectral_axis(chans, img_name)
        ia.close()

        if i==0:
            filelist = img_name
        else:
            filelist += ' '+img_name 

    # Concatenate
    imagename = os.path.expanduser(args.output)+'.image'
    ia.imageconcat(outfile=imagename, infiles=filelist)
    exportfits(imagename=imagename, 
            fitsimage=imagename.replace('.image','.fits'))

if __name__=="__main__":
    try:
        main()
    finally:
        print 'Cleaning up'
        os.system('rm -rf temp*.image')
    
