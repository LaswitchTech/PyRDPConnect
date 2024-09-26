#!/bin/bash

# Step 1: Update the system
echo "Updating the Operating System..."
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y

# Step 2: Install a Minimal Desktop Environment
echo "Installing Openbox and Git..."
sudo apt-get install -y lightdm openbox git

# Step 3: Clone the PyRDPConnect Repository
echo "Cloning the PyRDPConnect repository..."
cd ~
git clone https://github.com/LaswitchTech/PyRDPConnect.git

# Step 4: Configure Openbox to Start Without Panels
echo "Configuring Openbox to start without panels..."
mkdir -p ~/.config/openbox
cat <<EOL > ~/.config/openbox/autostart
# Autostart PyRDPConnect in full-screen mode
~/PyRDPConnect/dist/linux/PyRDPConnect &
EOL

# Step 5: Set Openbox to Start Automatically
echo "Setting Openbox to start automatically..."
cat <<EOL > ~/.xinitrc
exec openbox-session
EOL

# Step 6: Set Locale to en_CA.utf-8
echo "Setting locale to en_CA.utf-8..."
sudo sed -i '/en_GB.UTF-8/s/^/#/' /etc/locale.gen
sudo sed -i '/en_CA.UTF-8/s/^# //g' /etc/locale.gen
sudo locale-gen
sudo update-locale LANG=en_CA.UTF-8

# Step 7: Set Timezone to Montreal, QC, CA
echo "Setting timezone to America/Montreal..."
sudo timedatectl set-timezone America/Toronto

# Step 8: Set Up Raspberry Pi to Boot into the Desktop Environment
echo "Configuring Raspberry Pi to boot into the desktop environment..."
sudo raspi-config nonint do_boot_behaviour B4 # Automatically boot to desktop and login as 'pi'

# Instructions for further manual steps
echo "Setup completed. Please reboot the Raspberry Pi to apply the changes."
