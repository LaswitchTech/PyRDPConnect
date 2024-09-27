# Setup as a Thin-Client

Here is how you can convert a Raspberry Pi into a thin-client using PyRDPConnect.

```sh
wget https://www.albcie.com/dist/img/logo/logo-alb-globe-white.png
mv logo-alb-globe-white.png logo.png
curl -s https://raw.githubusercontent.com/LaswitchTech/PyRDPConnect/refs/heads/dev/setup.sh -o setup.sh
bash setup.sh
```

## Security Considerations
Running scripts directly from the internet can be risky. It’s always a good practice to review the script before running it:
```sh
curl -s https://raw.githubusercontent.com/LaswitchTech/PyRDPConnect/refs/heads/dev/setup.sh | less
```

## What the Script Does
The `setup.sh` script will:
- Install necessary dependencies for running PyRDPConnect on the Raspberry Pi.
- Configure the Raspberry Pi to launch PyRDPConnect in full-screen mode upon startup.
- Set up the environment to act as a thin-client, minimizing unnecessary services and processes.

## Post-Installation Steps
After running the setup script:
1. Verify that the installation was successful by rebooting the Raspberry Pi. PyRDPConnect should start automatically in full-screen mode.
2. Configure the RDP connections through the PyRDPConnect interface as needed.
3. Optionally, adjust any system settings for your specific use case, such as network configurations or power management settings.

## Rollback Instructions
If you need to undo the changes made by the setup script, follow these steps:
1. Remove installed packages:
```sh
sudo apt-get remove --purge <package_names>
```
2. Restore any modified configuration files.
3. Disable or remove any startup scripts related to PyRDPConnect.
