"""Handle data for goco."""
from typing import Optional, Tuple, List, Sequence, Dict
from dataclasses import dataclass
from pathlib import Path
import json
import os

#from casaplotms import plotms
from casatasks import initweights, gaincal, applycal, rmtables
from goco_helpers.clean_tasks import (get_tclean_params, tclean_parallel,
                                      pb_clean, auto_masking)
from goco_helpers.config_generator import read_config
from goco_helpers.continuum import get_continuum
from goco_helpers.image_tools import pb_crop
from goco_helpers.json_coders import CustomObjEncoder, custom_hooks
from goco_helpers.mstools import (flag_freqs_to_channels, spws_per_eb,
                                  spws_for_names)
import astropy.units as u
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

    #@concat_uvdata.setter
    #def concat_uvdata(self, value: Path):
    #    self.config['uvdata']['concat'] = f'{value}'

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
                spws = spws_per_eb(uvdata)[1]
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
                      eb: Optional[int] = None,
                      suffix_ending: Optional[str] = None,
                      tclean_pars: Optional[Dict] = None) -> Path:
        """Generate an image name.
        
        Args:
          intent: Environment value.
          fits: Optional. Is it a FITS image?
          uvdata: Optional. Use this uvdata for image name.
          spw: Optional. SPW of the image.
          eb: Optional. EB of the image.
          suffix_ending: Optional. Append at the end of the auto suffix.
          tclean_pars: Optional. Additional parameters for naming.
        """
        # Check in config
        opt = 'image_name' if spw is None else f'image_name_spw{spw}'
        if intent in self.config and opt in self.config[intent]:
            return Path(self.config[intent][opt])

        # Imtype
        if fits:
            extension = '.fits'
        else:
            extension = ''

        # SPW suffix
        suffix = ''
        if tclean_pars is not None:
            suffix += f".{tclean_pars.get('deconvolver', 'hogbom')}"
            weighting = tclean_pars.get('weighting', 'natural')
            if weighting == 'briggs':
                suffix += f".robust{tclean_pars.get('robust', '0.5')}"
            if 'nsigma' in tclean_pars:
                suffix += f".nsigma{tclean_pars['nsigma']}"
        if suffix_ending is not None:
            suffix += suffix_ending
        if spw is not None:
            suffix += f'.spw{spw}.image{extension}'
        else:
            suffix += f'.image{extension}'

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
            imagenames.append(self.get_imagename(intent,
                                                 spw=spw,
                                                 fits=fits))

        return imagenames

    def concat_data(self):
        """Concatenate data if more than 1 EB."""
        if len(self.data) > 1 and not self.is_concat():
            self.log.info('Concatenating input MSs')
            vis = [f'{data.uvdata}' for data in self.data]
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

    def _clean_continuum(self,
                         vis: Dict[str, Path],
                         intent: str,
                         nsigma: Optional[float] = None,
                         nproc: int = 5,
                         suffix_ending: Optional[str] = None,
                         tclean_nsigma: bool = True,
                         resume: bool = False,
                         **tclean_args) -> Dict:
        # Check intent
        if intent not in ['continuum_control', 'continuum']:
            raise ValueError(f'Intent {intent} not recognized')

        # Log message
        self.log.info('*' * 15)
        if intent == 'continuum_control':
            self.log.info('Continuum control (PB mask) clean:')
        elif intent == 'continuum':
            self.log.info('Continuum auto-masking clean:')
        else:
            raise ValueError(f'Intent {intent} not recognized')
        self.log.info('*' * 15)

        # Parameters
        tclean_pars = get_tclean_params(self.config['continuum'])
        tclean_pars = CLEAN_DEFAULTS | tclean_pars | tclean_args
        tclean_pars['specmode'] = 'mfs'
        if nsigma is None:
            nsigma = self.config.getfloat('continuum', 'nsigma', fallback=3)

        # Iterate over visibilities
        image_info = {}
        for key, val in vis.items():
            # Image name
            imagename = self.get_imagename(intent, uvdata=val,
                                           tclean_pars=(tclean_pars |
                                                        {'nsigma': nsigma}),
                                           suffix_ending=suffix_ending)
            info = {'imagename': imagename}
            info_file = imagename.with_suffix('.info.json')

            # Perform clean
            if resume and imagename.exists():
                self.log.info('Skipping %s continuum image', key)
                self.log.info('Loading info file: %s', info_file)
                info.update(json.loads(info_file.read_text(), # pylint: disable=unspecified-encoding
                                       object_hook=custom_hooks))
            else:
                self.log.info('Cleaning: %s (%s)', key, val)
                if imagename.exists():
                    self.log.warning('Deleting %s continuum image', key)
                    os.system(f"rm -rf {imagename.with_suffix('.*')}")
                imagename = imagename.parent / imagename.stem
                if intent == 'continuum_control':
                    self.log.debug('Clean parameters: %s', tclean_pars)
                    info.update(pb_clean([val], imagename, nproc=nproc,
                                         nsigma=nsigma, log=self.log.info,
                                         tclean_nsigma=tclean_nsigma,
                                         **tclean_pars))
                else:
                    if 'b75' in self.config['continuum']:
                        b75 = self.config['continuum']['b75'].split()
                        b75 = float(b75[0]) * u.Unit(b75[1])
                    else:
                        b75 = None
                    self.log.debug('Clean parameters: %s', tclean_pars)
                    tclean_pars.setdefault('pbcor', True)
                    info.update(auto_masking([val], imagename, nproc=nproc,
                                             b75=b75, nsigma=nsigma,
                                             tclean_nsigma=tclean_nsigma,
                                             log=self.log.info, **tclean_pars))
                # Save info for resume
                info_file.write_text( # pylint: disable=unspecified-encoding
                    json.dumps(info, indent=4, cls=CustomObjEncoder))

            image_info[key] = info

        return image_info

    def get_continuum_vis(self,
                          pbclean: bool = False,
                          clean_cont: bool = False,
                          nproc: int = 5,
                          intents: Sequence[str] = ('average_all', 'line-free'),
                          flags_file: Optional[Path] = None,
                          resume: bool = False) -> Tuple[Path]:
        """Apply flags and calculate continuum.

        Args:
          pbclean: Optional. Clean using a PB mask?
          clean_cont: Optional. Clean using auto-masking?
          nproc: Optional. Number of parallel processes.
          intents: Optional. Types of continuum to obtain.
          flags_file: Optional. Use different file with flags.
          resume: Optional. Resume from previous attempt.

        Returns:
          The path of the averaged visibilities and line-free continuum
          visibilities.
        """
        # File products
        if flags_file is None:
            flags_file = self.concat_uvdata.with_suffix('.line_chan_flags.json')
            flags_file = self.environ.uvdata / flags_file.name

        # Continuum: all channels
        to_clean = {}
        if 'average_all' in intents:
            cont_all = self.concat_uvdata.with_suffix('.cont_all.ms')
            cont_all = self.environ.uvdata / cont_all.name
            if cont_all.exists() and resume:
                self.log.info('Skipping all channel continuum')
            else:
                if cont_all.exists():
                    self.log.warning('Deleting all channel continuum MS')
                    os.system(f'rm -rf {cont_all}')
                self.log.info('Calculating all channels continuum')
                get_continuum(self.concat_uvdata, cont_all,
                              config=self.config['continuum'],
                              plotdir=self.environ.plots, spw='0')
            to_clean['average_all'] = cont_all
        else:
            cont_all = None

        # Continuum: flagged channels
        if 'line-free' in intents:
            cont_avg = self.concat_uvdata.with_suffix('.cont_avg.ms')
            cont_avg = self.environ.uvdata / cont_avg.name
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
                self.log.info('Calculating line-free continuum')
                get_continuum(self.concat_uvdata, cont_avg,
                              config=self.config['continuum'], flags=flags,
                              plotdir=self.environ.plots, spw='0')
            to_clean['line-free'] = cont_avg
        else:
            cont_avg = None

        # For imaging
        if pbclean:
            self._clean_continuum({'average_all': cont_all,
                                   'line-free': cont_avg},
                                  'continuum_control',
                                  nproc=nproc,
                                  resume=resume)
        if clean_cont:
            self._clean_continuum({'average_all': cont_all,
                                   'line-free': cont_avg},
                                  'continuum',
                                  nproc=nproc,
                                  resume=resume)

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

