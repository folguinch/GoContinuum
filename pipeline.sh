#!/bin/bash
###############################################################################
############################ The complete pipeline ############################
###############################################################################
# Created by: Fernando Olguin
#             Patricio Sanhueza
#
#

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
STEPS=( "DIRTY" "AFOLI" "CONTSUB" "SPLIT" "YCLEAN" "PBCLEAN" )

# Functions
function usage () {
cat <<fin
Usage: pipeline.sh [[-h|--help]] [[--noredo]] [[-s|--silent]] [[--vv]] [[--dirty]] [[--skip] step ...] [[--put_rms]] [[--pos] x y] [[--max]] field

Parameters:
  field                 Field name

Options:
  -h, --help            Help
  --neb                 Number of EBs
  --noredo              Skip steps some steps already finished
  -s, --silent          Set verbose=0 in pipeline.sh
  --vv                  Set verbose level to debug
  --dirty               Compute dirty images if dirty directory does not exist
  --skip                Skip given steps (see --steps)
  --steps               List available steps
  --put_rms             Put rms in image headers
  --pos                 Position where to extract spectrum
  --max                 Use max to determine position of peak
fin
}

function list_steps () {
    logger ${STEPS[@]}
}

function update_triggers () {
    SKIP=0
    while [[ $# -gt 0 ]]
    do
        case ${1^^} in
            DIRTY )
                logger "Unsetting ${1^^}"
                DODIRTY=0
                shift
                SKIP=$((SKIP+1))
                ;;
            AFOLI )
                logger "Unsetting ${1^^}"
                DOAFOLI=0
                shift
                SKIP=$((SKIP+1))
                ;;
            CONTSUB )
                logger "Unsetting ${1^^}"
                DOCONTSUB=0
                shift
                SKIP=$((SKIP+1))
                ;;
            SPLIT )
                logger "Unsetting ${1^^}"
                DOSPLIT=0
                shift
                SKIP=$((SKIP+1))
                ;;
            YCLEAN )
                logger "Unsetting ${1^^}"
                DOYCLEAN=0
                shift
                SKIP=$((SKIP+1))
                ;;
            PBCLEAN )
                logger "Unsetting ${1^^}"
                DOPBCLEAN=0
                shift
                SKIP=$((SKIP+1))
                ;;
            * )
                break
                ;;
        esac
    done
    logger "DEBUG" "Skipping $SKIP options"
}

function logger (){
    local level="INFO"
    local sep1="================================================================================"
    local sep2="--------------------------------------------------------------------------------"
    if [[ $1 != "" ]]
    then
        if [[ $1 == "DEBUG" ]] || [[ $1 == "INFO" ]] || [[ $1 == "WARN" ]] || 
            [[ $1 == "ERROR" ]] || [[ $1 == "SEP" ]]
        then
            level="$1"
            shift
        fi
    fi

    if [[ $level != "SEP" ]]
    then
        local msg="$level: $@"
    elif [[ $1 -eq 1 ]]
    then
        local msg="$sep1"
    else
        local msg="$sep2"
    fi

    if [[ $VERBOSE -eq 1 ]]
    then
        if [[ $level != "DEBUG" ]]
        then
            echo "$msg" | tee -a "${LOGGERFILE}"
            if [[ $level == "ERROR" ]]
            then
                exit 0
            fi
        else
            echo "$msg" >> ${LOGGERFILE}
        fi
    elif [[ $VERBOSE -eq 2 ]]
    then
        echo "$msg" | tee -a "${LOGGERFILE}"
    fi
}

function check_environment () {
    if [[ ! -d $Dirty ]]
    then
        if [[ DODIRTY -eq 1 ]]
        then
            logger "Computing dirty images"
            get_dirty
        else
            logger "ERROR" "Could not find dirty directory"
        fi
    elif [[ DODIRTY -eq 1 ]]
    then
        logger "Computing dirty images if needed"
        get_dirty
    fi
    if [[ ! -d $Plots ]]
    then
        logger "Creating plots directory"
        mkdir $Plots
    fi
    if [[ ! -d $PBclean ]]
    then
        logger "Creating pbclean directory"
        mkdir $PBclean
    fi
}

function rms_to_header () {
    local script="$DIR/rms_to_header.py"
    casa -c $script $*
}

function deldir () {
    logger "WARN" "Removing directory: $1"
    rm -rf $1

    if [[ $2 != "" ]]
    then
        exit $2
    fi
}

