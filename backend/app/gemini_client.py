import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from .data_loader import FacultyMember

# List of preferred models in order of priority
MODELS_TO_TRY = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash"
]

class GeminiClient:
    def __init__(self):
        self.api_key = self._find_api_key()

    def _find_api_key(self) -> str:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if key:
            return key

        candidate_env_paths = [
            "/app/.env",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env")),
            os.path.abspath(os.path.join(os.getcwd(), ".env")),
            os.path.abspath(os.path.join(os.getcwd(), "backend/.env")),
        ]
        for env_path in candidate_env_paths:
            if os.path.exists(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("GEMINI_API_KEY="):
                                key = line.split("=", 1)[1].strip("\"' ")
                                if key:
                                    return key
                except Exception as e:
                    print(f"[GeminiClient] Error reading {env_path}: {e}")
        return ""

    def generate_rag_answer(
        self,
        query: str,
        faculty: List[FacultyMember],
        announcements: List[str],
        links: List[Dict[str, str]]
    ) -> str:
        if not self.api_key:
            return self._generate_fallback_answer(query, faculty, announcements, links)

        # Build Context
        context_parts = []
        if faculty:
            context_parts.append("### Relevant ECE Faculty Members at IIT Roorkee:")
            for f in faculty[:5]:
                interests_str = ", ".join(f.research_interests) if f.research_interests else "Information on profile"
                cv_info = f"CV/Resume Link: {f.cv_links[0]}" if f.cv_links else "No direct CV uploaded"
                context_parts.append(
                    f"- Name: {f.name}\n"
                    f"  Designation: {f.designation}\n"
                    f"  Email: {f.email}\n"
                    f"  Research Interests: {interests_str}\n"
                    f"  Profile: {f.profile_url}\n"
                    f"  {cv_info}\n"
                    f"  Bio/Details: {f.bio_summary[:200]}"
                )

        if announcements:
            context_parts.append("### Department Announcements & Programs:")
            for a in announcements:
                context_parts.append(f"- {a}")

        if links:
            context_parts.append("### Important Official Links:")
            for l in links:
                context_parts.append(f"- [{l.get('text', 'Link')}]({l.get('url', '#')})")

        context_text = "\n\n".join(context_parts)

        system_instruction = (
            "You are QueryECE, the official AI Assistant for the Department of Electronics and Communication "
            "Engineering (ECE) at the Indian Institute of Technology Roorkee (IIT Roorkee).\n"
            "Your goal is to answer the user's question accurately, concisely, and helpfully using ONLY the provided "
            "department data.\n"
            "Guidelines:\n"
            "1. Ground all facts in the provided context. If no professor or record matches, explain politely and suggest checking the directory.\n"
            "2. Highlight faculty names, their designations, and their specific research domains in bold.\n"
            "3. Mention contact emails and profile links when relevant.\n"
            "4. Maintain a professional, welcoming academic tone.\n"
            "5. Use clean GitHub markdown formatting with bullet points."
        )

        user_content = f"User Question: {query}\n\nContext:\n{context_text}"

        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_content}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1000
            }
        }

        # Try models in order
        for model in MODELS_TO_TRY:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12) as res:
                    res_json = json.loads(res.read().decode("utf-8"))
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8") if e.fp else ""
                log_msg = f"[GeminiClient] Model {model} HTTP Error {e.code}: {err_body}\n"
                print(log_msg)
                try:
                    with open("/app/gemini_debug.log", "a") as df:
                        df.write(log_msg)
                except Exception:
                    pass
            except Exception as e:
                log_msg = f"[GeminiClient] Model {model} failed: {type(e).__name__} - {e}\n"
                print(log_msg)
                try:
                    with open("/app/gemini_debug.log", "a") as df:
                        df.write(log_msg)
                except Exception:
                    pass

        # If LLM calls fail, return rule-based fallback
        return self._generate_fallback_answer(query, faculty, announcements, links)

    def _generate_fallback_answer(
        self,
        query: str,
        faculty: List[FacultyMember],
        announcements: List[str],
        links: List[Dict[str, str]]
    ) -> str:
        if not faculty and not announcements and not links:
            return f"No specific faculty or records found for **\"{query}\"** in the IIT Roorkee ECE Department. Please try browsing the Faculty Directory or searching with broader keywords."

        lines = [f"Here are the most relevant findings for **\"{query}\"** at IIT Roorkee ECE:"]

        if faculty:
            lines.append("\n### Relevant Faculty Members:")
            for f in faculty[:4]:
                interests = ", ".join(f.research_interests[:3]) if f.research_interests else "See official profile"
                lines.append(f"- **{f.name}** ({f.designation})")
                lines.append(f"  - **Email**: `{f.email}`")
                lines.append(f"  - **Areas**: {interests}")
                if f.profile_url:
                    lines.append(f"  - [Official Profile]({f.profile_url})")

        if announcements:
            lines.append("\n### Department Announcements:")
            for a in announcements[:3]:
                lines.append(f"- {a}")

        return "\n".join(lines)
