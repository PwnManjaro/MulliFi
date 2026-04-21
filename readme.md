
🛰️ MulliFi

===========

  

A robust Python utility for UniFi gateways that automates **Mullvad WireGuard VPN** rotations. It features a clean Flask web dashboard for manual control and an APScheduler-based backend for automatic periodic IP rotation.

  

🛠️ Key Features

----------------

  

*  **Dynamic Rotation**: Automatically switches VPN endpoints based on a cron schedule.

*  **UniFi Proxy API Integration**: Seamlessly updates WireGuard client configs on UDM, UDM Pro, SE, and UXG devices.

*  **Mullvad Relay Discovery**: Fetches active, verified WireGuard relays directly from Mullvad's API.

*  **Web Dashboard**: Monitor tunnel health, check your public-facing VPN IP, and trigger manual "teleports."

*  **Docker Ready**: Fully containerized for easy deployment on home servers or NAS.

  

🚀 Quick Start (Docker)

-----------------------

  

The fastest way to get Mullifi running is via Docker.

  

### 1\. Configuration

  

Create a config.json in your local directory:

  

    { 
    "UNIFI_IP": "192.168.1.1", 
    "UNIFI_API_KEY": "your_unifi_api_key", 
    "VPN_CLIENT_ID": "vpn-client-uuid-from-unifi-url",
    "MULLVAD_PRIVATE_KEY": "your_mullvad_private_key", 
    "SCHEDULE_HOUR": 3, 
    "SCHEDULE_MINUTE": 0, 
    "FLASK_PORT": 5000, 
    "FLASK_SECRET": "your_ultra_secret_string" 
    } 
    
      

### 2\. Build and Start

  

 

    docker-compose up -d --build 

  

🐍 Manual Installation

----------------------

  

     git clone https://github.com/PwnManjaro/MulliFi.git 
     cd MulliFi
     python -m venv venv
     source venv/bin/activate
     pip install -r requirements.txt
     python main.py 
    
      

Headless Mode

-------------

  

It is also possible to run MulliFi in headless mode

  

    bash python main.py —no-gui 

  

For docker this can be achieved by editing the docker file

  

Prerequisites

-------------

  

To make MulliFi work you need to have already configured a VPN client to mullvad on your Unifi network, MulliFi will use the existing Mullvad and unifi profiles to update.

  

🛠️ Configuration Details

-------------------------

  

UNIFI\_IP

  

The local IP address of your UniFi Gateway.

  

UNIFI\_API\_KEY

  

Generated in UniFi OS

  

VPN\_CLIENT\_ID

  

Find this in the URL when editing the VPN client in UniFi.

  

MULLVAD\_PRIVATE\_KEY

  

Your 44-character base64 private key from Mullvad.

  

FLASK\_PORT

  

The port the web dashboard will listen on (default: 5000).

  

⚠️ Security Disclaimer

----------------------

  

This application interacts with your network gateway.

  

*  **Never** commit your config.json to public repositories.

* If you do not need the manual switcher run it in headless mode

* Use a strong FLASK\_SECRET.

* Disable SSL verification only if you understand the risks of Man-in-the-Middle (MITM) attacks in your local network.

* to state the obvious: Do not expose this to the internet



