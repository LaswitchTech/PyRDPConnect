#!/bin/bash

# Function to detect the operating system distribution
get_distribution() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    else
        echo "unknown"
    fi
}

# Get the distribution
DISTRO=$(get_distribution)

# Function to print the current step
log_step() {
    echo "Step $1: $2"
}

# Update the system
log_step 1 "Updating the Operating System..."
if [ "$DISTRO" == "raspbian" ] || [ "$DISTRO" == "debian" ]; then
    sudo apt-get update
    sudo apt-get full-upgrade -y
    sudo apt-get upgrade -y
    sudo apt-get dist-upgrade -y
else
    echo "Unsupported distribution: $DISTRO"
    exit 1
fi

# Install necessary packages based on the distribution
log_step 2 "Installing a Minimal Desktop Environment, Git, Firefox, ImageMagick, and feh..."
if [ "$DISTRO" == "raspbian" ] || [ "$DISTRO" == "debian" ]; then
    sudo apt-get install -y lightdm openbox git xterm firefox-esr plymouth plymouth-themes imagemagick feh freerdp2-x11 python3 python3-pyqt5 python3-pyqt5.*
else
    echo "Unsupported distribution: $DISTRO"
    exit 1
fi

# Clone or update the PyRDPConnect repository
log_step 3 "Cloning or updating the PyRDPConnect repository..."
if [ -d "~/PyRDPConnect" ]; then
    cd ~/PyRDPConnect
    git pull
    cd ~
else
    cd ~
    git clone https://github.com/LaswitchTech/PyRDPConnect.git
fi

# Create a gradient background image
log_step 4 "Creating a gradient background image..."
mkdir -p ~/backgrounds
convert -size 1920x1080 gradient:'#265162-#002136' ~/backgrounds/gradient.png

# Configure Openbox
log_step 5 "Configuring Openbox to start without panels, set the gradient background, and customize the menu..."
mkdir -p ~/.config/openbox

# Autostart and menu configurations
cat <<EOL > ~/.config/openbox/autostart
# Set gradient background
feh --bg-scale ~/backgrounds/gradient.png &
EOL
if [ "$DISTRO" == "raspbian" ]; then
  cat <<EOL >> ~/.config/openbox/autostart
# Autostart PyRDPConnect in full-screen mode
python ~/PyRDPConnect/src/PyRDPConnect.py &
EOL
fi

cat <<EOL > ~/.config/openbox/menu.xml
<openbox_menu>
    <menu id="root-menu" label="Openbox Menu">
        <item label="PyRDPConnect">
            <action name="Execute">
                <command>python ~/PyRDPConnect/src/PyRDPConnect.py</command>
            </action>
        </item>
        <item label="Terminal">
            <action name="Execute">
                <command>xterm</command>
            </action>
        </item>
        <item label="Web Browser">
            <action name="Execute">
                <command>firefox</command>
            </action>
        </item>
        <item label="Restart">
            <action name="Execute">
                <command>systemctl reboot</command>
            </action>
        </item>
        <item label="Shutdown">
            <action name="Execute">
                <command>systemctl poweroff</command>
            </action>
        </item>
    </menu>
</openbox_menu>
EOL

# Set Openbox to start automatically
log_step 6 "Setting Openbox to start automatically..."
cat <<EOL > ~/.xinitrc
exec openbox-session
EOL

# Set locale and timezone
log_step 7 "Setting locale and timezone..."
sudo sed -i '/en_GB.UTF-8/s/^/#/' /etc/locale.gen
sudo sed -i '/en_CA.UTF-8/s/^# //g' /etc/locale.gen
sudo locale-gen
sudo update-locale LANG=en_CA.UTF-8
sudo timedatectl set-timezone America/Toronto

# Configure PolicyKit for non-sudo reboot and shutdown
log_step 8 "Configuring PolicyKit for non-sudo reboot/shutdown..."
sudo bash -c 'cat <<EOL > /etc/polkit-1/localauthority/50-local.d/10-power-management.pkla
[Allow Reboot and Shutdown]
Identity=unix-user:*
Action=org.freedesktop.login1.reboot;org.freedesktop.login1.power-off
ResultActive=yes
EOL'

# Disable verbose boot and enable Plymouth theme
log_step 9 "Disabling verbose boot and enabling Plymouth theme..."
if [ -f "/boot/firmware/cmdline.txt" ]; then
    FILE=/boot/firmware/cmdline.txt
    sudo sed -i 's/console=tty1/console=tty3 splash quiet plymouth.ignore-serial-consoles/' $FILE
    if ! grep -q "splash quiet" $FILE; then
      echo "splash quiet" | sudo tee -a $FILE
    fi
    sudo bash -c "echo "disable_splash=1" >> $FILE"
fi

# Copy and set custom Plymouth theme
log_step 10 "Setting the custom Plymouth theme..."
if [ -d "/usr/share/plymouth/themes/pyrdpconnect" ]; then
    sudo rm -rf /usr/share/plymouth/themes/pyrdpconnect
fi
sudo cp -r ~/PyRDPConnect/src/plymouth /usr/share/plymouth/themes/pyrdpconnect
sudo plymouth-set-default-theme -R pyrdpconnect
sudo update-initramfs -u

# Enable auto-login for Debian
if [ "$DISTRO" == "debian" ]; then
    log_step 11 "Enabling auto-login for Debian..."
    if grep -q "^#autologin-user=" /etc/lightdm/lightdm.conf; then
        sudo sed -i "s/^#autologin-user=.*/autologin-user=$USER/" /etc/lightdm/lightdm.conf
    else
        echo "autologin-user=$USER" | sudo tee -a /etc/lightdm/lightdm.conf
    fi

    if grep -q "^#autologin-user-timeout=" /etc/lightdm/lightdm.conf; then
        sudo sed -i "s/^#autologin-user-timeout=.*/autologin-user-timeout=0/" /etc/lightdm/lightdm.conf
    else
        echo "autologin-user-timeout=0" | sudo tee -a /etc/lightdm/lightdm.conf
    fi
fi

# Add PyRDPConnect.desktop to autostart in Debian
if [ "$DISTRO" == "debian" ]; then
    log_step 12 "Adding PyRDPConnect to Debian's autostart using a .desktop entry..."

    # Create the autostart directory if it doesn't exist
    mkdir -p ~/.config/autostart

    # Create the .desktop file for PyRDPConnect
    cat <<EOL > ~/.config/autostart/PyRDPConnect.desktop
[Desktop Entry]
Name=PyRDPConnect
Exec=python ~/PyRDPConnect/src/PyRDPConnect.py
Type=Application
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOL
fi

# Additional Raspberry Pi OS-specific configurations
if [ "$DISTRO" == "raspbian" ]; then
    log_step 12 "Configuring Raspberry Pi OS for desktop boot and multi-monitor support..."

    # Set up Raspberry Pi to boot into the desktop environment
    sudo raspi-config nonint do_boot_behaviour B4

    # Enable HDMI output for both monitors
    sudo bash -c 'cat <<EOL >> /boot/config.txt
# Enable HDMI output for both monitors
hdmi_force_hotplug=1
hdmi_force_hotplug:1=1
hdmi_group=2
hdmi_mode=82
hdmi_group:1=2
hdmi_mode:1=82
disable_overscan=1
EOL'
fi

# Final instructions
log_step 13 "Setup completed. Please reboot the system to apply the changes."
