#!/bin/bash
################################################################################
#              Functions for the data reduction pipeline                       #
#                                                                              #
# Change History                                                               #
# 2019/01/16  Fernando Olguin   Initial version.                               #
#             Patricio Sanhueza                                                #
#                                                                              #
################################################################################
################################################################################
################################################################################

################################################################################
# Delete directory                                                             #
################################################################################
function deldir () 
{
    logger "WARN" "Removing directory: $1"
    rm -r $1

    # If exit message is given
    if [[ $2 != "" ]]
    then
        exit $2
    fi
}

################################################################################
# Insert rms in input images headers                                           #
################################################################################
function rms_to_header () 
{
    local script="${DIR}/rms_to_header.py"
    local logfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_rms_to_header.log"
    casa --logfile $logfile -c $script $*
}

################################################################################
# Compute dirty images                                                         #
################################################################################
function get_dirty () 
{
    local script="$DIR/run_clean.py"
    local logfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_dirty.log"
    local casaflags="--logfile $logfile -c"
    local msfiles=( ${UVDATA}/${SRC0}*.ms )
    local cmd="$MPICASA $casaflags $script"
    cmd="$cmd $CONFIG $DIRTY"
    logger "DEBUG" "msfiles = ${msfiles[@]}"

    # Run casa
    if [[ ! -d $DIRTY ]]
    then
        mkdir $DIRTY
        set +e
        $cmd "${msfiles[@]}"
        if [[ $? -ge 1 ]]
        then
            logger "WARN" "Got error from CASA while calculating the dirty images"
            logger "WARN" "Check and remove (if needed) files in: $DIRTY"
            exit 0
        fi
        set -e
        logger "SEP" 2
    else
        for ms in ${msfiles[@]}
        do
            local fname="$(basename $ms)"
            fname="${fname%.*}"
            for f in ${DIRTY}/${fname}*.fits
            do
                if [[ ! -f $f ]]
                then
                    logger "Computing dirty images for ms: $ms"
                    $cmd $ms
                    logger "Done with dirty for $ms"
                else
                    logger "Skipping dirty for ms: $ms"
                fi
                break
            done
            logger "SEP" 2
        done
    fi
}

################################################################################
# Compute pb limited clean images                                              #
################################################################################
function run_pbclean () 
{
    local script="$DIR/run_clean.py"
    local logfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_pbclean.log"
    local casaflags="--logfile $logfile -c"
    local cmd="$MPICASA $casaflags $script"
    if [[ $2 -eq 0 ]]
    then
        local spw=0
        while [[ $spw -le $((NSPW-1)) ]]
        do
            if [[ $NEB -gt 1 ]]
            then
                local imgname="$(basename ${DIRTY}/${SRC}*.spw${spw}.*.image)"
                imgname="$PBCLEAN/${imgname/.image/}.${1##*.}"
            else
                local imgname="$(basename ${DIRTY}/${SRC}*.spw${spw}.*.image)"
                imgname="$PBCLEAN/${imgname/.image/}.${1##*.}"
            fi
            if [[ $REDO -eq 1 ]] || [[ ! -d "${imgname}.image" ]]
            then
                if [[ -d "${imgname}.image" ]]
                then
                    logger "Removing pb cleaned image"
                    deldir "${imgname}.*"
                fi
                local flags="--spw $spw --section pbclean"
                logger "Running pbclean"
                $cmd $flags $CONFIG $PBCLEAN $1 
                logger "Pbclean succeded"
            else
                logger "Image ${imgname}.image already exists"
            fi
            spw=$((spw + 1))
            logger "SEP" 2
        done
    elif [[ $2 -eq 1 ]]
    then
        local imgname="${PBCLEAN}/$(basename $1)"
        if [[ $REDO -eq 1 ]] || [[ ! -d "${imgname}.image" ]]
        then
            if [[ -d "${imgname}.image" ]]
            then
                logger "Removing pb cleaned image: $(basename $imgname)"
                deldir "${imgname}.*"
            fi
            logger "Running pbclean"
            local flags="--all_spw --section pbclean"
            $cmd $flags $CONFIG $PBCLEAN $1
            logger "Pbclean succeded"
        else
            logger "Image ${imgname}.image already exists"
        fi
    fi
}