function get_dirty () {
    local script="$DIR/get_dirty.py"
    local casalogfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_dirty.log"
    local casaflags="--logfile $casalogfile -c"
    local msfiles=( ${UVdata}/${SRC0}*.ms )
    local config="${BASE}${SRC0}.cfg"
    local casa="/home/myso/opt/casa-release-5.5.0-149.el7/bin/casa"
    local mpicasa="/home/myso/opt/casa-release-5.5.0-149.el7/bin/mpicasa"
    logger "DEBUG" "msfiles = ${msfiles[@]}"

    # Run casa
    if [[ ! -d $Dirty ]]
    then
        mkdir $Dirty
        set +e
        $mpicasa -n 4 $casa $casaflags $script $config $Dirty "${msfiles[@]}"
        if [[ $? -ge 1 ]]
        then
            logger "WARN" "Got error from CASA while calculating the dirty images"
            logger "WARN" "Check and remove (if needed) files in: $Dirty"
            exit 0
        fi
        set -e
        logger "SEP" 2
    else
        for ms in ${msfiles[@]}
        do
            local fname="$(basename $ms)"
            #local ext="${fname##*.}"
            fname="${fname%.*}"
            for f in ${Dirty}/${fname}*.fits
            do
                if [[ ! -f $f ]]
                then
                    logger "Computing dirty images for ms: $ms"
                    $mpicasa -n 3 $casa $casaflags $script $config $Dirty $ms
                else
                    logger "Skipping dirty for ms: $ms"
                fi
                break
            done
            logger "SEP" 2
        done
    fi
}

function get_spectra () {
    local script="$DIR/extract_spectra.py"
    if [[ $Method == "position" ]]
    then
        logger "Extracting spectrum at: ${Xpos}, ${Ypos}"
        local flags="$Method $1 $2 $Xpos $Ypos"
    elif [[ $Method == "max" ]]
    then
        logger "Extracting spectrum at maximum"
        local flags="--niter 1 --image_file ${1/.fits/.max.fits}"
        flags="$flags $Method --pos_file $3 $2 $1"
    fi
    python $script $flags
}

function combine_peaks () {
    local script="$DIR/combine_peaks.py"
    python $script $1 $2
}

function get_continuum_channels () {
    local script="$DIR/continuum_iterative.py"
    for specfile in $*
    do
        local plotname="${specfile/dirty/plots}"
        local flags="--table ${BASE}pipeline_${method}_continuum.dat"
        flags="$flags --tableinfo $(basename $specfile)"
        flags="$flags --plotname ${plotname/.dat/.png}"
        flags="$flags --chanfile ${specfile/.dat/.chanfile.txt}"
        flags="$flags --min_width 2" 
        flags="$flags --config ${BASE}${SRC0}.cfg" 
        flags="$flags --spec ${specfile} sigmaclip --sigma 3.0 1.3"
        logger "SEP" 2
        python $script $flags 
    done
}

function get_peak_continuum_channels () {
    local methodin="$Method"
    if [[ $Method == "max" ]]
    then
        # First pass
        local counter=0
        logger "Extracting spectra (1st pass)"
        for dirt in ${Dirty}/${SRC}*.image.fits
        do
            local specbase=${dirt/.fits/}
            if [[ $counter -eq 0 ]]
            then
                local posfile="${dirt/.fits/.max.positions.dat}"
                posfile=${posfile/.spw[0-3]./.}

                # Reset if redo
                if [[ $Redo -eq 1 ]] && [[ -f $posfile ]]
                then
                    rm -f $posfile
                elif [[ $Redo -eq 0 ]] && [[ -f $posfile ]]
                then
                    logger "File $(basename $posfile) already created"
                    break
                fi
                counter=1
            fi
            # Find position of maxima
            logger "SEP" 2
            logger "Working on: $(basename $dirt)"
            get_spectra $dirt $specbase $posfile
        done
        logger "Extracting spectra done"

        # Combine peaks
        logger "SEP" 2
        logger "Combining peaks"
        local combposfile="${posfile/.dat/.combined.dat}"
        if [[ $Redo -eq 1 ]] || [[ ! -f $combposfile ]]
        then
            combine_peaks $posfile $combposfile
            logger "Done combining peaks"
        else
            logger "File $(basename $combposfile) already created"
        fi

        # Assign source position values
        Method="position"
        local positions="$(cat $combposfile)"
        counter=1
        for pos in $positions
        do
            if [[ $counter -eq 1 ]]
            then
                Xpos="$pos"
            else
                Ypos="$pos"
            fi
            counter=2
        done
    fi
    # Second pass
    logger "Extracting spectra (2nd pass)"
    for dirt in ${Dirty}/${SRC}*.image.fits
    do
        logger "SEP" 2
        logger "Extracting spectra"
        logger "Working on: $(basename $dirt)"
        specbase=${dirt/.fits/}
        get_spectra $dirt $specbase
        
        logger "Getting continuum channels"
        local specfiles="${specbase}.p0spec.dat"
        get_continuum_channels $specfiles
    done
    logger "Done with AFOLI"

    # Restore method
    if [[ "$methodin" != "$Method" ]]
    then
        Method="$methodin"
    fi
}

