import os
import sys
aux = os.path.dirname(sys.argv[2])
sys.path.insert(0, aux)
import casa_utils as utils

utils.welcome()


