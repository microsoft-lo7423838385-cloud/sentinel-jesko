#!/bin/bash
#always remove \r

#       HA ?! HA ?!? HA ?!	            #
#		HAKA! HAKA! HAKA!               #
#			INCOMING!!!                 #
#		     Developer                  #
#=======================================#
#
#
#Author: METRO THE HACKER!!!!!!!!!!
#Editor: METRO THE HAKA




#install linux depencies
sudo apt update > /dev/null
if ! command -v python3.12 > /dev/null; then
	sudo add-apt-repository ppa:deadsnakes/ppa -y > /dev/null
	sudo apt install python3.12 -y > /dev/null
	sudo apt install python3.12-dev -y > /dev/null
fi

sudo apt install python3-pip -y > /dev/null
# sudo apt-get install python3.12-distutils -y > /dev/null
sudo apt-get install python3-apt -y > /dev/null
sudo apt install -y python3-virtualenv > /dev/null

if ! command -v python3.12 > /dev/null; then
	echo "Failure Installing python"
	exit
fi

! command -v unzip > /dev/null && sudo apt-get install unzip -y > /dev/null

req=$(([[ "$PWD" == *".sender"* ]] && echo "linux-requirements.txt") || echo ".sender/linux-requirements.txt")
if command -v virtualenv > /dev/null; then
	virtualenv .venv > /dev/null
	source .venv/bin/activate
	pip install -r "$req" > /dev/null
else
	python3.12 -m pip install -r "$req" --break-system-packages > /dev/null
fi

echo "success"


