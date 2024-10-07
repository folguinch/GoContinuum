#!casa -c
import argparse
import os
from ConfigParser import ConfigParser

# Local utils
aux = os.path.dirname(sys.argv[2])
sys.path.insert(0, aux)
import casa_utils as utils

"""Perform uvcontsub and apply calibration table if required

The input for applycal can be configured in the `lineapplycal` (default)
section of the configuration file. For observations with more than one EB, the 
command line argument `eb` can be used. To specify the table for each EB, 2 
methods are available:
    1. Define a section `lineapplycal<i>` with `i` the EB number
    2. Comma separated values for each EB. If multiple table are used per EB,
    space is used per EB, e.g `caltable = cal1EB1 cal2EB1, cal1EB2 ...`. With
    the exception of the `interp` parameter, which  uses semi-colon separated
    values.
"""

def run_uvcontsub(args):
    args.outvis = args.uvdata[0]+'.contsub'
    if args.noredo and os.path.isdir(args.outvis):
        casalog.post('Skipping uvcontsub')
    else:
        uvcontsub(vis=args.uvdata[0], fitspw=args.fitspw, want_cont=False, 
                combine='spw', excludechans=True, fitorder=1)

def main():
    # Configuration file default values
    config_default = {'calwt':'false', 'interp':'linear', 'flagbackup':'false', 
            'spwmap':''}

    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    parser.add_argument('--section', nargs=1, type=str, default=['uvcontsub'],
            help='Section in config file')
    parser.add_argument('--eb', nargs=1, type=int, default=[None],
            help='EB number')
    parser.add_argument('--noredo', action='store_true',
            help='Do not redo if files exists')
    parser.add_argument('configfile', nargs=1, action=utils.NormalizePath, 
            help='Configuration file')
    parser.add_argument('uvdata', nargs=1, action=utils.NormalizePath,
            help='uv data ms')
    parser.add_argument('chans', nargs='*', action=utils.NormalizePath, 
            help='Channel list files')
    parser.set_defaults(pipe=[utils.verify_args, utils.load_config,
        utils.load_chan_list, run_uvcontsub, utils._run_cal],
            config=config_default, calsect='lineapplycal', outvis=None,
            fitspw=None)
    args = parser.parse_args()

    # Run steps in pipe
    for step in args.pipe:
        step(args)

if __name__=="__main__":
    main()
