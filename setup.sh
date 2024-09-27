#!/bin/bash

# Step 1: Update the system
echo "Updating the Operating System..."
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y

# Step 2: Install a Minimal Desktop Environment, Firefox, ImageMagick, and feh
echo "Installing Openbox, Git, Firefox, ImageMagick, and feh..."
sudo apt-get install -y lightdm openbox git xterm firefox-esr plymouth plymouth-themes imagemagick feh

# Step 3: Clone the PyRDPConnect Repository
echo "Cloning the PyRDPConnect repository..."
if [ ! -d "~/PyRDPConnect" ]; then
  cd ~
  git clone https://github.com/LaswitchTech/PyRDPConnect.git
else
  echo "PyRDPConnect directory already exists. Skipping clone step."
fi

# Step 4: Create a Gradient Image for the Background
echo "Creating a gradient background image..."
mkdir -p ~/backgrounds
convert -size 1920x1080 gradient:'#265162-#002136' ~/backgrounds/gradient.png

# Step 5: Configure Openbox to Start Without Panels, Set Gradient Background, and Customize the Menu
echo "Configuring Openbox to start without panels, setting gradient background, and customizing the menu..."
mkdir -p ~/.config/openbox

# Set the gradient background using feh # ~/PyRDPConnect/dist/linux/PyRDPConnect &
cat <<EOL > ~/.config/openbox/autostart
# Set gradient background
feh --bg-scale ~/backgrounds/gradient.png &
# Autostart PyRDPConnect in full-screen mode
python ~/PyRDPConnect/src/PyRDPConnect.py &
EOL

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

# Step 6: Set Openbox to Start Automatically
echo "Setting Openbox to start automatically..."
cat <<EOL > ~/.xinitrc
exec openbox-session
EOL

# Step 7: Set Locale to en_CA.utf-8
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

# Step 8: Set Timezone to Montreal, QC, CA
echo "Setting timezone to America/Montreal..."
sudo timedatectl set-timezone America/Toronto

# Step 9: Configure Polkit for Non-Sudo Reboot/Shutdown
echo "Configuring PolicyKit to allow reboot and shutdown without password..."
sudo bash -c 'cat <<EOL > /etc/polkit-1/localauthority/50-local.d/10-power-management.pkla
[Allow Reboot and Shutdown]
Identity=unix-user:*
Action=org.freedesktop.login1.reboot;org.freedesktop.login1.power-off
ResultActive=yes
EOL'

# Step 10: Disable Verbose Boot and Enable Plymouth Theme
echo "Configuring boot process to disable verbose boot..."
sudo sed -i 's/console=tty1/console=tty3 splash quiet plymouth.ignore-serial-consoles/' /boot/firmware/cmdline.txt

# Verify that the 'splash' and 'quiet' options are added
if ! grep -q "splash quiet" /boot/firmware/cmdline.txt; then
  echo "splash quiet" | sudo tee -a /boot/firmware/cmdline.txt
fi

# Disable rainbow splash screen
echo "Disabling rainbow splash screen..."
sudo bash -c 'echo "disable_splash=1" >> /boot/firmware/config.txt'

# Step 11: Copy the Plymouth theme from the project and set it as default
echo "Copying custom Plymouth theme and setting it as default..."
if [ -d "/usr/share/plymouth/themes/pyrdpconnect" ]; then
    sudo rm -rf /usr/share/plymouth/themes/pyrdpconnect
fi
sudo cp -r ~/PyRDPConnect/src/plymouth /usr/share/plymouth/themes/pyrdpconnect

# Set the custom theme as the default and update the initramfs
sudo plymouth-set-default-theme -R pyrdpconnect
sudo update-initramfs -u

# Step 12: Set Up Raspberry Pi to Boot into the Desktop Environment
echo "Configuring Raspberry Pi to boot into the desktop environment..."
sudo raspi-config nonint do_boot_behaviour B4 # Automatically boot to desktop and login as 'pi'

# Instructions for further manual steps
echo "Setup completed. Please reboot the Raspberry Pi to apply the changes."
