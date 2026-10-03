import re
from typing import List, Tuple, Dict, Any
from .data_loader import DataLoader, FacultyMember

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it", "its",
    "itself", "let", "me", "more", "most", "my", "myself", "no", "nor", "not", "of",
    "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "with", "would", "you", "your", "yours", "yourself", "yourselves",
    "prof", "professor", "dr", "tell", "work", "works", "working", "department",
    "ece", "iit", "roorkee", "iitr"
}

class SearchEngine:
    def __init__(self, data_loader: DataLoader):
        self.loader = data_loader

    def search(self, query: str, top_k: int = 6) -> Dict[str, Any]:
        query_clean = query.strip()
        tokens = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9_-]+\b', query_clean) if len(w) > 1]
        search_terms = [t for t in tokens if t not in STOP_WORDS] or tokens

        faculty_scores: List[Tuple[FacultyMember, float]] = []

        query_lower = query_clean.lower()

        for member in self.loader.faculty:
            score = 0.0
            name_lower = member.name.lower()
            desig_lower = member.designation.lower()
            email_lower = member.email.lower()
            interests_str = " ".join(member.research_interests).lower()
            raw_lower = member.raw_text.lower()

            # Exact full name match bonus
            if name_lower and name_lower in query_lower:
                score += 50.0

            # Direct designation query (e.g. "head of department")
            if "head" in query_lower and "head" in desig_lower:
                score += 30.0

            # Query terms matching
            for term in search_terms:
                if term in name_lower:
                    score += 15.0
                if term in email_lower:
                    score += 10.0
                if term in interests_str:
                    score += 12.0
                if term in desig_lower:
                    score += 5.0
                if term in raw_lower:
                    # frequency count (capped at 5)
                    count = min(raw_lower.count(term), 5)
                    score += count * 1.5

            if score > 0:
                faculty_scores.append((member, score))

        faculty_scores.sort(key=lambda x: x[1], reverse=True)
        top_faculty = [f[0] for f in faculty_scores[:top_k]]

        # Search static announcements
        matched_announcements = []
        for ann in self.loader.static_content.announcements:
            ann_lower = ann.lower()
            if any(term in ann_lower for term in search_terms):
                matched_announcements.append(ann)

        # Search static links
        matched_links = []
        for l in self.loader.static_content.links:
            text_lower = l.get("text", "").lower()
            if any(term in text_lower for term in search_terms):
                matched_links.append(l)

        return {
            "query": query,
            "faculty": top_faculty,
            "announcements": matched_announcements[:4],
            "links": matched_links[:5],
            "total_matches": len(faculty_scores)
        }
