#!casa -c
import argparse

# Local utils
aux = os.path.dirname(sys.argv[2])
sys.path.insert(0, aux)
import casa_utils as utils

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
    parser.add_argument('--box', type=int, nargs=4, default=None,
            help='Box for cropping the image')
    parser.add_argument('inputs', nargs='*', type=str, 
            help='Input images')
    args = parser.parse_args()
    
    utils.join_cubes(args.inputs, args.output, args.channels, box=args.box)

if __name__=="__main__":
    try:
        main()
    finally:
        print 'Cleaning up'
        os.system('rm -rf temp*.image')
    
