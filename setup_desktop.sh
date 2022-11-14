#!/bin/sh
# curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_desktop.sh | bash


# wget -O /home/jovyan/.condarc https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/.condarc
# sudo wget -O /opt/conda/.condarc https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/.condarc-opt

DIR="/home/jovyan/.config"

if [ -d "$DIR/xfce4" ]; then
  # Take action if $DIR exists. #
  echo "Initizlized.. skipping..."
else
  ###  Control will jump here if $DIR does NOT exists ###
  echo "Initizlizing..."
  # mkdir -p "$DIR"
  # wget -O $DIR/xfce4.zip https://github.com/L1NNA/L1NNA-peppapig/releases/download/dot/xfce4.zip
  # unzip $DIR/xfce4.zip -d $DIR/
fi


# update jvd:
# /usr/bin/python3 -m pip install -U pip
# /usr/bin/python3 -m pip uninstall -y jvd 
# /usr/bin/python3 -m pip install -q git+https://github.com/L1NNA/JARV1S-Ghidra@master
# if ! command -v /usr/bin/python3 &> /dev/null
# then
#    echo "COMMAND could not be found"
#    exit
# fi
# /usr/bin/python3 -m pip install -q git+https://github.com/L1NNA/JARV1S-Ghidra@master
