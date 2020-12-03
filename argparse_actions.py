import os
import argparse

from astropy.io import fits
import numpy as np

def validate_files(filenames, check_is_file=True):
    try:
        validated = os.path.expanduser(filenames)
        if check_is_file and not os.path.isfile(validated):
            raise IOError('%s does not exist' % validated)
    except AttributeError:
        validated = []
        for fname in filenames:
            validated += [os.path.expanduser(fname)]
            if check_is_file and not os.path.isfile(validated[-1]):
                raise IOError('%s does not exist' % (validated[-1]))

    return validated

##### Loaders #####

class LoadTXTArray(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        array = np.loadtxt(values, dtype=float)
        setattr(namespace, self.dest, array)

class LoadFITS(argparse.Action):
    """Action for loading a FITS file with astropy"""

    def __call__(self, parser, namespace, values, option_string=None):
        values = validate_files(values)
        try:
            vals = fits.open(''+values)[0]
        except TypeError:
            vals = []
            for val in values:
                vals += [fits.open(val)[0]]
        setattr(namespace, self.dest, vals)

