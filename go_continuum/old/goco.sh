#!/bin/bash
################################################################################
#                       ALMA Data reduction pipeline                           #
#                                                                              #
# Produce ALMA continuum and data cubes. This program performs continuum       #
# channel identification and performs continuum subtraction to produce the     #
# data products.                                                               #
#                                                                              #
################################################################################
################################################################################
################################################################################
# Bash options
set -eu

# Environmental
export MPICASA

# Global constants
readonly DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
readonly LOGS="logs"
readonly -a STEPS=( "DIRTY" "AFOLI" "CONTSUB" "SPLIT" "YCLEAN" "PBCLEAN" )

# Globals
declare BASE="./"
declare OPTSPEC=":hsn:b:-:"
declare METHOD="max"
declare XPOS=""
declare YPOS=""
declare -i REDO=1
declare -i VERBOSE=1
declare -i PUTRMS=0
declare -i NSPW=4
declare -i NEB=1
declare -i NPROC=5
# Default task triggers
declare -i DODIRTY=1
declare -i DOAFOLI=1
declare -i DOCONTSUB=1
declare -i DOSPLIT=1
declare -i DOYCLEAN=1
declare -i DOPBCLEAN=1
# Others
declare LOGGERFILE SRC0 SRC CONFIG DIRTY PLOTS UVDATA PBCLEAN CLEAN YCLEAN
declare option

################################################################################
################################################################################
# Functions                                                                    #
################################################################################
################################################################################
# Import functions
source ${DIR}/utils.sh
source ${DIR}/functions.sh

#######################################
# Usage function.
#######################################
function usage() {
  # Print usage and exit with error
  cat <<fin
Usage: goco [-h|--help] [-s|--silent] [--vv] [--steps] [-b|--base] [--noredo] [-n|--nproc]
    [--nspw N] [--skip STEP [STEP ...]] [--put_rms] [--pos x y] [--neb NEB] field

Parameters:
  field                 Field name

Options:
  -h, --help            Help
  -s, --silent          Set verbose=0 in pipeline.sh
  --vv                  Set verbose level to debug
  --steps               List available steps
  -b, --base            Base directory (default: ./)
  --noredo              Skip steps some steps already finished
  -n, nproc             Number of processes for CLEANing
  --nspw N              Number of spectral windows (not tested)
  --skip STEP ...       Skip given steps (see --steps)
  --neb                 Number of EBs
  --put_rms             Put rms in image headers
  --pos                 Position where to extract spectrum
  --max                 Use max to determine position of peak
fin
  exit 1
}

#######################################
# Open the help in readme file.
# Globals:
#   DIR
#######################################
function Help() {
  # Show instructions in README.md
  less ${DIR}/README.md
  exit
}

#######################################
# List the available steps and exit.
# Globals:
#   STEPS
#######################################
function list_steps () 
{
  logger ${STEPS[@]}
  exit
}

################################################################################
# Unset triggers from skip                                                     #
################################################################################
function update_triggers () 
{
    # First argument is how many arguments to skip from cmd line
    local skip=$1
    shift $skip
    
    while [[ $# -gt 0 ]]
    do
        case ${1^^} in
            DIRTY )
                logger "Unsetting ${1^^}"
                DODIRTY=0
                shift
                OPTIND=$((OPTIND+1));;
            AFOLI )
                logger "Unsetting ${1^^}"
                DOAFOLI=0
                shift
                OPTIND=$((OPTIND+1));;
            CONTSUB )
                logger "Unsetting ${1^^}"
                DOCONTSUB=0
                shift
                OPTIND=$((OPTIND+1));;
            SPLIT )
                logger "Unsetting ${1^^}"
                DOSPLIT=0
                shift
                OPTIND=$((OPTIND+1));;
            YCLEAN )
                logger "Unsetting ${1^^}"
                DOYCLEAN=0
                shift
                OPTIND=$((OPTIND+1));;
            PBCLEAN )
                logger "Unsetting ${1^^}"
                DOPBCLEAN=0
                shift
                OPTIND=$((OPTIND+1));;
            * )
                break;;
        esac
    done
}

################################################################################
# Check directories exist                                                      #
################################################################################
function check_environment () 
{
    if [[ ! -d $DIRTY ]]
    then
        if [[ $DODIRTY -eq 1 ]]
        then
            logger "Computing dirty images"
            get_dirty
        else
            logger "ERROR" "Could not find dirty directory"
        fi
    elif [[ $DODIRTY -eq 1 ]]
    then
        logger "Computing dirty images if needed"
        get_dirty
    fi
    if [[ ! -d $PLOTS ]]
    then
        logger "Creating plots directory"
        mkdir $PLOTS
    fi
    if [[ ! -d $PBCLEAN ]]
    then
        logger "Creating pbclean directory"
        mkdir $PBCLEAN
    fi
}

