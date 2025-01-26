#!/bin/sh
#
#   entrypoint.sh (C) 2025, Peter Sulyok
#   Entry point for `smfc` docker image.
#

# Set a default value for $SMFC_ARG environment variable if it was undefined.
if [ -z "${SMFC_ARGS+x}" ]; then
    SMFC_ARGS="-l 3"
fi

# Start `smfc` as a foreground process.
/opt/smfc/smfc.py -c /opt/smfc/smfc.conf $SMFC_ARGS
