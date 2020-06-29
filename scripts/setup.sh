#!/bin/bash
sudo apt-get install xscreensaver xinput-calibrator guake autoconf arduino
cp ../assets/autostart /etc/xdg/lxsession/LXDE-pi/autostart
cd ../api
npm install
cd ../ui
npm install
echo "Automated setup complete"
