#!/usr/bin/env bash
# Install SSM globally on Ubuntu/Linux

# Make launcher and uninstall script executable
chmod +x ssm
chmod +x uninstall.sh
# Copy the program to /usr/local/bin for launcher to work right
sudo mkdir /usr/local/bin/ssm_pkg
sudo touch /usr/local/bin/ssm_pkg/main.py
sudo cp ./ssm_pkg/main.py /usr/local/bin/ssm_pkg/main.py
# Copy launcher to /usr/local/bin
echo "Installing SSM globally..."
if sudo cp ssm /usr/local/bin/ssm; then
    echo "SSM installed globally! You can now run 'sudo ssm' from any terminal."
else
    echo "Failed to copy launcher to /usr/local/bin. Try running: sudo bash install.sh"
fi
