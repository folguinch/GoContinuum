#!/bin/bash
################################################################################
#                       BASH utilities                                         #
#                                                                              #
# BASH general functions.                                                      #
#                                                                              #
# Change History                                                               #
# 2019/01/16  Fernando Olguin   Initial version.                               #
#                                                                              #
################################################################################
################################################################################
################################################################################

#######################################
# Logging function.
# Globals:
#   LOGGERFILE
#   VERBOSE
# Arguments:
#   Logging level (DEBUG, INFO, WARN, ERROR, SEP)
#   Message or int for level SEP
#######################################
function logger() {
  # Some defintions
  local level="INFO"
  local sep1="================================================================================"
  local sep2="--------------------------------------------------------------------------------"
  local msg

  # Check if LOGGERFILE is set
  if [[ ! -v LOGGERFILE ]]; then
    local LOGGERFILE="./debug.log"
    echo "WARN: Setting LOGGERFILE=${LOGGERFILE}"
  fi

  # Check if VERBOSE level is set
  if [[ ! -v VERBOSE ]]; then
    local VERBOSE=1
    echo "WARN: Setting VERBOSE=${VERBOSE}"
  fi

  # Set the logging level
  if [[ $1 != "" ]]; then
    if [[ $1 == "DEBUG" ]] || [[ $1 == "INFO" ]] || [[ $1 == "WARN" ]] ||
        [[ $1 == "ERROR" ]] || [[ $1 == "SEP" ]]; then
      level="$1"
      shift
    fi
  fi

  # Message or searator
  if [[ $level != "SEP" ]]; then
    msg="$level: $@"
  elif [[ $1 -eq 1 ]]; then
    msg="$sep1"
  else
    msg="$sep2"
  fi

  # Initiate logger file
  if [[ ! -e $LOGGERFILE ]]; then
    touch $LOGGERFILE
  fi
  
  # Print according to the verbose level
  if [[ $VERBOSE -eq 1 ]]; then
    if [[ $level != "DEBUG" ]]; then
      # Log message
      echo "${msg}" | tee -a "${LOGGERFILE}"
      if [[ $level == "ERROR" ]]; then
        exit 1
      fi
    else
      echo "$msg" >> ${LOGGERFILE}
    fi
  elif [[ $VERBOSE -eq 2 ]]; then
    echo "${msg}" | tee -a "${LOGGERFILE}"
  fi
}