function run_uvcontsub () {
    local script="$DIR/run_uvcontsub.py"
    local casalogfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_run_uvcontsub.log"
    if [[ $Redo -eq 1 ]] || [[ ! -d "$1.contsub" ]]
    then
        if [[ -d "$1.contsub" ]]
        then
            logger "Removing ${1}.contsub"
            rm -rf "${1}.contsub"
        fi
        logger "Running uvcontsub"
        casa --logfile $casalogfile -c $script $*
        logger "uvcontsub succeded"
    elif [[ -d "$1.contsub" ]]
    then
        logger "Directory ${1}.contsub already exists"
    fi
}

function run_pbclean () {
    local script="$DIR/pbclean.py"
    local casalogfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_pbclean.log"
    local casaflags="--logfile $casalogfile -c"
    local config="${BASE}${SRC0}.cfg"
    if [[ $2 -eq 0 ]]
    then
        local spw=0
        while [[ $spw -le 3 ]]
        do
            if [[ $NEB -gt 1 ]]
            then
                local imgname="$(basename ${Dirty}/${SRC}*.spw${spw}.*.image)"
                imgname="$PBclean/${imgname/.image/}.${1##*.}"
            else
                local imgname="$(basename ${Dirty}/${SRC}*.spw${spw}.*.image)"
                imgname="$PBclean/${imgname/.image/}.${1##*.}"
            fi
            if [[ $Redo -eq 1 ]] || [[ ! -d "${imgname}.image" ]]
            then
                if [[ -d "${imgname}.image" ]]
                then
                    logger "Removing pb cleaned image: $(basename $imgname)"
                    rm -rf "${imgname}.*"
                fi
                logger "Runnung pbclean"
                mpicasa -n 5 $(which casa) $casaflags $script --nothreshold --spw $spw $1 $imgname $config
                logger "Pbclean succeded"
            else
                logger "Image ${imgname}.image already exists"
            fi
            spw=$((spw + 1))
            logger "SEP" 2
        done
    elif [[ $2 -eq 1 ]]
    then
        local imgname="${PBclean}/$(basename $1)"
        if [[ $Redo -eq 1 ]] || [[ ! -d "${imgname}.image" ]]
        then
            if [[ -d "${imgname}.image" ]]
            then
                logger "Removing pb cleaned image: $(basename $imgname)"
                rm -rf "${imgname}.*"
            fi
            logger "Runnung pbclean"
            mpicasa -n 5 $(which casa) $casaflags $script --nothreshold --continuum $1 $imgname $config
            logger "Pbclean succeded"
        else
            logger "Image ${imgname}.image already exists"
        fi
    fi
}

