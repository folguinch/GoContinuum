"""Handle data for goco."""
from typing import Optional, Tuple, List, Sequence
from dataclasses import dataclass
from pathlib import Path

from goco_helpers.clean_tasks import get_tclean_params, tclean_parallel
from goco_helpers.config_generator import read_config
from goco_helpers.continuum import get_continuum
from goco_helpers.image_tools import pb_crop
from goco_helpers.mstools import (flag_freqs_to_channels, spws_per_eb,
                                  spws_for_names)
import casatasks as tasks

from go_continuum.afoli import afoli_iter_data
from go_continuum.environment import GoCoEnviron

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
        print('=' * 80)
        if self.config is None:
            self.log.info('Reading config file: %s', self.configfile)
            self.config = read_config(self.configfile)

        if self.data is None:
            self.log.info('Generating handlers')
            self.data = self._handlers_from_config()

        if self.is_concat():
            self.log.info('Setting SPWs of concat data')
            self.set_concat_spws()
        print('=' * 80)

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

        # Generate the handlers
        handlers = []
        for i in range(neb):
            if neb != len(original_uvdata) and len(original_uvdata) == 1:
                uvdata = original_uvdata
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
            print('-' * 80)
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
            self.concat_spws = self.data[0].spws
        else:
            self.concat_spws = spws_for_names(self.concat_uvdata)
        self.log.info('Concat spws: %s', self.concat_spws)

    def get_imagename(self,
                      intent: str,
                      uvdata: Path = None,
                      spw: Optional[int] = None,
                      eb: Optional[int] = None) -> Path:
        """Generate an image name.
        
        Args:
          intent: environment value.
          spw: optional; SPW of the image.
          eb: optional; EB of the image
        """
        # SPW suffix
        if spw is not None:
            suffix = f'.spw{spw}.image'
        else:
            suffix = '.image'

        # Separte by EB?
        if uvdata is not None:
            aux = uvdata.with_suffix(suffix)
        elif eb is None:
            aux = self.concat_uvdata.with_suffix(suffix)
        else:
            aux = self.data[eb].uvdata.with_suffix(suffix)

        return self.environ[intent] / aux.name

    def get_imagenames(self, intent: str) -> List[Path]:
        """Generate a list of image names."""
        imagenames = []
        for spw in range(self.nspws):
            imagenames.append(self.get_imagename(intent, spw=spw))

        return imagenames

    def concat_data(self):
        """Concatenate data if more than 1 EB."""
        if len(self.data) > 1 and not self.is_concat():
            self.log.info('Concatenating input MSs')
            vis = [f'{data.uvdata}' for data in self.data.values()]
            tasks.concat(vis=vis, concatvis=f'{self.concat_uvdata}')
            self.set_concat_spws()

    def clean_cube(self, intent: str, spw: int, nproc: int = 5) -> Path:
        """Clean data for requested `intent`."""
        # Get tclean parameters
        tclean_pars = get_tclean_params(self.config[intent])
        if intent == 'dirty':
            tclean_pars.update({'niter': 0})
        spw_str = ','.join(self.concat_spws[spw])
        tclean_pars.update({'specmode': 'cube', 'spw': spw_str})

        # Run tclean
        imagename = self.get_imagename('dirty', spw)
        if intent == 'yclean':
            raise NotImplementedError
        else:
            tclean_parallel(self.concat_uvdata, imagename, nproc, tclean_pars,
                            log=self.log.info)

        # Crop data
        crop = self.config.getboolean(intent, 'crop', fallback=False)
        if crop:
            level = self.config.getfloat(intent, 'crop_level')
            cropimage = pb_crop(imagename, imagename.with_suffix('.pb'), level)
            self.log.info('Cropped image saved to: %s', cropimage)

        return imagename

    def afoli(self,
              image_intent: str = 'dirty',
              resume: bool = False) -> None:
        """Run AFOLI."""
        # Get target images
        images = self.get_imagenames(image_intent)
        if self.config.getboolean('afoli', 'use_crop', falback=False):
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
        cont_avg = self.concat_uvdata.with_suffix('.cont_avg.ms')
        cont_all = self.concat_uvdata.with_suffix('.cont_all.ms')

        # Continuum: all channels
        if cont_all.exists() and resume:
            self.log.info('Skipping all channel continuum')
        else:
            if cont_all.exists():
                self.log.warning('Deleting all channel continuum ms')
                os.system(f'rm -rf {cont_all}')
            get_continuum(self.concat_uvdata, cont_all,
                          config=self.config['continuum'])

        # Continuum: flagged channels
        if cont_avg.exists() and resume:
            self.log.info('Skipping line free continuum')
        else:
            # Files
            if cont_avg.exists():
                self.log.warning('Deleting line free continuum ms')
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
            get_continuum(self.concat_uvdata, cont_avg,
                          config=self.config['continuum'], flags=flags)

        # For imaging
        if pbclean:
            image_all = self.get_imagename('continuum_control', cont_all)
            image_avg = self.get_imagename('continuum_control', cont_avg)
            tclean_pars = get_tclean_params(self.config['continuum'])

            # All channels
            if resume and image_all.exists():
                self.log.info('Skipping all channel continuum image')
            else:
                if image_all.exists():
                    self.log.warning('Deleting all channel continuum image')
                    os.system(f"rm -rf {image_all.with_suffix('.*')}")
                imagename = image_all.parent / image_all.stem
                pb_clean(cont_all, imagename, nproc=nproc, logs=self.log.info,
                         **tclean_pars)

            # Avg channels
            if image_avg.exists() and resume:
                self.log.info('Skipping line free continuum image')
            else:
                if image_avg.exists():
                    self.log.warning('Deleting line free continuum image')
                    os.system(f"rm -rf {image_avg.with_suffix('.*')}")
                imagename = image_all.parent / image_avg.stem
                pb_clean(cont_avg, imagename, nproc=nproc, logs=self.log.info,
                         **tclean_pars)
        return cont_all, cont_avg

    def get_contsub_vis(self):
        """Calculate continuum subtracted visibilities."""
        # File products
        flags_file = self.concat_uvdata.with_suffix('.fitspec.json')
        constub_vis = self.concat_uvdata.with_suffix('.contsub.ms')

        # Continuum: flagged channels
        if contsub_vis.exists() and resume:
            self.log.info('Skipping continuum subtraction')
        else:
            # Files
            if cont_avg.exists():
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
            uvcontsub(vis=f'{self.concat_uvdata}',
                      outputvis=f'{contsub_vis}',
                      fitorder=fitorder,
                      fitspec=flags)

        return constub_vis
