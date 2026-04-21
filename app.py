import json
import random
import logging
import argparse
import datetime
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import urllib3
from flask import Flask, render_template, redirect, url_for, flash, request
from apscheduler.schedulers.background import BackgroundScheduler

# --- Global Configuration & Constants ---
MULLVAD_RELAY_API = "https://api.mullvad.net/www/relays/wireguard/"
MULLVAD_CHECK_URL = "https://am.i.mullvad.net/json"
UNIFI_URL_TEMPLATE = "https://{ip}/proxy/network/api/s/default/rest/networkconf/{id}"

# Suppress SSL warnings for local gateway interaction
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MulliFiManager:
    EU_NODES = ["se", "no", "nl", "de", "ch", "at", "be", "dk", "fr", "es", "it", "gb"]

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.state_file = Path("vpn_state.json")
        self.scheduler = BackgroundScheduler()
        self.cfg = self._load_config()
        
        self.headers = {"X-API-KEY": self.cfg['UNIFI_API_KEY']}
        self.unifi_endpoint = UNIFI_URL_TEMPLATE.format(
            ip=self.cfg['UNIFI_IP'], 
            id=self.cfg['VPN_CLIENT_ID']
        )

    def _load_config(self) -> dict:
        try:
            return json.loads(self.config_path.read_text())
        except Exception as e:
            logger.critical(f"Initialization failed: Could not load {self.config_path} - {e}")
            raise

    def get_last_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except json.JSONDecodeError:
                logger.error("State file corrupted.")
        return {"country_code": "??", "last_switch": "Never"}

    def check_health(self) -> Dict[str, bool]:
        health = {"unifi": False, "mullvad": False}
        try:
            m_res = requests.get(MULLVAD_RELAY_API, timeout=3)
            health["mullvad"] = m_res.status_code == 200
            
            u_res = requests.get(self.unifi_endpoint, headers=self.headers, verify=False, timeout=2)
            health["unifi"] = u_res.status_code == 200
        except requests.RequestException as e:
            logger.warning(f"Health check connectivity issue: {e}")
        return health

    def _get_wireguard_interface_defaults(self, config_text: str) -> Tuple[str, str]:
        lines = config_text.splitlines()
        addr = next((l.split('=')[1].strip() for l in lines if "Address =" in l), "10.64.0.1/32")
        dns = next((l.split('=')[1].strip() for l in lines if "DNS =" in l), "10.64.0.1")
        return addr, dns

    def _build_wireguard_config(self, address: str, dns: str, server: dict) -> str:
        return (
            "[Interface]\n"
            f"PrivateKey = {self.cfg['MULLVAD_PRIVATE_KEY'].strip()}\n"
            f"Address = {address}\n"
            f"DNS = {dns}\n"
            "MTU = 1420\n\n"
            "[Peer]\n"
            f"PublicKey = {server['pubkey'].strip()}\n"
            f"Endpoint = {server['ipv4_addr_in']}:51820\n"
            "AllowedIPs = 0.0.0.0/0\n"
            "PersistentKeepalive = 25\n"
        )

    def update_vpn(self, country_code: str) -> bool:
        country_code = country_code.lower().strip()[:2]
        
        try:
            # Fetch UniFi state
            response = requests.get(self.unifi_endpoint, headers=self.headers, verify=False, timeout=5)
            response.raise_for_status()
            payload = response.json().get('data', [{}])[0]
            
            # Extract current networking info
            current_conf = payload.get('wireguard_client_configuration_file', "")
            ip, dns = self._get_wireguard_interface_defaults(current_conf)

            # Fetch and filter Mullvad relays
            relay_res = requests.get(MULLVAD_RELAY_API, timeout=5)
            relay_res.raise_for_status()
            relays = [r for r in relay_res.json() if r['country_code'] == country_code and r['active']]
            
            if not relays:
                logger.error(f"No active relays for {country_code}")
                return False
                
            server = random.choice(relays)
            new_conf = self._build_wireguard_config(ip, dns, server)

            # Prepare and send UniFi update
            payload.update({
                "name": f"Vanish-{country_code.upper()}",
                "enabled": True,
                "wireguard_client_configuration_file": new_conf,
                "wireguard_client_configuration_filename": f"vanish_{country_code}.conf"
            })
            payload.pop('_id', None)
            
            put_res = requests.put(self.unifi_endpoint, json=payload, headers=self.headers, verify=False, timeout=10)
            put_res.raise_for_status()
            
            self._persist_state(country_code, server['ipv4_addr_in'])
            logger.info(f"Successfully swapped tunnel to {country_code.upper()}")
            return True

        except Exception as e:
            logger.error(f"VPN Update failed: {e}")
            return False

    def _persist_state(self, country_code: str, server_ip: str):
        state = {
            "country_code": country_code, 
            "last_switch": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "server_ip": server_ip
        }
        self.state_file.write_text(json.dumps(state))

    def rotate_random_eu(self):
        self.update_vpn(random.choice(self.EU_NODES))

    def start_scheduler(self):
        self.scheduler.add_job(
            self.rotate_random_eu, 
            'cron', 
            hour=self.cfg['SCHEDULE_HOUR'], 
            minute=self.cfg['SCHEDULE_MINUTE'], 
            id='daily_rotation', 
            replace_existing=True
        )
        self.scheduler.start()