function run_yclean () {
    local script="$DIR/exec_yclean.py"
    local config="${BASE}${SRC0}.cfg"
    local casalogfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_exec_yclean.log"
    
    cd $BASE
    if [[ $Redo -eq 1 ]] || [[ ! -d $YCLEAN ]]
    then
        if [[ -d $YCLEAN ]]
        then
            logger "Emptying YCLEAN directory: $YCLEAN"
            rm -rf ${YCLEAN}/*
            rm -rf *MASCARA.tc*
        else
            mkdir $YCLEAN
        fi
        if [[ -d $CLEAN ]]
        then
            logger "Emptying CLEAN directory: $CLEAN"
            rm -rf ${CLEAN}/*.cube*
        else
            mkdir $CLEAN
        fi
        logger "Running YCLEAN"
        mpicasa -n 3 $(which casa) --logfile $casalogfile -c $script $1 $config
        logger "YCLEAN succeded"
    else
        logger "YCLEAN already ran"
    fi
    cd -
}

function split_continuum () {
    local script="$DIR/split_ms.py"
    local casalogfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_split_ms.log"
    local splitfile1="${1}.cont_avg"
    local splitfile2="${1}.allchannels_avg"
    if [[ $Redo -eq 1 ]] || [[ ! -d $splitfile1 ]]
    then
        if [[ -d $splitfile1 ]]
        then
            logger "Removing continuum split files"
            rm -rf $splitfile1 $splitfile2
        fi
        logger "Splitting the ms"
        casa --logfile $casalogfile -c $script $*
        logger "Splitting succeded"
    else
        logger "Files $splitfile1 and $splitfile2 already exist"
    fi
}

function concat_vis () {
    local script="$DIR/run_concat.py"
    local casalogfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_run_concat.log"
    logger "Concatenating: $*"
    casa --logfile $casalogfile -c $script $*
    logger "Concatenation succeded"
}

function run_pipe () {
    local ptype="$1"
    logger "Running $ptype pipe"
    shift
    local uvdatams="$1"
    logger "DEBUG" "uvdatams = $uvdatams"
    shift
    local concatms="$@"
    logger "DEBUG" "concatms = $concatms"
    if [[ $NEB -gt 1 ]]
    then
        concatms="${uvdatams/${SRC0}.[0-9]./${SRC0}.}"
        if [[ $ptype == "line" ]] 
        then
            concatms="${concatms}.contsub"
        else
            concatms="${concatms}.${2##*.}"
        fi
        logger "DEBUG" "setting concatms = $concatms"
        if [[ $Redo -eq 1 ]] || [[ ! -d $concatms ]]
        then
            if [[ -d $concatms ]]
            then
                logger "Removing concatenated $ptype file: $(basename $concatms)"
                rm -rf $concatms
            fi
            concat_vis $concatms $@
        else
            logger "File $(basename $concatms) already created"
        fi
        echo "SEP" 2
    fi

    logger "DEBUG" "final concatms = $concatms"
    if [[ $ptype == "line" ]] && [[ $DOYCLEAN -eq 1 ]]
    then
        # YCLEAN HERE
        run_yclean $concatms
    elif [[ $ptype == "continuum" ]] && [[ $DOPBCLEAN -eq 1 ]]
    then
        # Run pb clean
        run_pbclean $concatms 1
    elif [[ $DOYCLEAN -eq 0 ]] || [[ $DOPBCLEAN -eq 0 ]]
    then
        logger "Skipping $ptype pipe"
    else
        logger "ERROR" "Pipe type not recognized: $ptype"
    fi
}

function main () {
    # Check that all the directories exist
    check_environment

    # Put the rms in header
    if [[ $PutRms -eq 1 ]]
    then
        rms_to_header ${Dirty}/${SRC}*.image
    fi
    
    # Initial channel windows from peak
    local counter=1
    local contsubms=""
    local splitms1=""
    local splitms2=""
    while [[ $counter -le $NEB ]]
    do
        if [[ $NEB -gt 1 ]]
        then
            SRC="${SRC0}.${counter}"
        else
            SRC="${SRC0}"
        fi
        logger "Working on source: $SRC"
        get_peak_continuum_channels 
        logger "SEP" 2
        
        # uvcontsub
        local uvdatams="${UVdata}/${SRC}*.ms"
        local chanfiles="${Dirty}/${SRC}*.chanfile.txt"
        run_uvcontsub $uvdatams $chanfiles
        contsubms="${contsubms} ${uvdatams}.contsub"

        # Splits
        logger "SEP" 2
        split_continuum "${BASE}${SRC0}.cfg" $uvdatams $chanfiles
        splitms1="${splitms1} ${uvdatams}.cont_avg"
        splitms2="${splitms2} ${uvdatams}.allchannels_avg"

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

# Command line options
BASE="./"
PutRms=0
Redo=1
Method="max"
Xpos=""
Ypos=""
NEB=1
SKIP=1
VERBOSE=1
# Task triggers
DODIRTY=0
DOAFOLI=1
DCONTSUB=1
DOSPLIT=1
DOYCLEAN=1
DOPBCLEAN=1

# Initialize logger file
LOGS="logs"
if [[ ! -d $LOGS ]]
then
    mkdir $LOGS
fi
LOGGERFILE="$LOGS/pipeline_debug.log"
logger "SEP" 1

while [[ "$1" != "" ]]; do
    logger "DEBUG" "Processing cmd option: $1"
    case $1 in
        -h | --help )           
            usage
            exit 1
            ;;
        --noredo )              
            Redo=0
            shift
            ;;
        -s | --silent )
            VERBOSE=0
            shift
            ;;
        --vv )
            VERBOSE=2
            logger "Previous messages written to file"
            shift
            ;;
        --dirty )               
            DODIRTY=1
            shift
            ;;
        --skip )                
            shift
            update_triggers $@
            shift $SKIP
            SKIP=1
            ;;
        --steps )               
            list_steps
            exit 1
            ;;
        --put_rms )             
            PutRms=1
            shift
            ;;
        --pos )                 
            Method="position"
            shift
            Xpos=$1
            shift
            Ypos=$1
            shift
            ;;
        --max )                 
            Method="max"
            shift
            ;;
        --neb )                 
            shift
            NEB=$1
            shift
            ;;
        * )                     
            SRC0=$1
            shift
            break
            ;;
    esac
done

# Environment setup
if [[ $BASE != "" ]]
then
    BASE="${BASE}/"
fi
Dirty="${BASE}dirty"
Plots="${BASE}plots"
UVdata="${BASE}final_uvdata"
PBclean="${BASE}pbclean"
CLEAN="${BASE}clean"
YCLEAN="${BASE}yclean"

main
echo "QMD"