################################################################################
# CLEAN cubes with YCLEAN                                                      #
################################################################################
function run_yclean () 
{
    local script="$DIR/exec_yclean.py"
    local logfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_exec_yclean.log"
    local casaflags="--logfile $logfile -c"
    local cmd="$MPICASA $casaflags $script $1 $CONFIG"
    local cleanfinal=( ${CLEAN}/${SRC0}.spw*.cube* )
    
    cd $BASE
    if [[ $REDO -eq 1 ]] || [[ ! -d $YCLEAN ]]
    then
        if [[ -d $YCLEAN ]]
        then
            logger "WARN" "Emptying YCLEAN directory: $YCLEAN"
            rm -r ${YCLEAN}/*
            rm -r *MASCARA.tc*
        else
            mkdir $YCLEAN
        fi
        if [[ -d $CLEAN ]] && [[ -e ${cleanfinal[0]} ]]
        then
            logger "WARN" "Emptying CLEAN directory: $CLEAN"
            rm -r ${CLEAN}/${SRC0}*.cube*
        elif [[ ! -d $CLEAN ]]
        then
            mkdir $CLEAN
        fi
        logger "Running YCLEAN"
        $cmd
        logger "YCLEAN succeded"
    else
        if [[ $REDO -eq 0 ]] 
        then
            test -e ${cleanfinal[0]} && logger "YCLEAN already ran" || $cmd
        else
            logger "YCLEAN already ran"
        fi
    fi
    cd -
}

################################################################################
# Get peak spectrum                                                            #
################################################################################
function get_spectra () 
{
    local script="$DIR/extract_spectra.py"
    if [[ $METHOD == "position" ]]
    then
        logger "Extracting spectrum at: ${XPOS}, ${YPOS}"
        local flags="$METHOD $1 $2 $XPOS $YPOS"
    elif [[ $METHOD == "max" ]]
    then
        logger "Extracting spectrum at maximum"
        local flags="--niter 1 --image_file ${1/.fits/.max.fits}"
        flags="$flags $METHOD --pos_file $3 $2 $1"
    fi
    python $script $flags
}

################################################################################
# Average peak position                                                        #
################################################################################
function combine_peaks () 
{
    local script="$DIR/combine_peaks.py"
    python $script $1 $2
}

################################################################################
# Run AFOLI                                                                    #
################################################################################
function get_continuum_channels () 
{
    local script="$DIR/continuum_iterative.py"
    for specfile in $*
    do
        local plotname="${specfile/dirty/plots}"
        local flags="--table ${BASE}/goco_${METHOD}_continuum.dat"
        flags="$flags --tableinfo $(basename $specfile)"
        flags="$flags --plotname ${plotname/.dat/.png}"
        flags="$flags --chanfile ${specfile/.dat/.chanfile.txt}"
        flags="$flags --min_width 2" 
        flags="$flags --config $CONFIG" 
        flags="$flags --spec ${specfile} sigmaclip --sigma 3.0 1.3"
        logger "SEP" 2
        python $script $flags 
    done
}

################################################################################
# Get continuum channels                                                       #
################################################################################
function get_peak_continuum_channels () 
{
    local methodin="$METHOD"
    if [[ $METHOD == "max" ]]
    then
        # First pass
        local counter=0
        logger "Extracting spectra (1st pass)"
        for dirt in ${DIRTY}/${SRC}*.image.fits
        do
            local specbase=${dirt/.fits/}
            if [[ $counter -eq 0 ]]
            then
                # Peak positions files
                local posfile="${dirt/.fits/.max.positions.dat}"
                posfile=${posfile/.spw[0-3]./.}

                # Reset if redo
                if [[ $REDO -eq 1 ]] && [[ -f $posfile ]]
                then
                    rm -f $posfile
                elif [[ $REDO -eq 0 ]] && [[ -f $posfile ]]
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
        if [[ $REDO -eq 1 ]] || [[ ! -f $combposfile ]]
        then
            combine_peaks $posfile $combposfile
            logger "Done combining peaks"
        else
            logger "File $(basename $combposfile) already created"
        fi

        # Assign source position values
        METHOD="position"
        local positions="$(cat $combposfile)"
        counter=1
        for pos in $positions
        do
            if [[ $counter -eq 1 ]]
            then
                XPOS="$pos"
            elif [[ $counter -eq 2 ]]
            then
                YPOS="$pos"
            else
                logger "ERROR" "Counter out of bounds in: get_peak_continuum_channels"
            fi
            counter=$((counter+1))
        done
    fi
    # Second pass
    logger "Extracting spectra (2nd pass)"
    for dirt in ${DIRTY}/${SRC}*.image.fits
    do
        # Get final spectrum
        logger "SEP" 2
        logger "Extracting spectra"
        logger "Working on: $(basename $dirt)"
        specbase=${dirt/.fits/}
        get_spectra $dirt $specbase
        
        # Run AFOLI
        logger "Getting continuum channels"
        local specfiles="${specbase}.p0spec.dat"
        get_continuum_channels $specfiles
    done
    logger "Done with AFOLI"

    # Restore method
    if [[ "$methodin" != "$METHOD" ]]
    then
        METHOD="$methodin"
    fi
}

################################################################################
# Run uvcontsub on visibilities                                                #
################################################################################
function run_uvcontsub () 
{
    local script="$DIR/run_uvcontsub.py"
    local logfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_run_uvcontsub.log"
    local cmd="$CASA --logfile $logfile -c $script"
    echo "$1.contsub"
    echo $REDO
    if [[ $REDO -eq 1 ]] || [[ ! -d "$1.contsub" ]]
    then
        if [[ -d "$1.contsub" ]]
        then
            logger "Removing ${1}.contsub"
            deldir "${1}.contsub"
        fi
        logger "Running uvcontsub"
        $cmd $* && logger "uvcontsub succeded" || logger "ERROR" "uvcontsub failed"
    elif [[ -d "$1.contsub" ]]
    then
        logger "Directory ${1}.contsub already exists"
    fi
}

################################################################################
# Split continuum visibilities                                                 #
################################################################################
function split_continuum () 
{
    local script="$DIR/split_ms.py"
    local logfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_split_ms.log"
    local cmd="$CASA --logfile $logfile -c $script"
    local splitfile1="${2}.cont_avg"
    local splitfile2="${2}.allchannels_avg"
    if [[ $REDO -eq 1 ]] || [[ ! -d $splitfile1 ]]
    then
        if [[ -d $splitfile1 ]]
        then
            logger "Removing continuum split files"
            rm -r $splitfile1 $splitfile2
        fi
        logger "Splitting the ms"
        $cmd $* && logger "Splitting succeded" || logger "ERROR" "Splitting continuum failed"
    else
        logger "Files $splitfile1 and $splitfile2 already exist"
    fi
}

################################################################################
# Concatenate visibilities                                                     #
################################################################################
function concat_vis () 
{
    local script="$DIR/run_concat.py"
    local logfile="$LOGS/casa_$(date --utc +%F_%H%M%S)_run_concat.log"
    local cmd="$CASA --logfile $logfile -c $script"
    logger "Concatenating: $*"
    $cmd $* && logger "Concatenation succeded" || logger "ERROR" "Concatenation failed"
}

################################################################################
# Run continuum or line pipe                                                   #
################################################################################
function run_pipe () 
{
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
        elif [[ $ptype == "continuum" ]]
        then
            concatms="${concatms}.${2##*.}"
        else:
            logger "ERROR" "Pipe type not recognized: $ptype"
        fi
        logger "DEBUG" "setting concatms = $concatms"
        if [[ $REDO -eq 1 ]] || [[ ! -d $concatms ]]
        then
            if [[ -d $concatms ]]
            then
                logger "Removing concatenated $ptype file: $(basename $concatms)"
                deldir $concatms
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

