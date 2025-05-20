import requests
from dotenv import load_dotenv
import os

API_BASE_URL = "https://secureprod155.houston.hpecorp.net/api"
VTN_BASE_URL = "https://vtn.hpecorp.net/api"

load_dotenv()

def get_headers(token):
    return {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

def start_scan(payload, token):
    return requests.post(f"{API_BASE_URL}/scans/initiate", json=payload, headers=get_headers(token)).json()

def check_scan_status(scan_id, token):
    return requests.get(f"{API_BASE_URL}/scans/status?scanId={scan_id}", headers=get_headers(token)).json()

def download_report(scan_id, token):
    payload = {
        "scanId": scan_id,
        "vtnInventory": "spdx",
        "vtnUpload": False,
        "download": True
    }
    return requests.post(f"{API_BASE_URL}/scans/reports", json=payload, headers=get_headers(token), stream=True)

def upload_inventory(inv_file, scan, token):
    payload = {
        "product_name":scan.job.product_name,
        "product_version":scan.job.product_version,
        "notifyUsers": False
    }
    with open(inv_file, "rb") as f:
        return requests.post(
                f"{VTN_BASE_URL}/inventory/import",
                headers={'Authorization': f'Bearer {token}'},
                files={"file": (os.path.basename(inv_file), f, "application/json")},
                data=payload
            )

def is_token_valid(token):
    response = requests.get(VTN_BASE_URL, headers=get_headers(token))#/hpe_product?name={PRODUCT_NAME}&version={PRODUCT_VERSION}", headers=get_headers(token))
    if response.status_code == 401:
        return False
    else:
        return True

def get_token():
    # Check if old token still valid and return
    old_token = os.getenv('VTN_SESSION_TOKEN')
    if is_token_valid(old_token):
        print(f"Old token still valid.")
        return old_token
    
    payload = {
        "email": os.getenv("VTN_EMAIL"),
        "password": os.getenv("VTN_TOKEN")
    }
    try:
        # Retrieve new session token
        response = requests.post(f"{VTN_BASE_URL}/login/app_login", data=payload)
        response.raise_for_status()
        if response.status_code == 200:
            token = response.json()['data']['token']['token']
            print(f"Successfully Authenticated")

            # Save the new token
            env_file = open('.env', 'r+')
            env_lines = env_file.readlines()
            env_file.close()
            for i in range(0, len(env_lines)):
                if 'VTN_SESSION_TOKEN' in env_lines[i]:
                    env_lines[i] = f"VTN_SESSION_TOKEN={token}"
            env_file = open('.env', 'w+')
            env_file.writelines(env_lines)
            env_file.close()
            return token
    except requests.RequestException as e:
        print(f"Failed to get session token | Error : {e}")
        return None