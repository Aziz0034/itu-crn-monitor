#!/usr/bin/env python3
"""
ITU CRN Availability Monitor
Monitors ITÜ course schedule for available spots in specified CRNs
"""

import logging
import argparse
import json
import time
import sys
from scraper import CRNScraper
from notifier import Notifier

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "program_level": "LS",
    "tracked_courses": [],
    "polling_interval_minutes": 5,
    "notifications_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": ""
}

PROGRAM_LEVEL_LABELS = {
    "LS": "Lisans"
}

def load_config(config_file: str):
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in configuration file {config_file}!")
        sys.exit(1)

    config = DEFAULT_CONFIG.copy()
    config.update(data)
    return config

def save_config(config_file: str, config):
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
        f.write("\n")

def prompt_value(label: str, allow_empty: bool = False) -> str:
    while True:
        value = input(label).strip()
        if value.lower() == "q":
            print("Kurulum sihirbazı kapatıldı.")
            sys.exit(0)
        if value or allow_empty:
            return value
        print("Bu alan boş bırakılamaz. Çıkmak için q yazabilirsiniz.")

def parse_crn_input(value: str):
    crns = []
    for raw_part in value.replace(";", ",").split(","):
        raw_part = raw_part.strip()
        if not raw_part:
            continue

        for part in raw_part.split(":"):
            part = part.strip()
            if not part:
                continue

            try:
                crns.append(int(part))
            except ValueError:
                print(f"Geçersiz CRN atlandı: {part}")

    return crns

def normalize_tracked_courses(tracked_courses):
    by_branch = {}
    seen = set()

    for item in tracked_courses:
        branch_code = str(item.get("branch_code", "")).strip().upper()
        if not branch_code:
            continue

        for crn in parse_crn_input(",".join(str(value) for value in item.get("crns", []))):
            key = (branch_code, crn)
            if key in seen:
                continue
            by_branch.setdefault(branch_code, []).append(crn)
            seen.add(key)

    return [
        {
            "branch_code": branch_code,
            "crns": crns
        }
        for branch_code, crns in by_branch.items()
    ]

def has_tracked_courses(config):
    return bool(normalize_tracked_courses(config.get("tracked_courses", [])))

def run_setup_wizard(config_file: str):
    config = load_config(config_file)
    branch_map = CRNScraper().get_branch_code_map("LS")

    print("\nITU CRN Monitor kurulum sihirbazı")
    print("Lisans dersleri takip edilecek. Çıkmak için herhangi bir adımda q yazabilirsiniz.")
    print("Birden fazla CRN için virgül kullanabilirsiniz. Örnek: 14251,14250\n")
    if not branch_map:
        print("OBS branş kodu listesi okunamadı; girilen branş kodları canlı doğrulanmadan kaydedilecek.\n")

    tracked_courses = []
    while True:
        branch_code = prompt_value("Ders branş kodu (örn. BLG, MAT, FIZ - bitirmek için Enter): ", allow_empty=True)
        if not branch_code:
            if tracked_courses:
                break
            print("En az bir ders branş kodu ve CRN girmelisiniz.")
            continue

        branch_code = branch_code.upper()
        if branch_map and branch_code not in branch_map:
            answer = prompt_value(f"{branch_code} OBS lisans branş listesinde bulunamadı. Yine de eklensin mi? [e/h]: ")
            if answer.lower() != "e":
                continue

        crns = []
        while not crns:
            crn_input = prompt_value(f"{branch_code} için takip edilecek CRN(ler): ")
            crns = parse_crn_input(crn_input)
            if not crns:
                print("Geçerli CRN bulunamadı. Sadece sayısal CRN girin.")

        tracked_courses.append({
            "branch_code": branch_code,
            "crns": crns
        })

    print("\nKaydedilecek dersler:")
    for item in tracked_courses:
        print(f"- {item['branch_code']}: {', '.join(str(crn) for crn in item['crns'])}")

    should_save = prompt_value("\nKaydetmek için Enter'a basın, iptal için q yazın: ", allow_empty=True)
    if should_save.lower() == "q":
        print("Kurulum iptal edildi.")
        sys.exit(0)

    config["program_level"] = "LS"
    config["tracked_courses"] = normalize_tracked_courses(tracked_courses)
    config.pop("crns", None)
    config.pop("branch_codes", None)

    save_config(config_file, config)
    print(f"\nAyarlar {config_file} dosyasına kaydedildi.\n")

