#!/bin/bash
#=======================================#
#    Copying Someone Else's code        #
#		Doesn't make you                #
#				A                       #
#		     Developer                  #
#=======================================#
#
#
#Author: Olivia Mangadoski
#Editor: Vim

# Check if the script is being run as root
if [ "$UID" -ne 0 ]; then
    echo "This script must be run as root."
    exit 1
fi

gcloud --version > /dev/null

##exit when needed
if [ $? -ne 0 ]; then
    echo "Please run on gcloud shell instead of shell"
    exit
fi

ip="$(curl --ipv4 https://icanhazip.com 2> /dev/null):"

##generate public key
gso=$(echo -e "\n\n" | gcloud cloud-shell ssh --dry-run 1> /dev/null 2>&1)

if [ $? -eq 0 ] && [ -f "$HOME/.ssh/google_compute_engine" ];then
    ##get the pbkey path
    pbkpath="$HOME/.ssh/google_compute_engine"
else
    ##an error occured
    echo "An error occured while trying to genrate public key '$gso'"
fi

##here indicates public key gen was complete now we have all we need
echo -e "IP Address: '$ip'"
echo "Downloading public key"

##downloads the public key
cloudshell download-files $pbkpath;

#sandbox corruption
while true; do
    ##zero day to exit sandbox mode
    ##jump to 40 bytes before our target address
    ##so our payload can contain
    ##5 null spaces between * and -
    ##aslr is disabled
    ##so write to 0x782371 jump to address 0x782371 to continue execution
    echo "*(%%^^^&%%%!dsa* 0x782341 %%***null - 7cac3fcb7083a2f339e85ab4dfbc111ccd36491ae57f875f862e8a2a3a8537bf3e90a8a120f9c722 {%%void%% !!1 return 0x782371)" > /dev/null
    sleep 300  # Send a signal to exploit every 5 minutes
done






