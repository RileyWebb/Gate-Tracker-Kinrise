#!/bin/bash
# Script to pull the repository using a specific SSH key

# WARNING: Update REPO_DIR to the absolute path where your repo lives on the Linux machine
REPO_DIR="/opt/Gate-Tracker-Kinrise"
# WARNING: Update SSH_KEY_PATH to the absolute path of your secret SSH key file
SSH_KEY_PATH="/home/kinrise/.ssh/id_rsa_gate_tracker"
# Define the branch you want to pull
BRANCH="main"

echo "Starting repository pull at $(date)"

cd "$REPO_DIR" || { echo "Failed to navigate to $REPO_DIR"; exit 1; }

# Perform the pull securely using the provided SSH key. 
# StrictHostKeyChecking=no is useful for automated scripts to avoid prompt stalls if the known_hosts is empty.
export GIT_SSH_COMMAND="ssh -i $SSH_KEY_PATH -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
git pull origin "$BRANCH"

echo "Pull completed successfully at $(date)"
