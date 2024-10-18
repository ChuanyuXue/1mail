import logging
import os
import imaplib
from datetime import datetime, timedelta
import email
from email.header import decode_header
import html2text
import re
from email.utils import parsedate_to_datetime
from typing import List, Tuple, Optional
from comms import get_gmail_credentials
from email import message as email_message
from config import EMAIL_DIR, DATE_FORMAT

logging.basicConfig(level=logging.INFO)


def load_credentials() -> Tuple[str, str]:
    try:
        user, password = get_gmail_credentials()
        if user is None or password is None:
            raise ValueError("Invalid credentials")
        return user, password
    except Exception as e:
        logging.error(f"Failed to load credentials: {e}")
        raise


def connect_to_gmail_imap(user: str, password: str) -> imaplib.IMAP4_SSL:
    imap_url = "imap.gmail.com"
    try:
        mail = imaplib.IMAP4_SSL(imap_url)
        mail.login(user, password)
        mail.select("inbox")
        return mail
    except Exception as e:
        logging.error(f"Connection failed: {e}")
        raise


def fetch_emails_by_last_update(mail: imaplib.IMAP4_SSL) -> List[bytes]:
    date_time = datetime.now() - timedelta(days=1)
    date_time_str = date_time.strftime("%d-%b-%Y")
    status, messages = mail.search(None, f'(SINCE "{date_time_str}")')
    if status == "OK":
        return messages[0].split()
    else:
        logging.error(f"Failed to fetch emails: {status}")
        return []


def is_human_readable(text: str) -> bool:
    common_words = set(
        [
            "the",
            "be",
            "to",
            "of",
            "and",
            "a",
            "in",
            "that",
            "have",
            "I",
            "it",
            "for",
            "not",
            "on",
            "with",
            "he",
            "as",
            "you",
            "do",
            "at",
        ]
    )

    text = text.lower()
    words = re.findall(r"\b\w+\b", text)

    if not words:
        return False

    if not any(word in common_words for word in words):
        return False

    vowels = sum(1 for char in text if char in "aeiou")
    consonants = sum(1 for char in text if char.isalpha() and char not in "aeiou")
    if consonants == 0 or vowels / consonants < 0.2:
        return False

    if len(set(words)) / len(words) < 0.5:
        return False

    avg_word_length = sum(len(word) for word in words) / len(words)
    if avg_word_length > 15:
        return False

    return True


def decode_email_subject(subject: Tuple[bytes, Optional[str]]) -> str:
    decoded_subject, encoding = subject
    if isinstance(decoded_subject, bytes):
        return decoded_subject.decode(encoding or "utf-8", errors="replace")
    return decoded_subject


def extract_email_timestamp(date_str: Optional[str]) -> str:
    if not date_str:
        return "Unknown"
    try:
        return parsedate_to_datetime(date_str).strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError:
        date_tuple = email.utils.parsedate_tz(date_str)
        if date_tuple:
            return datetime(*date_tuple[:6]).strftime("%Y-%m-%d %H:%M:%S")
        return "Unknown"


def extract_email_body(email_message: email_message.Message) -> Tuple[str, List[str]]:
    body = ""
    attachments = []
    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                body = (
                    payload.decode(errors="replace")
                    if isinstance(payload, bytes)
                    else str(payload)
                )
            elif content_type == "text/html":
                payload = part.get_payload(decode=True)
                html_body = (
                    payload.decode(errors="replace")
                    if isinstance(payload, bytes)
                    else str(payload)
                )
                h = html2text.HTML2Text()
                h.ignore_links = True
                body = h.handle(html_body)
            else:
                filename = part.get_filename()
                if filename:
                    attachments.append(filename)
    else:
        payload = email_message.get_payload(decode=True)
        body = (
            payload.decode(errors="replace")
            if isinstance(payload, bytes)
            else str(payload)
        )
        if email_message.get_content_type() == "text/html":
            h = html2text.HTML2Text()
            h.ignore_links = True
            body = h.handle(body)

    return body, attachments


def clean_email_body(body: str) -> str:
    body = body.strip()
    body = "\n".join(line for line in body.splitlines() if line.strip())
    body = re.sub(
        r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
        "",
        body,
    )

    filtered_lines = [line for line in body.splitlines() if is_human_readable(line)]
    return "\n".join(filtered_lines)


def get_email_content(mail: imaplib.IMAP4_SSL, email_id: bytes) -> str:
    try:
        status, data = mail.fetch(email_id, "(RFC822)")  # type: ignore
        if status != "OK" or not data or not isinstance(data[0], tuple):
            logging.error(
                f"Failed to fetch email content: status={status}, data={data}"
            )
            return ""

        raw_email = data[0][1]
        email_message = email.message_from_bytes(raw_email)

        subject = decode_email_subject(decode_header(email_message["Subject"])[0])
        sender = email_message["From"]
        timestamp = extract_email_timestamp(email_message["Date"])

        body, attachments = extract_email_body(email_message)
        body = clean_email_body(body)

        attachment_info = (
            "\n\nAttachments:\n" + "\n".join(attachments) if attachments else ""
        )

        return f"From: {sender}\nSubject: {subject}\nDate: {timestamp}\n\n{body}{attachment_info}"
    except Exception as e:
        logging.error(f"Error in get_email_content: {e}")
        return ""


def save_email_content(email_contents: List[str], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for content in email_contents:
            file.write(content)
            file.write("\n" * 5)


def main() -> None:
    user, password = load_credentials()
    if not user or not password:
        logging.error("Gmail credentials not found in environment variables")
        return

    mail = connect_to_gmail_imap(user, password)
    try:
        email_ids = fetch_emails_by_last_update(mail)
        email_contents = [content for content in (get_email_content(mail, email_id.decode()) for email_id in email_ids) if content]  # type: ignore

        date_time = datetime.now() - timedelta(days=1)
        date_time_str = date_time.strftime(DATE_FORMAT)
        save_email_content(
            email_contents, os.path.join(EMAIL_DIR, f"{date_time_str}.txt")
        )
        logging.info(
            f"Saved {len(email_contents)} emails to {EMAIL_DIR}/{date_time_str}.txt"
        )
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        mail.logout()


if __name__ == "__main__":
    main()
