import os
import json
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class FacultyMember(BaseModel):
    id: str
    name: str
    designation: str
    email: str
    phone: str = ""
    office: str = ""
    website: str = ""
    profile_url: str = ""
    research_interests: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    cv_links: List[str] = Field(default_factory=list)
    bio_summary: str = ""
    raw_text: str = ""

class StaticContent(BaseModel):
    department: str = "Electronics and Communication Engineering"
    institution: str = "IIT Roorkee"
    announcements: List[str] = Field(default_factory=list)
    links: List[Dict[str, str]] = Field(default_factory=list)

def find_data_file(filename: str) -> Optional[str]:
    candidate_paths = [
        os.path.join("/data", filename),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data", filename)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../data", filename)),
        os.path.abspath(os.path.join(os.getcwd(), "data", filename)),
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            return p
    return None

class DataLoader:
    _instance = None

    def __init__(self):
        self.faculty: List[FacultyMember] = []
        self.faculty_by_email: Dict[str, FacultyMember] = {}
        self.static_content = StaticContent()
        self.load_all_data()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = DataLoader()
        return cls._instance

    def load_all_data(self):
        # 1. Load structured research interests map
        structured_interests: Dict[str, List[str]] = {}
        struct_path = find_data_file("faculty_structured.json")
        if struct_path:
            try:
                with open(struct_path, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                    for item in s_data:
                        em = item.get("email", "").lower().strip()
                        if em:
                            structured_interests[em] = item.get("research_interests", [])
            except Exception as e:
                print(f"[DataLoader] Warning loading faculty_structured.json: {e}")

        # 2. Load deep profiles
        deep_path = find_data_file("faculty_deep_profiles.json")
        if deep_path:
            try:
                with open(deep_path, "r", encoding="utf-8") as f:
                    deep_data = json.load(f)
                    for p in deep_data:
                        member = self._parse_deep_profile(p, structured_interests)
                        if member:
                            self.faculty.append(member)
                            if member.email:
                                self.faculty_by_email[member.email.lower()] = member
            except Exception as e:
                print(f"[DataLoader] Error loading faculty_deep_profiles.json: {e}")

        # 3. Load static content
        static_path = find_data_file("static_content.json")
        if static_path:
            try:
                with open(static_path, "r", encoding="utf-8") as f:
                    st_data = json.load(f)
                    self.static_content = StaticContent(
                        department=st_data.get("department", "Electronics and Communication Engineering"),
                        institution=st_data.get("institution", "IIT Roorkee"),
                        announcements=st_data.get("announcements", []),
                        links=st_data.get("links", [])
                    )
            except Exception as e:
                print(f"[DataLoader] Error loading static_content.json: {e}")

        print(f"[DataLoader] Loaded {len(self.faculty)} faculty members & {len(self.static_content.announcements)} announcements.")

    def _parse_deep_profile(self, profile_dict: Dict[str, Any], structured_interests: Dict[str, List[str]]) -> Optional[FacultyMember]:
        raw = profile_dict.get("raw_text_corpus", "")
        profile_url = profile_dict.get("profile_url", "")
        cv_links = profile_dict.get("cv_resume_links", [])
        lines = [l.strip() for l in raw.split("\n") if l.strip()]

        # Extract Email
        email_match = re.search(r'([\w\.-]+)(?:@|\[at\])ece\.iitr\.ac\.in', raw, re.IGNORECASE)
        email = f"{email_match.group(1)}@ece.iitr.ac.in".lower() if email_match else ""

        # Extract Name & Designation
        name = ""
        designation = ""
        for idx, line in enumerate(lines):
            if line in ["Download Resume", "CONTACT US", "Directory"]:
                for k in range(idx + 1, min(idx + 10, len(lines))):
                    candidate_desig = lines[k].lower()
                    if any(t in candidate_desig for t in ["professor", "head of the department", "head of department", "assistant professor", "associate professor"]):
                        name = lines[k - 1]
                        designation = lines[k]
                        break
                if name:
                    break

        if not name:
            for idx, line in enumerate(lines[:60]):
                l_lower = line.lower().strip()
                if any(t == l_lower for t in ["professor", "assistant professor", "associate professor", "head of the department"]):
                    if idx > 0 and len(lines[idx - 1]) < 60:
                        name = lines[idx - 1]
                        designation = line
                        break

        # Extract phone & website
        phone = ""
        website = ""
        phone_match = re.search(r'(\+?91[-\s]?)?(01332[-\s]?\d{5,6}|\d{10})', raw)
        if phone_match:
            phone = phone_match.group(0)

        web_match = re.search(r'https?://[^\s]+\.(?:wordpress\.com|github\.io|iitr\.ac\.in|sites\.google\.com)[^\s]*', raw)
        if web_match and "faculty" not in web_match.group(0).lower():
            website = web_match.group(0)

        # Research interests
        interests = structured_interests.get(email, [])
        if not interests:
            for i, line in enumerate(lines):
                if "RESEARCH INTERESTS" in line.upper():
                    if i + 1 < len(lines) and lines[i + 1] != "BIOSKETCH":
                        raw_interests = lines[i + 1]
                        interests = [item.strip() for item in re.split(r'[,;]', raw_interests) if len(item.strip()) > 3]
                    break

        # Filter CV links (keep faculty resumes, discard general timetables)
        cleaned_cvs = []
        for cv in cv_links:
            cv_lower = cv.lower()
            if "resume" in cv_lower or "biodata" in cv_lower or ("pdf" in cv_lower and "time table" not in cv_lower):
                cleaned_cvs.append(cv)

        # Education extraction
        education = []
        for i, line in enumerate(lines):
            if "EDUCATIONAL DETAILS" in line.upper() or "EDUCATION" in line.upper():
                for j in range(i + 1, min(i + 12, len(lines))):
                    if lines[j] in ["Professional Background", "RESEARCH", "Honours and Awards"]:
                        break
                    if any(deg in lines[j].upper() for deg in ["PHD", "PH.D", "BTECH", "MTECH", "B.TECH", "M.TECH", "B.E", "M.E", "M.S"]):
                        education.append(lines[j])

        # Short bio summary (lines 50-75)
        bio_lines = lines[48:75]
        bio_summary = " ".join(bio_lines)[:400]

        member_id = email.split("@")[0] if email else name.lower().replace(" ", "_")

        return FacultyMember(
            id=member_id,
            name=name or "ECE Faculty Member",
            designation=designation or "Faculty Member",
            email=email,
            phone=phone,
            website=website,
            profile_url=profile_url,
            research_interests=interests,
            education=education,
            cv_links=cleaned_cvs,
            bio_summary=bio_summary,
            raw_text=raw[:2000]
        )
