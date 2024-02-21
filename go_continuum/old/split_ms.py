import argparse
import os
from ConfigParser import ConfigParser

# Local utils
aux = os.path.dirname(sys.argv[2])
sys.path.insert(0, aux)
import casa_utils as utils

def split_ms(args):
    # Convenience variables
    config = args.config
    section = args.section[0]
    
    # Define width and validate
    if args.widths_avg is not None:
        width = map(int, args.widths_avg.split(','))
    elif 'width' in config.options(section):
        width = map(int, config.get(section,'width').split())
    else:
        casalog.post('width parameter is not defined', 'SEVERE')
        raise ValueError('width parameter is not defined')
    lenspw = len(config.get(section,'spws').split(','))
    if len(width)!=lenspw:
        if len(width)==1:
            casalog.post('Using the same width for all spws', 'WARN')
            width = width*lenspws
        else:
            msg = 'The number of spws does not match the number of widths'
            casalog.post(msg, 'SEVERE')
            raise ValueError(msg)
    
    # Split flagged
    flagmanager(vis=args.uvdata[0], mode='save', versionname='before_cont_flags')
    initweights(vis=args.uvdata[0], wtmode='weight', dowtsp=True)
    flagdata(vis=args.uvdata[0], mode='manual', spw=args.fitspw, flagbackup=False)
    outputvis = args.uvdata[0]+'.cont_avg'
    args.outvis = outputvis
    if os.path.isdir(outputvis):
        casalog.post('Deleting %s' % outputvis, 'WARN')
        os.system('rm -rf %s' % outputvis)
    split(vis=args.uvdata[0],
            spw=config.get(section,'spws'),
            outputvis=outputvis,
            width=width,
            datacolumn=config.get(section,'datacolumn'))
    flagmanager(vis=args.uvdata[0], mode='restore', versionname='before_cont_flags')
    utils._run_cal(args)
    
    # Split unflagged
    outputvis = args.uvdata[0]+'.allchannels_avg'
    args.outvis = outputvis
    if os.path.isdir(outputvis):
        casalog.post('Deleting %s' % outputvis, 'WARN')
        os.system('rm -rf %s' % outputvis)
    split(vis=args.uvdata[0],
            spw=config.get(section,'spws'),
            outputvis=outputvis, 
            width=width,
            datacolumn=config.get(section,'datacolumn'))
    utils._run_cal(args)

def main():
    # Configuration file default values
    config_default = {'spws':'0,1,2,3', 'datacolumn':'corrected', 
            'calwt':'false', 'interp':'linear', 'flagbackup':'false', 
            'spwmap':''}

    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    #parser.add_argument('--concatvis', nargs=1, type=str, 
    #        help='Concatenated ms name')
    parser.add_argument('--section', nargs=1, type=str, default=['split_ms'],
            help='Section in config file')
    parser.add_argument('--eb', nargs=1, type=int, default=[None],
            help='EB number')
    parser.add_argument('--widths_avg', default=None, type=str,
            help='Channel width average (coma separated)')
    parser.add_argument('configfile', nargs=1, action=utils.NormalizePath,
            help='Configuration file name')
    parser.add_argument('uvdata', nargs=1, action=utils.NormalizePath,
            help='uv data ms')
    parser.add_argument('chans', nargs='*', action=utils.NormalizePath,
            help='Channel list files')
    parser.set_defaults(pipe=[utils.verify_args, utils.load_config,
        utils.load_chan_list, split_ms],
            config=config_default, calsect='contapplycal', outvis=None,
            fitspw=None)
    args = parser.parse_args()

    # Run steps in pipe
    for step in args.pipe:
        step(args)

if __name__=="__main__":
    main()
