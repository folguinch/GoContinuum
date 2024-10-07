"""Data structures to manage information."""
from typing import Optional
from dataclasses import dataclass, asdict, InitVar
from pathlib import Path

@dataclass
class GoCoEnviron():
    """Structures the go-continuum environment."""
    basedir: Path = Path('./')
    """Base directory."""
    uvdata: Optional[Path] = None
    """Directory where the generated MSs will be."""
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
    check_env: InitVar[bool] = False
    """Check that directories exist."""

    def __post_init__(self, check_env):
        if self.uvdata is None:
            self.uvdata = self.basedir / 'uvdata'
        if self.dirty is None:
            self.dirty = self.basedir / 'dirty'
        if self.continuum_control is None:
            self.continuum_control = self.basedir / 'continuum_control'
        if self.cubes is None:
            self.cubes = self.basedir / 'cubes'
        if self.auto_selfcal is None:
            self.auto_selfcal = self.basedir / 'auto_selfcal'
        if self.plots is None:
            self.plots = self.basedir / 'plots'
            #self.plots.mkdir(exist_ok=True)
        if check_env:
            self.do_check_env()

    def __getitem__(self, key):
        #dict_form = {'dirty': self.dirty,
        #             'continuum_control': self.continuum_control,
        #             'cubes': self.cubes,
        #             'auto_selfcal': self.auto_selfcal,
        #             'plots': self.plots}
        dict_form = asdict(self)
        return dict_form[key]

    def do_check_env(self):
        """Check that all directories exist."""
        for path in asdict(self).values():
            path.mkdir(exist_ok=True)

    def mkdir(self, name: str):
        """Make directory if needed."""
        self[name].mkdir(exist_ok=True)
