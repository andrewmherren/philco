## Setup
* Copy assets/config.txt to /boot/config.txt for touch screen config (verify compatibility if raspbian other than buster)
* Copy assets/input.conf to /usr/share/X11/xorg.conf.d/input.conf for touch calibration. New calibration can be made from menu > preferences > calibrate touch
* run `uname -r` to see which arm version raspi has.
* Go to nodejs.org and download node for arm version above.
* run `tar -xvf node...`
* Then copy binaries with "suco cp -R node-v6.../* /usr/local
* then run the setups script `/scripts/setups.sh`
* Disable screen power of in preferences > screen saver
* Finally pair bluetooth keyboard using bluetooth symbol in task bar.
* Go to https://www.arduino.cc/en/Main/Software
* download the Linux 32-bit arm version
* `cd~/Downloads`
* `tar -xvf arduino-1...`
* `sudo mv arduino-1... /etc/arduino`
* `sudo /etc/arduino/install.sh`
* Goto https://www.pjrc.com/teensy/teensyduino.html and download teensyduino for arm 32-bit and linux udev rules (follow install instructions on site)
