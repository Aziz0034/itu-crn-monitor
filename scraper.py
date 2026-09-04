import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Any

class CRNScraper:
    def __init__(self):
        self.base_url = "https://obs.itu.edu.tr"
        self.course_schedule_url = f"{self.base_url}/public/DersProgram"
        self.branch_codes_url = f"{self.base_url}/public/DersProgram/SearchBransKoduByProgramSeviye"
        self.course_search_url = f"{self.base_url}/public/DersProgram/DersProgramSearch"
        self.session = requests.Session()
        # Set headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.5',
            'Connection': 'keep-alive',
        })
        self.branch_code_map_cache = {}
        
    def fetch_page(self) -> str:
        """Fetch the course schedule page content"""
        try:
            response = self.session.get(self.course_schedule_url, timeout=20)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException as e:
            logging.error(f"Error fetching page: {e}")
            return ""

    def fetch_branch_codes(self, program_level: str = "LS") -> List[Dict[str, Any]]:
        """Fetch active course branch codes for a program level."""
        try:
            response = self.session.get(
                self.branch_codes_url,
                params={"programSeviyeTipiAnahtari": program_level},
                timeout=20
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            branch_codes = response.json()
            logging.info(f"Fetched {len(branch_codes)} branch codes for program level {program_level}")
            return branch_codes
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Error fetching branch codes for {program_level}: {e}")
            return []

    def get_branch_code_map(self, program_level: str = "LS") -> Dict[str, Dict[str, Any]]:
        """Return branch-code records keyed by the visible code, such as BLG or MAT."""
        if program_level in self.branch_code_map_cache:
            return self.branch_code_map_cache[program_level]

        branch_codes = self.fetch_branch_codes(program_level)
        branch_map = {
            str(branch.get("dersBransKodu", "")).strip().upper(): branch
            for branch in branch_codes
            if branch.get("dersBransKodu") and branch.get("bransKoduId")
        }
        self.branch_code_map_cache[program_level] = branch_map
        return branch_map

    def fetch_courses_for_branch(self, program_level: str, branch_code_id: int) -> str:
        """Fetch the course table HTML for a single branch code."""
        try:
            response = self.session.get(
                self.course_search_url,
                params={
                    "programSeviyeTipiAnahtari": program_level,
                    "dersBransKoduId": branch_code_id,
                },
                timeout=20
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException as e:
            logging.error(f"Error fetching courses for branch id {branch_code_id}: {e}")
            return ""

    @staticmethod
    def _cell_text(cell) -> str:
        return cell.get_text(" ", strip=True)

    @staticmethod
    def _to_int(value: str, default: int = 0) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default
    
    def parse_course_data(self, html_content: str, branch_code: str = "") -> List[Dict[str, Any]]:
        """
        Parse course data from HTML content
        Returns a list of dictionaries containing course information
        """
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        courses = []
        
        table = soup.find('table')
            
        if table:
            rows = table.find_all('tr')
            
            for row in rows:
                try:
                    cells = row.find_all('td')
                    if len(cells) >= 11:
                        crn = self._cell_text(cells[0])
                        quota = self._cell_text(cells[9])
                        enrolled = self._cell_text(cells[10])
                        quota_int = self._to_int(quota)
                        enrolled_int = self._to_int(enrolled)
                        available = max(quota_int - enrolled_int, 0)

                        course_info = {
                            'crn': crn,
                            'course_code': self._cell_text(cells[1]),
                            'course_name': self._cell_text(cells[2]),
                            'instruction_method': self._cell_text(cells[3]),
                            'instructor': self._cell_text(cells[4]),
                            'building': self._cell_text(cells[5]),
                            'day': self._cell_text(cells[6]),
                            'time': self._cell_text(cells[7]),
                            'classroom': self._cell_text(cells[8]),
                            'quota': quota,
                            'enrolled': enrolled,
                            'available': available,
                            'reservation': self._cell_text(cells[11]) if len(cells) > 11 else '',
                            'programs': self._cell_text(cells[12]) if len(cells) > 12 else '',
                            'branch_code': branch_code,
                        }
                        
                        # Convert CRN to integer for easier comparison
                        try:
                            course_info['crn'] = int(course_info['crn'])
                        except ValueError:
                            # If CRN is not a valid integer, keep as string
                            pass
                            
                        courses.append(course_info)
                except Exception as e:
                    logging.error(f"Error parsing row: {e}")
                    continue
        
        return courses
    
    def get_tracked_crn_status(self, tracked_courses: List[Dict[str, Any]], program_level: str = "LS") -> Dict[int, Dict[str, Any]]:
        """
        Check availability for configured branch-code/CRN pairs.
        Returns dictionary mapping CRN to its status
        """
        branch_map = self.get_branch_code_map(program_level)
        found_courses = {}
        requested_crns = []
        seen_requested_crns = set()

        for tracked_course in tracked_courses:
            branch_code = str(tracked_course.get("branch_code", "")).strip().upper()
            target_crns = []
            for crn in tracked_course.get("crns", []):
                crn = int(crn)
                target_crns.append(crn)
                if crn not in seen_requested_crns:
                    requested_crns.append(crn)
                    seen_requested_crns.add(crn)

            if not branch_code or not target_crns:
                continue

            branch = branch_map.get(branch_code)
            if not branch:
                logging.error(f"Branch code {branch_code} was not found for program level {program_level}")
                for crn in target_crns:
                    found_courses[crn] = {
                        'crn': crn,
                        'course_code': 'BRANCH_NOT_FOUND',
                        'course_name': f'Branch code {branch_code} not found',
                        'available': 'N/A',
                        'branch_code': branch_code,
                    }
                continue

            html_content = self.fetch_courses_for_branch(program_level, branch.get("bransKoduId"))
            for course in self.parse_course_data(html_content, branch_code):
                crn = course.get("crn")
                if crn in target_crns:
                    found_courses[crn] = course

        # Return status for requested CRNs
        result = {}
        for crn in requested_crns:
            crn = int(crn)
            if crn in found_courses:
                result[crn] = found_courses[crn]
            else:
                # CRN not found on the page - mark as 'Not Found'
                result[crn] = {
                    'crn': crn,
                    'course_code': 'NOT_FOUND',
                    'course_name': 'Course not found',
                    'available': 'N/A'
                }
                
        return result

    def get_crn_status(self, crns: List[int], program_level: str = "LS", branch_codes=None) -> Dict[int, Dict[str, Any]]:
        """Backward-compatible wrapper for branch-specific CRN checks."""
        if not branch_codes:
            logging.error("Branch codes are required for CRN status checks.")
            return {
                int(crn): {
                    'crn': int(crn),
                    'course_code': 'BRANCH_REQUIRED',
                    'course_name': 'Branch code is required',
                    'available': 'N/A'
                }
                for crn in crns
            }

        tracked_courses = []
        for branch_code in branch_codes:
            tracked_courses.append({
                "branch_code": branch_code,
                "crns": crns,
            })

        return self.get_tracked_crn_status(tracked_courses, program_level)
