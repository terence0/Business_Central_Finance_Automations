from msal import ConfidentialClientApplication
import json
import logging
import requests


# Configuration
with open('./config/config.json', 'r') as config_file:
    config = json.load(config_file)
    
# Function to get access token
def get_access_token_v1():
    try:
        # Initialize the MSAL Confidential Client Application
        app = ConfidentialClientApplication(
            client_id=config['api']['client_id'],
            authority=config['api']['authority'] + config['api']['tenant_id'],
            client_credential=config['api']['client_secret'],
        )

        # Acquire token for client
        result = app.acquire_token_for_client(scopes=[config['api']['scope']])

        # Check if the token was successfully retrieved
        if "access_token" in result:
            logging.info("Access token successfully retrieved.")
            return result['access_token']
        else:
            logging.error(f"Failed to retrieve access token: {result.get('error_description')}")
            raise Exception(f"Error: {result.get('error')}, Description: {result.get('error_description')}")

    except Exception as e:
        logging.error(f"An error occurred while retrieving the access token: {e}")
        raise

def get_access_token():
    try:
        # Define the token endpoint and payload
        token_url = config['api']['token_url']
        payload = {
            'client_id': config['api']['client_id'],
            'client_secret': config['api']['client_secret'],
            'scope': config['api']['scope'],
            'grant_type': config['api']['grant_type']
        }

        # Make the POST request to the token endpoint
        logging.info("Requesting access token...")
        response = requests.post(token_url, data=payload, verify=False)

        # Check if the request was successful
        if response.status_code == 200:
            token_data = response.json()
            logging.info("Access token successfully retrieved.")
            return token_data['access_token']
        else:
            logging.error(f"Failed to retrieve access token: {response.text}")
            raise Exception(f"Error: {response.status_code}, Response: {response.text}")

    except Exception as e:
        logging.error(f"An error occurred while retrieving the access token: {e}")
        raise

# Test the function
if __name__ == "__main__":
    token = get_access_token()
    print(f"Access Token: {token}")


