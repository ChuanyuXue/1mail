import os
from datetime import datetime, timedelta
from typing import Optional
from openai import OpenAI
from comms import get_openai_api_key, get_gmail_credentials, get_recipient_email
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import OPENAI_MODEL, PROMPT_TEMPLATE_PATH, EMAIL_DIR, SUMMARY_DIR, EMAIL_SIGNATURE, DATE_FORMAT


def load_api_key() -> Optional[str]:
    try:
        return get_openai_api_key()
    except Exception as e:
        print(f"Failed to load API key: {e}")
        return None


def read_file(path: str) -> Optional[str]:
    try:
        with open(path, "r") as file:
            return file.read()
    except Exception as e:
        print(f"Failed to read file {path}: {e}")
        return None


def process_emails_with_chatgpt(client: OpenAI, email_content: str) -> Optional[str]:
    prompt_template = read_file(PROMPT_TEMPLATE_PATH)
    if not prompt_template:
        return None

    prompt = prompt_template.format(email_content=email_content)

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that analyzes, categorizes, and summarizes emails.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in processing emails with ChatGPT: {e}")
        return None


def save_summary_to_file(summary: str, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w") as file:
            file.write(summary)
    except Exception as e:
        print(f"Failed to save summary to file: {e}")


def send_email(subject: str, body: str, recipient: str) -> None:
    sender_email, sender_password = get_gmail_credentials()
    
    if not sender_email or not sender_password:
        print("Invalid email credentials")
        return

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = recipient
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(message)
        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")


def main() -> None:
    api_key = load_api_key()
    if not api_key:
        print("OpenAI API key not found in environment variables")
        return

    client = OpenAI(api_key=api_key)

    yesterday = (datetime.now() - timedelta(days=1)).strftime(DATE_FORMAT)
    email_file_path = os.path.join(EMAIL_DIR, f"{yesterday}.txt")

    email_content = read_file(email_file_path)
    if email_content:
        summary = process_emails_with_chatgpt(client, email_content)
        if summary:
            summary += EMAIL_SIGNATURE
            print("Email Summary:")
            print(summary)
            save_summary_to_file(summary, os.path.join(SUMMARY_DIR, f"{yesterday}.txt"))

            recipient_email = get_recipient_email()
            if recipient_email:
                subject = f"Email Summary for {yesterday}"
                send_email(subject, summary, recipient_email)


if __name__ == "__main__":
    main()