class CRNAvailabilityMonitor:
    def __init__(self, config_file: str = "config.json"):
        """Initialize the CRN monitor with configuration"""
        self.config_file = config_file
        
        self.config = load_config(config_file)

        self.scraper = CRNScraper()
        self.notifier = Notifier(config_file)
            
        self.tracked_courses = normalize_tracked_courses(self.config.get('tracked_courses', []))
        self.crn_list = [
            crn
            for tracked_course in self.tracked_courses
            for crn in tracked_course.get("crns", [])
        ]
        self.polling_interval = self.config.get('polling_interval_minutes', 5) * 60  # Convert to seconds
        self.program_level = 'LS'
        self.notifications_enabled = bool(self.config.get('notifications_enabled', False))
        self.notified_open_crns = set()
        
        if not self.tracked_courses:
            logger.error("No tracked courses configured! Run python main.py --setup first.")
            sys.exit(1)
            
        logger.info(f"CRN Monitor initialized with CRNs: {self.crn_list}")
        logger.info(f"Tracked courses: {self.tracked_courses}")
        logger.info(f"Program level: {self.program_level} ({PROGRAM_LEVEL_LABELS.get(self.program_level, self.program_level)})")
        logger.info(f"Notifications enabled: {self.notifications_enabled}")

    @staticmethod
    def available_spots_as_int(course_info) -> int:
        available_spots = course_info.get('available', 'N/A')
        if isinstance(available_spots, int):
            return available_spots

        if isinstance(available_spots, str):
            value = available_spots.strip()
            if value.isdigit():
                return int(value)

            parts = value.split('/')
            if len(parts) == 2 and parts[0].strip().isdigit():
                return int(parts[0].strip())

        quota = str(course_info.get('quota', '0')).strip()
        enrolled = str(course_info.get('enrolled', '0')).strip()
        if quota.isdigit() and enrolled.isdigit():
            return int(quota) - int(enrolled)

        return 0
        
    def check_availability(self):
        """Check availability for all configured CRNs"""
        logger.info("Checking CRN availability...")
        
        # Get current status for all CRNs
        crn_status = self.scraper.get_tracked_crn_status(
            self.tracked_courses,
            program_level=self.program_level
        )
        
        available_crn_count = 0
        for crn, course_info in crn_status.items():
            try:
                if course_info.get('course_code') in ['NOT_FOUND', 'BRANCH_NOT_FOUND']:
                    logger.warning(
                        f"CRN {crn} was not found in branch {course_info.get('branch_code', 'unknown')}"
                    )
                    self.notified_open_crns.discard(crn)
                    continue

                available_spots_int = self.available_spots_as_int(course_info)
                logger.debug(f"CRN {crn}: Available spots = {available_spots_int}")
                
                if available_spots_int > 0:
                    logger.info(
                        f"CRN {crn} ({course_info.get('course_code', 'Unknown')}) "
                        f"has {available_spots_int} available spot(s)!"
                    )
                    if not self.notifications_enabled:
                        logger.info("Notification skipped because notifications_enabled is false")
                    elif crn not in self.notified_open_crns:
                        if self.notifier.send_notification(crn, course_info.get('course_code', 'Unknown'), 
                                                          course_info.get('course_name', 'Unknown'), 
                                                          str(available_spots_int)):
                            logger.info(f"Notification sent for CRN {crn}")
                            self.notified_open_crns.add(crn)
                    else:
                        logger.info(f"CRN {crn} is still available; notification already sent")
                    available_crn_count += 1
                elif available_spots_int == 0:
                    logger.info(f"CRN {crn} has no available spots (currently full)")
                    self.notified_open_crns.discard(crn)
                elif isinstance(available_spots_int, int) and available_spots_int < 0:
                    logger.warning(f"CRN {crn} shows negative available spots ({available_spots_int})")
                else:
                    logger.info(f"CRN {crn} status uncertain: {available_spots}")
                    
            except Exception as e:
                logger.error(f"Error processing CRN {crn}: {e}")
                
        logger.info(f"Checked {len(crn_status)} CRNs. {available_crn_count} have available spots.")
        return crn_status
        
    def run(self):
        """Main application loop"""
        logger.info("Starting CRN Availability Monitor...")
        logger.info(f"Monitoring CRNs: {self.crn_list}")
        logger.info("Monitoring only configured undergraduate branch-code/CRN pairs.")
        logger.info(f"Polling interval: {self.polling_interval // 60} minutes")
        
        # Initial check
        self.check_availability()
        
        # Continuous monitoring
        try:
            while True:
                logger.info(f"Sleeping for {self.polling_interval // 60} minutes...")
                time.sleep(self.polling_interval)
                self.check_availability()
                
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user.")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")

def main():
    """Entry point of the application"""
    parser = argparse.ArgumentParser(
        prog="itu-crn-monitor",
        description="ITU OBS CRN kontenjan takip botu."
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Ders branş kodu ve CRN bilgilerini sorup config.json dosyasına kaydeder."
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Kullanılacak config dosyası. Varsayılan: config.json"
    )
    parser.add_argument(
        "--check-once",
        action="store_true",
        help="Tek kontenjan kontrolü yapar ve programı kapatır."
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        if args.setup or not has_tracked_courses(config):
            run_setup_wizard(args.config)
            if args.setup:
                return

        monitor = CRNAvailabilityMonitor(args.config)
        if args.check_once:
            monitor.check_availability()
            return

        monitor.run()
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
