#!/bin/bash

# Only install raspotify on the Mark-1 which has the correct rights for doing
# this and the correct repository.
if grep -q '"platform":.*"mycroft_mark_1"' /etc/mycroft/mycroft.conf; then
    sudo apt-get install -yq raspotify -o DPkg::Options::=--force-confdef
fi
exit 0
