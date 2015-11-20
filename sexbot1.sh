#!/bin/bash

# get the dir of this script
pushd `dirname $0` > /dev/null
program_dir=`pwd`
popd > /dev/null

cd $program_dir

sleep 20


while true
    do

        touch /tmp/sexbot1

        sleep 10

        echo "starting script"
        /usr/bin/python3 DogFight.py

        sleep 1

done
