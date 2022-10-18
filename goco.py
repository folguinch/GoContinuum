"""
"""
from typing import List
import sys

def _check_environment():
    pass

def _prep_data():
    pass
    
def _proc():
    pass

def main(args: List) -> None:
    """Goco main program.

    Args:
      args: command line args.
    """
    pipe = [_check_environment, _prep_data, _proc]
    steps = {
        'dirty': ,
        'afoli': ,
        'applycal': ,
        'contsub': ,
        'split': ,
        'yclean': ,
        'pbclean': ,
    }

    for step in pipe:
        step(args)

if __name__ == '__main__':
    main(sys.argv[1:])
