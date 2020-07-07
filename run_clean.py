import argparse
import os
from ConfigParser import ConfigParser

# Local utils
aux = os.path.dirname(sys.argv[2])
sys.path.insert(0, aux)
import casa_utils as utils

def run_tclean(**kwargs):
    # Run tclean
    casalog.post('Image name: ' + kwargs['imagename'])
    casalog.post('Processing spw: ' + kwargs['spw'])
    tclean(**kwargs)

    # Compute rms
    imagename = kwargs['imagename'] + '.image'
    utils.put_rms(imagename)

    # Export FITS
    exportfits(imagename=imagename, 
            fitsimage=imagename + '.fits', 
            overwrite=True)

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--all_spws', action='store_true', 
            help='Combine all spectral windows')
    group.add_argument('--spw', type=str, nargs=1, default=None,
            help='Value for tclean spw')
    parser.add_argument('--section', nargs=1, type=str, default=['dirty'],
            help='Configuration section name')
    parser.add_argument('configfile', nargs=1, type=str,
            help='Configuration file name')
    parser.add_argument('outputdir', nargs=1, type=str,
            help='Output directory')
    parser.add_argument('uvdata', nargs='*', type=str,
            help='UV data to extract dirty images')
    args = parser.parse_args()

    # Configuration file
    config = ConfigParser({'robust':'0.5', 'deconvolver':'hogbom',
        'specmode':'cube', 'outframe':'LSRK', 'gridder':'standard',
        'interactive':'False', 'weighting':'briggs', 'niter':'0',
        'chancunks':'-1'})
    config.read(args.configfile[0])
    section = args.section[0]

    # Common arguments, add as needed
    float_keys = ['robust', 'pblimit', 'pbmask'] 
    int_keys = ['niter', 'chanchunks']
    bool_keys = ['interactive', 'parallel', 'pbcor']
    ignore_keys = ['vis', 'imagename', 'spw']
    tclean_pars = {}
    for key in tclean.parameters.keys():
        if key not in config.options(section) or key in ignore_keys:
            continue
        #Check for type:
        if key in float_keys:
            tclean_pars[key] = config.getfloat(section, key)
        elif key in int_keys:
            tclean_pars[key] = config.getint(section, key)
        elif key in bool_keys:
            tclean_pars[key] = config.getboolean(section, key)
        elif key=='imsize':
            tclean_pars[key] = map(int, config.get(section, key).split())
        else:
            tclean_pars[key] = str(config.get(section, key))
    casalog.post('tclean non-default parameters: %r' % tclean_pars)

    for ms in args.uvdata:
        # Number of spws
        nspws = len(vishead(vis=ms, mode='list')['spw_name'][0])
        casalog.post('Processing ms: %s' % ms)
        casalog.post('Number of spws in ms %s: %i' % (ms, nspws))

        # Extract properties from ms file name
        msname = os.path.basename(ms.strip('/'))
        if msname.endswith('.ms'):
            msname, ext = os.path.splitext(msname)
        elif '.ms.' in msname:
            msname = msname.replace('.ms.','.')
        else:
            pass

        # Cases:
        # Combine spws or compute just for specific spw
        if args.all_spws or 'spw' in config.options(section) or \
                args.spw is not None:
            spw = ','.join(map(str,range(nspws)))
            if args.spw:
                spw = args.spw[0]
                imagename = '{0}/{1}.spw{2}.robust{3}'.format(args.outputdir[0],
                        msname, spw, tclean_pars['robust'])
            elif 'spw' in config.options(section) and \
                    config.get(section,'spw')!=spw:
                spw = config.options(section)
                imagename = '{0}/{1}.spw{2}.robust{3}'.format(args.outputdir[0],
                        msname, spw, tclean_pars['robust'])
            else:
                imagename = '{0}/{1}.robust{2}'.format(args.outputdir[0],
                        msname, tclean_pars['robust'])
            run_tclean(vis=ms, spw=spw, imagename=imagename,
                    **tclean_pars)
        else:
            # All spectral windows one by one
            for spw in range(nspws):
                imagename = '{0}/{1}.spw{2}.robust{3}'.format(args.outputdir[0],
                        msname, spw, tclean_pars['robust'])
                run_tclean(vis=ms, spw='%i' % spw,
                        imagename=imagename, **tclean_pars)

if __name__=='__main__':
    main()
