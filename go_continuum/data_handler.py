"""Handle data for goco."""
from typing import Optional, Tuple, List, Sequence
from dataclasses import dataclass
from pathlib import Path
import json

from casaplotms import plotms
from goco_helpers.clean_tasks import (get_tclean_params, tclean_parallel,
                                      pb_clean)
from goco_helpers.config_generator import read_config
from goco_helpers.continuum import get_continuum
from goco_helpers.image_tools import pb_crop
from goco_helpers.mstools import (flag_freqs_to_channels, spws_per_eb,
                                  spws_for_names)
import casatasks as tasks

from go_continuum.afoli import afoli_iter_data
from go_continuum.environment import GoCoEnviron

CLEAN_DEFAULTS = {'deconvolver': 'hogbom',
                  'gridder': 'standard',
                  'weighting': 'briggs',
                  'robust': 0.5,
                  'outframe': 'LSRK'}

@dataclass
class DataHandler:
    """Keep track of data used during goco."""
    name: Optional[str] = None
    """Name of the data."""
    field: Optional[str] = None
    """Field name."""
    uvdata: Optional[Path] = None
    """Measurement set directory."""
    eb: Optional[int] = None
    """Execution block number of the uvdata."""
    spws: Tuple[int] = None
    """Spectral window indices."""
    #spw_stems: Dict[str, str] = field(default_factory=dict, init=False)
    #"""Dictionary relating spw with file stems."""
    #spws: InitVar[Tuple[str]] = None
    #stems: InitVar[Tuple[str]] = None

    #def __post_init__(self, spws, stems):
    #    # Fill stems
    #    if spws is not None and self.uvdata is not None:
    #        for i, spw in enumerate(spws):
    #            self.spw_stems[spw] = DataHandler.get_std_stem(self.uvdata,
    #                                                           i,
    #                                                           eb=self.eb)
    #    elif stems is not None:
    #        for i, stem in enumerate(stems):
    #            self.spw_stems[f'{i}'] = stem

    #@staticmethod
    #def get_std_stem(uvdata: 'pathlib.Path',
    #                 spw: int,
    #                 eb: Optional[int] = None,
    #                 separator: str = '.') -> str:
    #    """Generate a stem name from `uvdata` and `spw`."""
    #    if eb is not None:
    #        return separator.join([uvdata.stem, f'eb{eb}', f'spw{spw}'])
    #    else:
    #        return separator.join([uvdata.stem, f'spw{spw}'])

    def freq_flags_to_chan(self,
                           flags_list: List[List[Tuple]],
                           invert: bool = False) -> str:
        """Convert frequency flags to channels for stored uv data."""
        # Check
        if len(flags_list) != len(self.spws):
            raise ValueError(('Cannot map flags to spws: '
                              f'{len(flags_list)} {len(self.spws)}'))

        # Iterate over spws
        flags_spw = []
        for spw, flags in zip(self.spws, flags_list):
            aux = flag_freqs_to_channels(spw, flags, self.uvdata, invert=invert)
            flags_spw.append(f'{spw}:{aux}')

        return ','.join(flags_spw)