# --- Web Application ---
mgr = MulliFiManager()
app = Flask(__name__)
app.secret_key = mgr.cfg.get("FLASK_SECRET", "dev-key-keep-it-secret")

@app.route('/')
def index():
    job = mgr.scheduler.get_job('daily_rotation')
    next_run = job.next_run_time.strftime("%H:%M") if job else "N/A"
    
    time_left = "N/A"
    if job:
        diff = job.next_run_time.replace(tzinfo=None) - datetime.datetime.now()
        hours, remainder = divmod(max(0, diff.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        time_left = f"{int(hours)}h {int(minutes)}m"

    return render_template(
        'index.html', 
        state=mgr.get_last_state(), 
        next_run=next_run, 
        time_left=time_left, 
        cfg=mgr.cfg, 
        health=mgr.check_health()
    )

@app.route('/switch/<cc>')
def manual_switch(cc):
    if mgr.update_vpn(cc):
        flash(f"Teleport to {cc.upper()} successful.")
    else:
        flash("Teleport failed. Check logs.", "error")
    return redirect(url_for('index'))

@app.route('/update_schedule', methods=['POST'])
def update_schedule():
    try:
        h, m = int(request.form.get('hour')), int(request.form.get('minute'))
        mgr.cfg.update({'SCHEDULE_HOUR': h, 'SCHEDULE_MINUTE': m})
        
        mgr.config_path.write_text(json.dumps(mgr.cfg, indent=4))
        mgr.scheduler.reschedule_job('daily_rotation', trigger='cron', hour=h, minute=m)
        
        flash(f"Rotation timer updated to {h:02d}:{m:02d}")
    except Exception as e:
        flash(f"Failed to update schedule: {e}", "error")
        
    return redirect(url_for('index'))

@app.route('/api/check')
def proxy_mullvad_check():
    try:
        return requests.get(MULLVAD_CHECK_URL, timeout=5).json()
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-gui", action="store_true", help="Run without Flask web UI")
    args = parser.parse_args()

    mgr.start_scheduler()
    
    last = mgr.get_last_state()
    if last['country_code'] != "??":
        logger.info(f"Boot: Restoring tunnel to {last['country_code']}")
        mgr.update_vpn(last['country_code'])

    if args.no_gui:
        logger.info("MulliFi running in headless mode.")
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            mgr.scheduler.shutdown()
    else:
        app.run(host='0.0.0.0', port=mgr.cfg.get('FLASK_PORT', 5000), threaded=True)