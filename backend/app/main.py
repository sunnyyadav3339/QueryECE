from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from .data_loader import DataLoader, FacultyMember
from .search_engine import SearchEngine
from .gemini_client import GeminiClient

app = FastAPI(
    title="QueryECE API",
    description="Intelligent search and question-answering assistant for IIT Roorkee ECE Department"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

data_loader = DataLoader.get_instance()
search_engine = SearchEngine(data_loader)
gemini_client = GeminiClient()

class QueryRequest(BaseModel):
    query: str = Field(..., description="User question or search query")
    top_k: int = Field(default=5, description="Number of faculty cards to return")

class QueryResponse(BaseModel):
    query: str
    answer: str
    faculty: List[FacultyMember]
    announcements: List[str]
    links: List[Dict[str, str]]
    total_matches: int

@app.get("/")
def read_root():
    return {
        "status": "QueryECE Backend is running",
        "department": "Electronics and Communication Engineering, IIT Roorkee",
        "faculty_count": len(data_loader.faculty),
        "announcements_count": len(data_loader.static_content.announcements),
        "gemini_active": bool(gemini_client.api_key)
    }

@app.get("/api/faculty", response_model=List[FacultyMember])
def list_faculty(
    q: Optional[str] = Query(None, description="Search query across names, emails, research areas"),
    designation: Optional[str] = Query(None, description="Filter by designation: Professor, Associate Professor, Assistant Professor, etc.")
):
    results = data_loader.faculty

    if designation:
        d_lower = designation.lower()
        results = [f for f in results if d_lower in f.designation.lower()]

    if q:
        search_res = search_engine.search(q, top_k=50)
        results = search_res["faculty"]

    return results

@app.get("/api/faculty/{identifier}", response_model=FacultyMember)
def get_faculty_member(identifier: str):
    ident_lower = identifier.lower().strip()

    # Search by email
    if ident_lower in data_loader.faculty_by_email:
        return data_loader.faculty_by_email[ident_lower]

    # Search by id or partial name
    for f in data_loader.faculty:
        if f.id.lower() == ident_lower or ident_lower in f.name.lower():
            return f

    raise HTTPException(status_code=404, detail=f"Faculty member '{identifier}' not found")

@app.get("/api/announcements")
def get_announcements():
    return {
        "announcements": data_loader.static_content.announcements,
        "links": data_loader.static_content.links
    }

@app.post("/api/query", response_model=QueryResponse)
def handle_query(request: QueryRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    search_res = search_engine.search(request.query, top_k=request.top_k)
    matched_faculty = search_res["faculty"]
    matched_announcements = search_res["announcements"]
    matched_links = search_res["links"]

    # Generate grounded answer via Gemini (with fallback)
    answer = gemini_client.generate_rag_answer(
        query=request.query,
        faculty=matched_faculty,
        announcements=matched_announcements,
        links=matched_links
    )

    return QueryResponse(
        query=request.query,
        answer=answer,
        faculty=matched_faculty,
        announcements=matched_announcements,
        links=matched_links,
        total_matches=search_res["total_matches"]
    )