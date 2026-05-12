#!/usr/bin/env python3
"""
Simple GPIO watcher for a dedicated person-exit button.
Posts an exit event for company 'Other' to the server's /api/event endpoint.
Usage:
  python3 exit_button_watcher.py --pin 17
Or set `person_exit_pin` in config.json under buttons or top-level.
"""
import argparse
import json
import logging
import os
import time
import requests
from functools import partial

try:
    from gpiozero import Button
except Exception:
    Button = None

# Config path (same lookup as other scripts)
CONFIG_PATH = '/etc/gate-tracker/config.json'
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = 'config.json'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config from {CONFIG_PATH}: {e}")
        return {}


def post_exit(server_url, token, gate='exit'):
    url = server_url.rstrip('/') + '/api/event'
    payload = {"gate": gate, "company": "Other", "action": "exit"}
    headers = {"Content-Type": "application/json"}
    if token:
        headers['Authorization'] = f"Bearer {token}"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        if resp.status_code == 200:
            logging.info(f"Logged exit to {url}")
        else:
            logging.error(f"Failed to log exit: {resp.status_code} {resp.text}")
    except Exception as e:
        logging.error(f"HTTP request failed: {e}")


def main():
    parser = argparse.ArgumentParser(description='Exit button watcher')
    parser.add_argument('--pin', '-p', type=int, help='GPIO pin number for the exit button')
    parser.add_argument('--gate', '-g', default='exit', help='Gate name to report (default: exit)')
    args = parser.parse_args()

    cfg = load_config()
    server_url = cfg.get('server_url') or cfg.get('server') or 'http://localhost:5000'
    secret = cfg.get('secret_token') or cfg.get('token') or None

    # Determine pin: CLI > config 'person_exit_pin' > config.buttons.person_exit.gpio_pin
    pin = args.pin
    if pin is None:
        pin = cfg.get('person_exit_pin')
    if pin is None:
        # check buttons section for a name 'person_exit' or 'exit_only'
        buttons = cfg.get('buttons', {})
        for name in ('person_exit', 'exit_only', 'exit_button'):
            if name in buttons and isinstance(buttons[name], dict):
                pin = buttons[name].get('gpio_pin')
                break

    if not pin:
        logging.error('No GPIO pin configured for the exit button. Provide --pin or set person_exit_pin in config.json.')
        return

    if Button is None:
        logging.error('gpiozero library not available. Install gpiozero to use GPIO features.')
        return

    logging.info(f"Starting exit button watcher on GPIO {pin}, reporting to {server_url}")

    button = Button(pin, bounce_time=0.2)
    button.when_pressed = partial(post_exit, server_url, secret, args.gate)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info('Exit button watcher stopped')


if __name__ == '__main__':
    main()