@dataclass
class DataManager:
    """Manage goco data."""
    configfile: Path
    """Configuration file name."""
    environ: GoCoEnviron
    """Environment manager."""
    log: 'logging.Logger'
    """Logging object."""
    data: Optional[List[DataHandler]] = None
    """Group data objects per EB."""
    concat_spws: Optional[List[Sequence[int]]] = None
    """The spw names of concat data."""
    config: 'configparser.ConfigParser' = None
    """Configuration parser."""
    flags: Optional[List[Tuple]] = None
    """Flagged frequency ranges for continuum."""

    def __post_init__(self):
        if self.config is None:
            self.log.info('Reading config file: %s', self.configfile)
            self.config = read_config(self.configfile)

        if self.data is None:
            self.log.info('Generating handlers')
            self.data = self._handlers_from_config()

        if self.is_concat():
            self.log.info('Setting SPWs of concat data')
            self.set_concat_spws()

    @property
    def concat_uvdata(self):
        return Path(self.config['uvdata']['concat'])

    @property
    def nspws(self):
        return len(self.concat_spws)

    def _handlers_from_config(self):
        """Initiate handlers from values in config."""
        # Some definitions
        neb = self.config['uvdata'].getint('neb', fallback=None)
        if neb is None:
            raise ValueError('Number of EBs (neb) not defined')
        original_uvdata = self.config['uvdata']['original']
        original_uvdata = list(map(Path, original_uvdata.split(',')))
        self.log.info('Will generate handlers for uvdata: %s', original_uvdata)

        # Generate the handlers
        handlers = []
        for i in range(neb):
            if neb != len(original_uvdata) and len(original_uvdata) == 1:
                uvdata = original_uvdata[0]
                spws = spws_per_eb(original_uvdata)[i+1]
            else:
                uvdata = original_uvdata[i]
                spws = spws_per_eb(uvdata)[i+1]
            handler = DataHandler(name=self.config['DEFAULT']['name'],
                                  field=self.config['DEFAULT']['field'],
                                  uvdata=uvdata,
                                  eb=i+1,
                                  spws=spws)
            handlers.append(handler)
            self.log.info('-' * 80)
            self.log.info('Data handler for: %s', handler.name)
            self.log.info('Field: %s', handler.field)
            self.log.info('EB: %i', handler.eb)
            self.log.info('SPWs: %s', handler.spws)

        return handlers

    def is_concat(self):
        """Has the concat MS been created?"""
        return self.concat_uvdata.exists()

    def set_concat_spws(self) -> None:
        """Set `concat_spws` from concat data."""
        if len(self.data) == 1:
            self.concat_spws = [[i] for i in self.data[0].spws]
        else:
            self.concat_spws = spws_for_names(self.concat_uvdata)
        self.log.info('Concat spws: %s', self.concat_spws)

    def get_imagename(self,
                      intent: str,
                      fits: bool = False,
                      uvdata: Path = None,
                      spw: Optional[int] = None,
                      eb: Optional[int] = None) -> Path:
        """Generate an image name.
        
        Args:
          intent: Environment value.
          fits: Optional; Is it a FITS image?
          uvdata: Optional; Use this uvdata for image name.
          spw: Optional; SPW of the image.
          eb: Optional; EB of the image.
        """
        # Imtype
        if fits:
            extension = '.fits'
        else:
            extension = ''

        # SPW suffix
        if spw is not None:
            suffix = f'.spw{spw}.image{extension}'
        else:
            suffix = f'.image{extension}'

        # Separate by EB?
        if uvdata is not None:
            aux = uvdata.with_suffix(suffix)
        elif eb is None:
            aux = self.concat_uvdata.with_suffix(suffix)
        else:
            aux = self.data[eb].uvdata.with_suffix(suffix)

        return self.environ[intent] / aux.name

    def get_imagenames(self,
                       intent: str,
                       fits: bool = False) -> List[Path]:
        """Generate a list of image names.
        
        Args:
          intent: Environment value.
          fits: Optional; Is it a FITS image?

        Return:
          A list with the image names.
        """
        imagenames = []
        for spw in range(self.nspws):
            imagenames.append(self.get_imagename(intent, spw=spw,
                                                 fits=fits))

        return imagenames

    def concat_data(self):
        """Concatenate data if more than 1 EB."""
        if len(self.data) > 1 and not self.is_concat():
            self.log.info('Concatenating input MSs')
            vis = [f'{data.uvdata}' for data in self.data.values()]
            tasks.concat(vis=vis, concatvis=f'{self.concat_uvdata}')
            self.set_concat_spws()

    def clean_cube(self, intent: str, spw: int, nproc: int = 5,
                   use_fits: bool = False) -> Path:
        """Clean data for requested `intent`.
        
        Args:
          intent: Type of imaging.
          spw: SPW to clean
          nproc: Optional; Number of processes.
          use_fits: Optional; Export and use image to FITS?

        Returns:
          Image file name.
        """
        # Check intent:
        if intent not in ['dirty', 'yclean', 'tclean']:
            raise NotImplementedError(f'Intent `{intent}` not recognized')

        # Get tclean parameters
        tclean_pars = get_tclean_params(self.config[intent])
        if intent == 'dirty':
            tclean_pars.update({'niter': 0})
        tclean_pars = CLEAN_DEFAULTS | tclean_pars
        spw_str = ','.join(map(str, self.concat_spws[spw]))
        tclean_pars.update({'specmode': 'cube', 'spw': spw_str})

        # Run tclean
        imagename = self.get_imagename(intent, spw=spw)
        if intent == 'yclean':
            raise NotImplementedError
        elif intent == 'dirty' and imagename.exists():
            pass
        else:
            self.log.debug('tclean parameters: %s', tclean_pars)
            tclean_parallel([self.concat_uvdata],
                            imagename.with_name(imagename.stem),
                            nproc,
                            tclean_pars,
                            log=self.log.info)

        # Convert to fits
        if use_fits:
            self.log.info('Exporting image to FITS')
            fitsimage = imagename.with_suffix('.image.fits')
            tasks.exportfits(imagename=f'{imagename}', fitsimage=f'{fitsimage}')

        # Crop data
        crop = self.config.getboolean(intent, 'crop', fallback=False)
        if crop:
            level = self.config.getfloat(intent, 'crop_level')
            pbimage = imagename.with_suffix('.pb')
            if use_fits:
                pbfits = pbimage.with_suffix('.pb.fits')
                tasks.exportfits(imagename=f'{pbimage}', fitsimage=f'{pbfits}')
                cropimage = pb_crop(fitsimage, pbfits, level)
            else:
                cropimage = pb_crop(imagename, pbimage, level)
            self.log.info('Cropped image saved to: %s', cropimage)

        return imagename

    def afoli(self,
              image_intent: str = 'dirty',
              resume: bool = False) -> None:
        """Run AFOLI."""
        # Get target images
        images = self.get_imagenames(image_intent)
        if self.config.getboolean('afoli', 'use_crop', fallback=False):
            images = [image.with_suffix('.crop.image') for image in images]
        self.flags = afoli_iter_data(images, self.config['afoli'],
                                     plot_dir=self.environ.plots, resume=resume,
                                     log=self.log.info)
        self.flags = list(self.flags.values())

    def get_continuum_vis(self,
                          pbclean: bool = False,
                          nproc: int = 5,
                          resume: bool = False) -> None:
        """Apply flags and calculate continuum."""
        # File products
        flags_file = self.concat_uvdata.with_suffix('.line_chan_flags.json')
        flags_file = self.environ.uvdata / flags_file.name
        cont_avg = self.concat_uvdata.with_suffix('.cont_avg.ms')
        cont_avg = self.environ.uvdata / cont_avg.name
        cont_all = self.concat_uvdata.with_suffix('.cont_all.ms')
        cont_all = self.environ.uvdata / cont_all.name

        # Continuum: all channels
        if cont_all.exists() and resume:
            self.log.info('Skipping all channel continuum')
        else:
            if cont_all.exists():
                self.log.warning('Deleting all channel continuum MS')
                os.system(f'rm -rf {cont_all}')
            self.log.info('Calculating all channels continum')
            get_continuum(self.concat_uvdata, cont_all,
                          config=self.config['continuum'],
                          plotdir=self.environ.plots, spw='0')

        # Continuum: flagged channels
        if cont_avg.exists() and resume:
            self.log.info('Skipping line-free continuum')
        else:
            # Files
            if cont_avg.exists():
                self.log.warning('Deleting line-free continuum MS')
                os.system(f'rm -rf {cont_avg}')
            if flags_file.is_file() and resume:
                flags = json.loads(flags_file.read_text())
            else:
                flags = []
                for data in self.data:
                    flags.append(data.freq_flags_to_chan(self.flags))
                flags = ','.join(flags)
                flags_file.write_text(json.dumps(flags, indent=4))
            
            # Get flagged continuum
            self.log.info('Calculating line-free continum')
            get_continuum(self.concat_uvdata, cont_avg,
                          config=self.config['continuum'], flags=flags,
                          plotdir=self.environ.plots, spw='0')

        # For imaging
        if pbclean:
            self.log.info('*' * 15)
            self.log.info('PB clean:')
            self.log.info('*' * 15)
            image_all = self.get_imagename('continuum_control', uvdata=cont_all)
            image_avg = self.get_imagename('continuum_control', uvdata=cont_avg)
            tclean_pars = get_tclean_params(self.config['continuum'])
            tclean_pars = CLEAN_DEFAULTS | tclean_pars
            tclean_pars['specmode'] = 'mfs'

            # All channels
            if resume and image_all.exists():
                self.log.info('Skipping all channel continuum image')
            else:
                if image_all.exists():
                    self.log.warning('Deleting all channel continuum image')
                    os.system(f"rm -rf {image_all.with_suffix('.*')}")
                imagename = image_all.parent / image_all.stem
                pb_clean(cont_all, imagename, nproc=nproc, log=self.log.info,
                         **tclean_pars)

            # Avg channels
            if image_avg.exists() and resume:
                self.log.info('Skipping line-free continuum image')
            else:
                if image_avg.exists():
                    self.log.warning('Deleting line free continuum image')
                    os.system(f"rm -rf {image_avg.with_suffix('.*')}")
                imagename = image_all.parent / image_avg.stem
                pb_clean(cont_avg, imagename, nproc=nproc, log=self.log.info,
                         **tclean_pars)

        return cont_all, cont_avg

    def get_contsub_vis(self, resume: bool = False):
        """Calculate continuum subtracted visibilities."""
        # File products
        flags_file = self.concat_uvdata.with_suffix('.fitspec.json')
        flags_file = self.environ.uvdata / flags_file.name
        contsub_vis = self.concat_uvdata.with_suffix('.contsub.ms')
        contsub_vis = self.environ.uvdata / contsub_vis.name

        # Continuum: flagged channels
        if contsub_vis.exists() and resume:
            self.log.info('Skipping continuum subtraction')
        else:
            # Files
            if contsub_vis.exists():
                self.log.warning('Deleting contsub ms')
                os.system(f'rm -rf {contsub_vis}')
            if flags_file.is_file() and resume:
                flags = json.loads(flags_file.read_text())
            else:
                flags = []
                for data in self.data:
                    flags.append(data.freq_flags_to_chan(self.flags,
                                                         invert=True))
                flags = ','.join(flags)
                flags_file.write_text(json.dumps(flags, indent=4))
            
            # Get flagged continuum
            fitorder = self.config.getint('contsub', 'fitorder', fallback=1)
            tasks.uvcontsub(vis=f'{self.concat_uvdata}',
                            outputvis=f'{contsub_vis}',
                            fitorder=fitorder,
                            fitspec=flags)

        return contsub_vis
