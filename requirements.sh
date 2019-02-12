#!/bin/bash

UPDATE_TIME_LIMIT=$(( 60 * 60 * 2))

# Only install raspotify on the Mark-1 which has the correct rights for doing
# this and the correct repository.
if grep -q '"platform":.*"mycroft_mark_1"' /etc/mycroft/mycroft.conf; then
    # Check if we should try to update the package list
    CURRENT_TIME=$(date +%s)
    LAST_UPDATE=$(stat /var/cache/apt/pkgcache.bin -c %Y || echo ${CURRENT_TIME})
    if (( ${CURRENT_TIME} - ${LAST_UPDATE} > $UPDATE_TIME_LIMIT )) ; then
        sudo apt-get update
    fi
    sudo apt-get install --force-yes -yq raspotify -o DPkg::Options::=--force-confdef
fi
exit 0
