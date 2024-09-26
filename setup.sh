#!/bin/bash

# Step 1: Update the system
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y

# Step 2: Install a Minimal Desktop Environment
echo "Installing Openbox..."
sudo apt-get update
sudo apt-get install -y openbox

# Step 3: Configure Openbox to Start Without Panels
echo "Configuring Openbox to start without panels..."
mkdir -p ~/.config/openbox
cat <<EOL > ~/.config/openbox/autostart
# Autostart PyRDPConnect in full-screen mode
/usr/bin/python3 /path/to/PyRDPConnect.py &
EOL

# Step 4: Set Openbox to Start Automatically
echo "Setting Openbox to start automatically..."
cat <<EOL > ~/.xinitrc
exec openbox-session
EOL

# Step 5: Set Up Raspberry Pi to Boot into the Desktop Environment
echo "Configuring Raspberry Pi to boot into the desktop environment..."
sudo raspi-config nonint do_boot_behaviour B4 # Automatically boot to desktop and login as 'pi'

# Instructions for further manual steps
echo "Setup completed. Please make sure to:"
echo "1. Replace '/path/to/PyRDPConnect.py' in the autostart file with the actual path to your PyRDPConnect script."
echo "2. Reboot the Raspberry Pi to apply the changes."