################################################################################
# Main                                                                         #
################################################################################
function main () 
{
    # Check that all the directories exist
    check_environment
    
    # Initial channel windows from peak
    local counter=1
    local contsubms=""
    local splitms1=""
    local splitms2=""
    local ebflag=""
    while [[ $counter -le $NEB ]]
    do
        if [[ $NEB -gt 1 ]]
        then
            SRC="${SRC0}.${counter}"
        fi
        logger "Working on source: $SRC"
        if [[ $DOAFOLI -eq 1 ]]
        then
            get_peak_continuum_channels 
        else
            logger "Skipping AFOLI"
        fi
        logger "SEP" 2

        # uv mses
        local uvdatams="${UVDATA}/${SRC}*.ms"
        local aux=( $uvdatams ) 
        if [[ ${#aux[@]} -ne 1 ]]
        then
            # Exit if there are more than 1 ms
            logger "ERROR" "More than 1 ms in ${UVDATA}"
        fi
        
        # uvcontsub
        local chanfiles="${DIRTY}/${SRC}*.chanfile.txt"
        if [[ $DOCONTSUB -eq 1 ]]
        then
            run_uvcontsub $counter $CONFIG $uvdatams $chanfiles
        else
            logger "Skipping uv contsub"
        fi
        if [ -d ${uvdatams}.contsub.selfcal ]
        then
            contsubms="${contsubms} ${uvdatams}.contsub.selfcal"
        else
            contsubms="${contsubms} ${uvdatams}.contsub"
        fi

        # Splits
        logger "SEP" 2
        if [[ $DOSPLIT -eq 1 ]]
        then
            split_continuum $counter $CONFIG $uvdatams $chanfiles
        else
            logger "Skipping split"
        fi
        if [ -d ${uvdatams}.cont_avg.selfcal ]
        then
            splitms1="${splitms1} ${uvdatams}.cont_avg.selfcal"
            splitms2="${splitms2} ${uvdatams}.allchannels_avg.selfcal"
        else
            splitms1="${splitms1} ${uvdatams}.cont_avg"
            splitms2="${splitms2} ${uvdatams}.allchannels_avg"
        fi

        #run_pbclean "${uvdatams}.contsub"
        counter=$((counter + 1))
        logger "SEP" 1
    done
    
    # For lines
    run_pipe "line" $uvdatams $contsubms 

    # For continuum
    run_pipe "continuum" $uvdatams $splitms1
    run_pipe "continuum" $uvdatams $splitms2
}

################################################################################
################################################################################
# Main program                                                                 #
################################################################################
################################################################################
# Setup logger
# Initialize logger file
if [[ ! -d $LOGS ]]; then
  mkdir $LOGS
fi
LOGGERFILE="${LOGS}/goco_debug.log"
logger "SEP" 1

# Process the input options. Add options as needed.
while getopts $OPTSPEC option; do
  if [[ $option == "-" ]]; then
    opt="$OPTARG"
    if [[ ${!OPTIND} == -* ]]; then
      OPTARG=":"
    else
      OPTARG="${!OPTIND}"
    fi
  else
    opt="$option"
  fi
  case $opt in
    h | help ) # display Help
      Help
      ;;
    s | silent ) # Decrease verbose level
      VERBOSE=0
      ;;
    vv ) # Increase verbose level
      VERBOSE=2
      logger "Previous messages written to file"
      ;;
    steps ) # Print steps and exit
      list_steps
      ;;
    b | base ) # Base directory
      BASE="$OPTARG"
      if [[ $opt == "base" ]]; then
        OPTIND=$((OPTIND+1))
      fi
      ;;
    noredo ) # Change REDO
      REDO=0
      ;;
    n | nproc ) # Number of processes for parallel
      NPROC="$OPTARG"
      if [[ $opt == "nproc" ]]; then
        OPTIND=$((OPTIND+1))
      fi
      ;;
    nspw ) # Number of spectral windows
      NSPW=$OPTARG
      logger "Number of spws: $NSPW"
      OPTIND=$((OPTIND+1))
      ;;
    skip ) # Skip given steps
      update_triggers $OPTIND $@
      ;;
    put_rms ) # Put RMS in dirty images          
      PUTRMS=1
      ;;
    pos ) # Give source position
      METHOD="position"
      XPOS=$OPTARG
      OPTIND=$((OPTIND+1))
      YPOS=${!OPTIND}
      logger "DEBUG" "Setting position to $XPOS, $YPOS"
      OPTIND=$((OPTIND+1))
      ;;
    neb ) # Number of EBs
      NEB=$OPTARG
      logger "DEBUG" "Number of EBs: $NEB"
      OPTIND=$((OPTIND+1))
      ;;
    \? ) # incorrect option
      echo "ERROR: Invalid option: -$OPTARG"
      usage
      ;;
    : ) # invalid argument
      echo "ERROR: -$OPTARG requires an argument"
      usage
      ;;
    * ) # invalid long anrguments
      echo "ERROR: Invalid option: --$opt"
      usage
      ;;
  esac
done
shift $((OPTIND-1))
SRC0=$1
logger "Source: $SRC0"

# In case someone puts the field at the beginning
if [[ $2 != "" ]] || [[ $SRC0 == "" ]]; then
  usage
fi

# Environment setup
SRC="${SRC0}"
CONFIG="${BASE}/${SRC0}.cfg"
DIRTY="${BASE}/dirty"
PLOTS="${BASE}/plots"
UVDATA="${BASE}/uvdata"
PBCLEAN="${BASE}/pbclean"
CLEAN="${BASE}/clean"
YCLEAN="${BASE}/yclean"
CASA="$(which casa)"
MPICASA="$(which mpicasa) -n $NPROC $CASA"
#MPICASA="$(which mpicasa) -n $NPROC $(which casa)"

logger "DEBUG" "$(declare -p | grep "declare -- *")"
main
echo "GOCO has ended"
