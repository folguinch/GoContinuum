"""Data structures to manage information."""
from typing import Optional
from dataclasses import dataclass
from pathlib import Path

@dataclass
class GoCoEnviron():
    """Structures the go-continuum environment."""
    basedir: Path = Path('./')
    """Base directory."""
    dirty: Optional[Path] = None
    """Directory for dirty images."""
    continuum_control: Optional[Path] = None
    """Directory for continuum control images."""
    cubes: Optional[Path] = None
    """Directory for data cubes."""
    auto_selfcal: Optional[Path] = None
    """Directory for auto-selfcal."""
    plots: Optional[Path] = None
    """Directory for plots."""

    def __post_init__(self):
        for name, val in self._map_names.items():
            if val is None:
                val = self.basedir / name
        self.plots.mkdir(exist_ok=True)

    def __get_item__(self, key):
        dict_form = {'dirty': self.dirty,
                     'continuum_control': self.continuum_control,
                     'cubes': self.cubes,
                     'auto_selfcal': self.auto_selfcal,
                     'plots': self.plots}
        return dict_form[key]

    def mkdir(self, name: str):
        """Make directory if needed."""
        self[name].mkdir(exist_ok=True)
