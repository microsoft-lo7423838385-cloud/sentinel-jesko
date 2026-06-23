Please Note

This files are not to be modifed

How to use your vps or ssh or cloud shell as relay to send smtp:?

"""what is a relay, relay helps you hide your main ip address and send via the vps or ssh or cloud shell's ip instead"""
"""it also helps solve port 25 issues with cloud shell, more of like port 25 bypass, because cloud shell is port 25 open,"""
"""and you know cloud shell randomises ip for new session, so it saves you looking up and down for new port 25 vps"


For vps/ssh:
1.) if you have vps, it's very easy just put your vps' ip address in config and vps' username 
2.) run the sender
3.) it will ask you for password, input it and continue to the sender and press enter

For cloud shell:
1.) move google_cloud.sh to your cloud shell
2.) then run sudo bash ./google_cloud.sh
3.) You get shown your ip address and username
4.) you get asked to download your private key
5.) Download it and put it on your host machine
6.) copy full path to the config and paste in "PUBLICK_KEY" in config
7.) put the ip address you got earlier in the config, make sure the ip address ends with ":"
8.) put also your user
9.) run the sender
10.) voila, our sender will use your cloud shell as relay to send mails
