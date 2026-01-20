"""
Search Index Module - Full-text search using Whoosh
"""
import os
import json
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from whoosh import index
from whoosh.fields import Schema, TEXT, ID, DATETIME, STORED, NUMERIC
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.analysis import StandardAnalyzer
from whoosh.writing import AsyncWriter


# Paths
LOGS_DIR = Path(__file__).parent.parent / "chat_logs"
INDEX_DIR = Path(__file__).parent.parent / "search_index"

# Schema for the search index
SCHEMA = Schema(
    filename=ID(stored=True, unique=True),
    room_id=ID(stored=True),
    start_time=STORED,
    messages_count=NUMERIC(stored=True),
    duration=NUMERIC(stored=True),
    file_size=NUMERIC(stored=True),
    # Full-text searchable fields
    content=TEXT(analyzer=StandardAnalyzer(), stored=False),
    room_id_text=TEXT(stored=False),
)


def get_or_create_index():
    """Get existing index or create a new one"""
    if not INDEX_DIR.exists():
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
    
    if index.exists_in(str(INDEX_DIR)):
        return index.open_dir(str(INDEX_DIR))
    else:
        return index.create_in(str(INDEX_DIR), SCHEMA)


def extract_log_data(filepath: Path) -> Optional[Dict[str, Any]]:
    """Extract data from a log file for indexing"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Combine all messages into searchable content
        messages = data.get("messages", [])
        content_parts = []
        for msg in messages:
            message_text = msg.get("message", "")
            sender = msg.get("from", "")
            content_parts.append(f"{sender}: {message_text}")
        
        content = "\n".join(content_parts)
        room_id = data.get("room_id", "")
        
        return {
            "filename": filepath.name,
            "room_id": room_id,
            "room_id_text": room_id,  # For text search on room_id
            "start_time": data.get("start_time"),
            "messages_count": data.get("messages_count", len(messages)),
            "duration": data.get("duration", 0),
            "file_size": filepath.stat().st_size,
            "content": content,
        }
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading {filepath}: {e}")
        return None


def rebuild_index():
    """Rebuild the entire search index from all log files"""
    print("🔍 Building search index...")
    
    if not LOGS_DIR.exists():
        print("  No logs directory found")
        return
    
    # Delete existing index and create fresh
    import shutil
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    
    ix = index.create_in(str(INDEX_DIR), SCHEMA)
    writer = ix.writer()
    
    count = 0
    for filepath in LOGS_DIR.glob("*.json"):
        data = extract_log_data(filepath)
        if data:
            writer.add_document(**data)
            count += 1
    
    writer.commit()
    print(f"  ✓ Indexed {count} log files")


def add_to_index(filename: str):
    """Add a single log file to the index"""
    filepath = LOGS_DIR / filename
    if not filepath.exists():
        return
    
    data = extract_log_data(filepath)
    if not data:
        return
    
    ix = get_or_create_index()
    writer = AsyncWriter(ix)
    
    # Update or add document
    writer.update_document(**data)
    writer.commit()


def remove_from_index(filename: str):
    """Remove a log file from the index"""
    ix = get_or_create_index()
    writer = ix.writer()
    writer.delete_by_term("filename", filename)
    writer.commit()


def search_logs(query_str: str, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    """
    Search logs using Whoosh full-text search
    
    Returns:
        {
            "results": [...],  # List of matching log summaries
            "total": N,        # Total number of matches
            "page": P,
            "limit": L,
            "totalPages": TP
        }
    """
    if not query_str or not query_str.strip():
        return {"results": [], "total": 0, "page": page, "limit": limit, "totalPages": 0}
    
    ix = get_or_create_index()
    
    results_list = []
    total = 0
    
    with ix.searcher() as searcher:
        # Search in content and room_id
        parser = MultifieldParser(
            ["content", "room_id_text"], 
            schema=ix.schema,
            group=OrGroup
        )
        query = parser.parse(query_str)
        
        # Get all results first to count total
        results = searcher.search(query, limit=None)
        total = len(results)
        
        # Calculate pagination
        start = (page - 1) * limit
        end = start + limit
        
        for hit in results[start:end]:
            results_list.append({
                "filename": hit["filename"],
                "room_id": hit["room_id"],
                "start_time": hit["start_time"],
                "messages_count": hit["messages_count"],
                "duration": hit["duration"],
                "file_size": hit["file_size"],
            })
    
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    
    return {
        "results": results_list,
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": total_pages
    }


def get_index_stats() -> Dict[str, Any]:
    """Get statistics about the search index"""
    ix = get_or_create_index()
    with ix.searcher() as searcher:
        return {
            "indexed_documents": searcher.doc_count(),
            "index_path": str(INDEX_DIR),
        }


# Auto-rebuild index if it doesn't exist or is empty
def ensure_index():
    """Ensure index exists and has documents"""
    if not INDEX_DIR.exists() or not index.exists_in(str(INDEX_DIR)):
        rebuild_index()
        return
    
    ix = get_or_create_index()
    with ix.searcher() as searcher:
        if searcher.doc_count() == 0:
            rebuild_index()
