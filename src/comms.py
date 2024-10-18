import os
from typing import Tuple, Optional

def get_gmail_credentials() -> Tuple[Optional[str], Optional[str]]:
    return os.environ.get('GMAIL_USER'), os.environ.get('GMAIL_PASSWORD')

def get_openai_api_key() -> Optional[str]:
    return os.environ.get('OPENAI_API_KEY')

def get_recipient_email() -> Optional[str]:
    return os.environ.get('RECIPIENT_EMAIL')
