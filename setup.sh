#!/bin/bash

# Step 1: Update the system
echo "Updating the Operating System..."
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y

# Step 2: Install a Minimal Desktop Environment and Firefox
echo "Installing Openbox, Git, and Firefox..."
sudo apt-get install -y lightdm openbox git xterm firefox-esr plymouth plymouth-themes

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
                <command>firefox</command>
            </action>
        </item>
        <!-- Restart -->
        <item label="Restart">
            <action name="Execute">
                <command>systemctl reboot</command>
            </action>
        </item>
        <!-- Shutdown -->
        <item label="Shutdown">
            <action name="Execute">
                <command>systemctl poweroff</command>
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

# Step 8: Configure Polkit for Non-Sudo Reboot/Shutdown
echo "Configuring PolicyKit to allow reboot and shutdown without password..."
sudo bash -c 'cat <<EOL > /etc/polkit-1/localauthority/50-local.d/10-power-management.pkla
[Allow Reboot and Shutdown]
Identity=unix-user:*
Action=org.freedesktop.login1.reboot;org.freedesktop.login1.power-off
ResultActive=yes
EOL'

# Step 9: Disable Verbose Boot and Enable Splash Screen with Custom Logo and Gradient Background
echo "Configuring boot process to disable verbose boot and enable splash screen with custom logo and gradient background..."
sudo sed -i 's/console=tty1/console=tty3 splash quiet plymouth.ignore-serial-consoles/' /boot/cmdline.txt

# Create a custom Plymouth theme
echo "Creating custom Plymouth theme with your logo and gradient background..."
sudo mkdir -p /usr/share/plymouth/themes/custom

# Assuming your logo is stored in ~/PyRDPConnect/src/icons/icon.png
sudo cp ~/PyRDPConnect/src/icons/icon.png /usr/share/plymouth/themes/custom/icon.png

# Create the Plymouth script for the custom theme
sudo bash -c 'cat <<EOL > /usr/share/plymouth/themes/custom/custom.plymouth
[Plymouth Theme]
Name=Custom
Description=Custom theme with logo and gradient background
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/custom
ScriptFile=/usr/share/plymouth/themes/custom/custom.script
EOL'

# Create the script file for the theme
sudo bash -c 'cat <<EOL > /usr/share/plymouth/themes/custom/custom.script
wallpaper_image = Image("icon.png");
wallpaper_image.SetPosition("center", 0, 0);
wallpaper_image.SetScale(1.0, 1.0);

# Gradient background
window.SetBackgroundTopColor(0.149, 0.318, 0.384);    # RGB for #265162
window.SetBackgroundBottomColor(0.0, 0.129, 0.212);   # RGB for #002136
EOL'

# Set the custom theme as the default
sudo plymouth-set-default-theme -R custom

# Step 10: Set Up Raspberry Pi to Boot into the Desktop Environment
echo "Configuring Raspberry Pi to boot into the desktop environment..."
sudo raspi-config nonint do_boot_behaviour B4 # Automatically boot to desktop and login as 'pi'

# Instructions for further manual steps
echo "Setup completed. Please reboot the Raspberry Pi to apply the changes."
