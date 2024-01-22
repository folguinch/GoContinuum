"""Handle data for goco."""
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, field, InitVar

@dataclass
class DataHandler:
    """Keep track of data used during goco."""
    name: Optional[str] = None
    """Name of the data."""
    uvdata: Optional['pathlib.Path'] = None
    """Measurement set directory."""
    eb: Optional[int] = None
    """Execution block number of the uvdata."""
    stems: Dict[str, str] = field(default_factory=dict, init=False)
    """Dictionary relating spw with file stems."""
    spws: InitVar[Tuple[str]] = None
    stems: InitVar[Tuple[str]] = None

    def __post_init__(self):
        # Fill stems
        if self.spws is not None and self.uvdata is not None:
            for i, spw in enumerate(spws):
                self.stems[spw] = DataHandler.get_std_stem(self.uvdata, i,
                                                           eb=self.eb)
        elif self.stems is not None:
            for i, stem in enumerate(stems):
                self.stems[f'{i}'] = stem

    @staticmethod
    def get_std_stem(uvdata: 'pathlib.Path', spw: int,
                     eb: Optional[int] = None,
                     separator: str = '_') -> str:
        """Generate a stem name from `uvdata` and `spw`."""
        if eb is not None:
            return separator.join([uvdata.stem, f'eb{eb}', f'spw{spw}'])
        else:
            return separator.join([uvdata.stem, f'spw{spw}'])

