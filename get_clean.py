import os, argparse
from ConfigParser import ConfigParser

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    parser.add_argument('--all_spws', action='store_true', 
            help='Combine all spectral windows')
    parser.add_argument('--section', nargs=1, type=str, default=['dirty'],
            help='Configuration section name (default = dirty)')
    parser.add_argument('configfile', nargs=1, type=str,
            help='Configuration file name')
    parser.add_argument('outputdir', nargs=1, type=str,
            help='Output directory')
    parser.add_argument('uvdata', nargs='*', type=str,
            help='UV data to estract dirty images')
    args = parser.parse_args()

    # Configuration file
    config = ConfigParser({'robust':'0.5', 'deconvolver':'hogbom',
        'specmode':'cube', 'outframe':'LSRK', 'gridder':'standard',
        'interactive':'False', 'weighting':'briggs', 'niter':'0',
        'chancunks':'-1'})
    config.read(args.configfile[0])
    section = args.section[0]
    print args.configfile[0]

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
    #field = config.get('dirty', 'field')
    #robust = config.getfloat('dirty', 'robust')
    #imsize = map(int, config.get('dirty', 'imsize').split())
    #cellsize = str(config.get('dirty', 'cellsize'))
    casalog.post('tclean non-default parameters: %r' % tclean_pars)

    for ms in args.uvdata:
        # Number of spws
        nspws = len(vishead(vis=ms, mode='list')['spw_name'][0])
        casalog.post('Processing ms: %s' % ms)
        casalog.post('Number of spws in ms %s: %i' % (ms, nspws))

        # Extract properties from ms file name
        msname = os.path.basename(ms.strip('/'))
        msname, ext = os.path.splitext(msname)

        # Cases:
        if args.all_spws or 'spw' in config.options(section):
            spw = ','.join(map(str,range(nspws)))
            if 'spw' in config.options(section) and \
                    config.get(section,'spw')!=spw:
                spw = config.options(section)
                imagename = '{0}/{1}.spw{2}.robust{3}'.format(args.outputdir[0],
                        msname, spw, tclean_pars['robust'])
            else:
                imagename = '{0}/{1}.robust{2}'.format(args.outputdir[0],
                        msname, tclean_pars['robust'])
            casalog.post('Processing spw: %i' % spw)
            tclean(vis = ms,
                    spw = spw,
                    imagename = imagename,
                    **tclean_pars)

            imagename = imagename + '.image'
            exportfits(imagename=imagename, fitsimage=imagename + '.fits',
                    overwrite=True)
        else:
            for spw in range(nspws):
                casalog.post('Processing spw: %i' % spw)
                imagename = '{0}/{1}.spw{2}.robust{3}'.format(args.outputdir[0],
                        msname, spw, tclean_pars['robust'])
                casalog.post(imagename)
                tclean(vis = ms,
                        #field = field,
                        spw = '%i' % spw,
                        imagename = imagename,
                        **tclean_pars)
                        #imsize = imsize,
                        #cell = cellsize,
                        #specmode = 'cube', 
                        #outframe = 'LSRK', 
                        #gridder = 'standard', 
                        #pblimit = 0.2,  
                        #deconvolver = deconvolver,
                        #interactive = False,
                        #weighting = 'briggs', 
                        #robust = robust, 
                        #niter = 0,
                        #chanchunks = -1,
                        #parallel = True,
                        #threshold = '0.14mJy')

                imagename = imagename + '.image'
                exportfits(imagename=imagename, fitsimage=imagename + '.fits',
                        overwrite=True)

if __name__=='__main__':
    main()
