#!/bin/bash

# Step 1: Update the system
echo "Updating the Operating System..."
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y

# Step 2: Install a Minimal Desktop Environment
echo "Installing Openbox and Git..."
sudo apt-get install -y lightdm openbox git xterm

# Step 3: Clone the PyRDPConnect Repository
echo "Cloning the PyRDPConnect repository..."
cd ~
git clone https://github.com/LaswitchTech/PyRDPConnect.git

# Step 4: Configure Openbox to Start Without Panels and Customize the Menu
echo "Configuring Openbox to start without panels and customizing the menu..."
mkdir -p ~/.config/openbox

# Custom Openbox menu
cat <<EOL > ~/.config/openbox/menu.xml
<openbox_menu>
    <menu id="root-menu" label="Openbox Menu">
        <!-- PyRDPConnect -->
        <item label="PyRDPConnect">
            <action name="Execute">
                <command>~/PyRDPConnect/dist/linux/PyRDPConnect</command>
            </action>
        </item>
        <!-- Terminal -->
        <item label="Terminal">
            <action name="Execute">
                <command>xterm</command>
            </action>
        </item>
        <!-- Web Browser -->
        <item label="Web Browser">
            <action name="Execute">
                <command>xdg-open https://www.google.com</command>
            </action>
        </item>
        <!-- Restart -->
        <item label="Restart">
            <action name="Execute">
                <command>reboot</command>
            </action>
        </item>
        <!-- Shutdown -->
        <item label="Shutdown">
            <action name="Execute">
                <command>sudo poweroff</command>
            </action>
        </item>
    </menu>
</openbox_menu>
EOL

# Set up autostart for PyRDPConnect
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

# Export the correct locale settings to avoid errors
export LANGUAGE=en_CA.UTF-8
export LC_ALL=en_CA.UTF-8
export LANG=en_CA.UTF-8
export LC_CTYPE="en_CA.UTF-8"

# Step 7: Set Timezone to Montreal, QC, CA
echo "Setting timezone to America/Montreal..."
sudo timedatectl set-timezone America/Toronto

# Step 8: Set Up Raspberry Pi to Boot into the Desktop Environment
echo "Configuring Raspberry Pi to boot into the desktop environment..."
sudo raspi-config nonint do_boot_behaviour B4 # Automatically boot to desktop and login as 'pi'

# Instructions for further manual steps
echo "Setup completed. Please reboot the Raspberry Pi to apply the changes."