@dataclass
class SelfcalDataManager(DataManager):
    """Manage self-calibration data."""
    cont_vis: Optional[Path] = None
    """Continuum visibility name."""

    def get_continuum_vis(self, resume: bool = False):
        """Obtain continuum visibilities."""
        # Flags
        flags_file = self.config.get('selfcal', 'flags_file', fallback=None)
        if flags_file is not None:
            flags_file = Path(flags_file)
            intents = ['line-free']
        else:
            intents = ['average_all']

        # Calculate visibilities
        cont_all, cont_avg = super().get_continuum_vis(intents=intents,
                                                       flags_file=flags_file,
                                                       resume=resume)

        # Set continuum visibilities
        if cont_all is not None:
            self.cont_vis = cont_all
        elif cont_avg is not None:
            self.cont_vis = cont_avg
        else:
            raise ValueError('No continuum visibilities')
        self.log.info('Working with vis file: %s', self.cont_vis)

    def clean_continuum(self,
                        nsigma: Optional[float] = None,
                        nproc: int = 1,
                        suffix_ending: Optional[str] = None,
                        tclean_nsigma: bool = False,
                        resume: bool = False,
                        **tclean_args) -> Dict:
        """Clean stored continuum visibilities.

        Args:
          nsigma: Optional. Number of rms levels to clean to.
          nproc: Optional. Number of parallel processes.
          suffix_ending: Optional. Additional ending for images.
          tclean_nsigma: Optional. Use `tclean` built-in nsigma?
          resume: Optional. Skip if files found?
          tclean_args: Optional. Additional tclean parameters.

        Returns:
          A dictionary with image files and thresholds.
        """
        info = self._clean_continuum({'cont_vis': self.cont_vis},
                                     'continuum',
                                     nproc=nproc,
                                     nsigma=nsigma,
                                     suffix_ending=suffix_ending,
                                     tclean_nsigma=tclean_nsigma,
                                     resume=resume,
                                     **tclean_args)

        return info['cont_vis']

    def init_weights(self):
        """Initialize weights."""
        initweights(vis=f'{self.concat_uvdata}', wtmode='weight', dowtsp=True)

    def self_calibrate(self,
                       caltable: Path,
                       solint: str,
                       iteration: int = 0,
                       calmode: str = 'p',
                       resume: bool = False):
        """Calculate gain table and apply it.

        If resume is `True`, then only the `gaincal` calculation is skipped.
        The table will be applied either way, so the continuum visibilities
        should be deleted before running again.

        The iteration number is used to define parameters specific for certain
        runs: `combine` and `gaintype`.

        Args:
          caltable: Calibration table file name.
          solint: Solution interval.
          iteration: Otional. Iteration number.
          calmode: Optional. Calibration mode.
          resume: Optional. Skip cal table calculation?
        """
        # Gaincal parameters
        gaintype = self.config.get('selfcal', 'gaintype', fallback='G')
        if ',' in gaintype:
            gaintype = gaintype.split(',')[iteration].strip()
        cal_params = {'field': self.config['selfcal']['field'],
                      'refant': self.config['selfcal']['refant'],
                      'gaintype': gaintype}
        combine = self.config.get('selfcal', 'combine', fallback=None)
        if combine is not None and ';' in combine:
            combine = combine.split(';')[iteration].strip()
            if 'none' in combine:
                combine = None
        if combine is not None:
            cal_params['combine'] = combine

        # Gain table
        if caltable.exists() and resume:
            self.log.info('Skipping caltable calculation')
        else:
            if caltable.exists():
                self.log.info('Removing calibration table')
                rmtables(f'{caltable}')
            self.log.info('Other gaincal parameters: %s', cal_params)
            gaincal(vis=f'{self.cont_vis}',
                    caltable=f'{caltable}',
                    calmode=calmode,
                    solint=solint,
                    **cal_params)

        # Applycal
        if 'spw' in cal_params.get('combine', ''):
            raise NotImplementedError('SPW mapping not implemented yet')
        applymode = self.config.get('selfcal', 'applymode', fallback='calonly')
        self.log.info('Apply mode: %s', applymode)
        applycal(vis=f'{self.cont_vis}',
                 gaintable=[f'{caltable}'],
                 applymode=applymode,
                 interp='linear')
