import logging
import requests
import json

class Notifier:
    def __init__(self, config_file: str = "config.json"):
        """Initialize notifier with configuration"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            logging.warning(f"Config file {config_file} not found. Using default settings.")
            self.config = {}
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in config file {config_file}")
            self.config = {}
    
    def send_telegram_notification(self, message: str) -> bool:
        """Send Telegram notification when CRN becomes available."""
        bot_token = self.config.get('telegram_bot_token', '')
        chat_id = self.config.get('telegram_chat_id', '')

        if not bot_token or not chat_id:
            logging.warning("Telegram bot token or chat id is not configured")
            return False

        try:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": True,
            }

            parse_mode = self.config.get('telegram_parse_mode')
            if parse_mode:
                payload["parse_mode"] = parse_mode

            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload,
                timeout=15
            )
            response.raise_for_status()
            result = response.json()
            if result.get("ok"):
                logging.info("Telegram notification sent successfully")
                return True

            logging.error(f"Telegram API returned an error: {result}")
            return False

        except Exception as e:
            logging.error(f"Error sending Telegram notification: {e}")
            return False
    
    def send_notification(self, crn: int, course_code: str, course_name: str, available_spots: str):
        """Send notification through Telegram."""
        message = (
            "ITU CRN Kontenjan Uyarisi\n"
            f"Ders: {course_code} - {course_name}\n"
            f"CRN: {crn}\n"
            f"Bos Kontenjan: {available_spots}\n\n"
            "Kayit icin: https://obs.itu.edu.tr/public/DersProgram"
        )

        return self.send_telegram_notification(message)
