import os
import argparse

import numpy as np

from argparse_actions import LoadTXTArray

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('inputfile', default=None, action=LoadTXTArray,
            help='Input file')
    parser.add_argument('outputfile', default=None, type=argparse.FileType('w'),
            help='Output file')
    args = parser.parse_args()

    # Center
    ceni, cenj = np.mean(args.inputfile, axis=0)

    # Distance to center
    d = np.sqrt((args.inputfile[:,0]-ceni)**2 + (args.inputfile[:,1]-cenj)**2)

    # Delete the furthest one
    ind = np.nanargmax(d)
    args.inputfile[ind] = np.nan

    # Average
    point = map(round, np.nanmean(args.inputfile, axis=0))

    # Write file
    args.outputfile.write('%i %i' % tuple(point))

if __name__=='__main__':
    main()
