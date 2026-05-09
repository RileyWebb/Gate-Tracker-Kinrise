#!/usr/bin/env python3
import argparse
import json
import time
import logging
import requests
from gpiozero import Button
from functools import partial
import threading

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Try to look for config in etc first, fallback to current directory
CONFIG_PATH = '/etc/gate-tracker/config.json'
import os
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = 'config.json'

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config from {CONFIG_PATH}: {e}")
        return None

def send_update(url, token, gate, company, action, name):
    logging.info(f"Button '{name}' pressed! Gate: {gate}, Company: {company}, Action: {action}")
    
    payload = {
        "gate": gate,
        "company": company,
        "action": action
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            logging.info(f"Successfully sent {action} for {gate}. Server response: {response.text}")
        else:
            logging.error(f"Failed to send update. Status Code: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP Request failed: {e}")

def send_heartbeat(server_url, token, device_id, interval=10):
    if not device_id:
        logging.info("No device id provided; skipping heartbeat thread.")
        return

    url = server_url.rstrip('/') + '/heartbeat'
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    while True:
        try:
            payload = {"device": device_id, "status": "ok"}
            requests.post(url, json=payload, headers=headers, timeout=5)
            logging.debug(f"Sent heartbeat for device {device_id}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Heartbeat failed for {device_id}: {e}")
        time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description='GPIO watcher for Gate Tracker')
    parser.add_argument('--device', '-d', help='Device id for this Pi (e.g. "pi-entrance" or "pi-exit")')
    args = parser.parse_args()

    config = load_config()
    if not config:
        return

    # Resolve device id from CLI first, then environment, then config file.
    device_id = args.device or os.environ.get("DEVICE") or config.get("device_id")

    if device_id:
        logging.info(f"Using device id: {device_id}")
    else:
        logging.warning("No device id set. Use --device, DEVICE env var, or config.json device_id.")

    server_url = config.get("server_url")
    secret_token = config.get("secret_token")
    buttons_config = config.get("buttons", {})

    # Keep references to prevent garbage collection
    active_buttons = []

    # Start heartbeat thread if device_id provided
    if device_id:
        heartbeat_thread = threading.Thread(target=send_heartbeat, args=(server_url, secret_token, device_id, 10), daemon=True)
        heartbeat_thread.start()

    for name, b_config in buttons_config.items():
        pin = b_config.get("gpio_pin")
        action = b_config.get("action")
        gate = b_config.get("gate")
        company = b_config.get("company")
        bounce_time = b_config.get("bounce_time", 0.2)
        button_device = b_config.get("device")

        # Device filtering logic:
        # - If a button has a `device` field, only register it when `--device` matches.
        # - If a button has no `device` field, register it only when --device is not provided (backwards compatibility).
        if button_device is not None:
            if device_id is None or button_device != device_id:
                logging.info(f"Skipping '{name}' assigned to device '{button_device}' (this device: '{device_id}')")
                continue
        else:
            if device_id is not None:
                logging.info(f"Skipping '{name}' because no device assignment present and --device was provided ({device_id})")
                continue

        if pin is None:
            logging.warning(f"Skipping '{name}' due to missing GPIO pin.")
            continue

        # Initialize the Button (pull_up=True implies button connects pin to GND)
        button = Button(pin, bounce_time=bounce_time)
        
        # When pressed, call send_update with the configured parameters
        button.when_pressed = partial(send_update, server_url, secret_token, gate, company, action, name)
        
        active_buttons.append(button)
        logging.info(f"Registered button '{name}' on GPIO {pin} for {gate} ({action} for Company {company})")

    logging.info("GPIO Watcher is running. Press CTRL+C to exit.")
    
    try:
        # Keep the script running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Exiting...")

if __name__ == "__main__":
    main()
