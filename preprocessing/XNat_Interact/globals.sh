#!/bin/bash

# Global variables defined here:

USER=$(whoami)

case "$USER" in
  aa2842)
    USER_ID=aa2842
    PWD=nymhuq-3mehxy-pykWom
    ;;
  or62)
    USER_ID=or62
    PWD=gyhdiX-dywme6-xyxdyc
    ;;
  *)
    echo "ERROR: User not recognized"
    ;;
esac

export USER_ID
export PWD