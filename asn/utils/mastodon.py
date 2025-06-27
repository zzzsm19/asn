import requests
import json
import datetime
from mastodon.return_types import Status

DOMAIN_NAME = 'asn25.top'

def post_status_with_time(access_token, status, created_at):
    if isinstance(created_at, datetime.datetime):
        created_at = created_at.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    url = f'https://{DOMAIN_NAME}/api/v1/statuses'
    headers = {
        'Authorization': f"Bearer {access_token}",
        'Content-Type': 'application/json'
    }
    data = {
        'status': status,
        'created_at': created_at
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    return Status(**(response.json()))