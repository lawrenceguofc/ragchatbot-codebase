from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class SessionData:
    """Stores summary-based context and metadata for a session"""

    summary: str      # rolling summary of the conversation
    title: str        # first user message, truncated to 50 chars
    created_at: str   # ISO format timestamp


class SessionManager:
    """Manages conversation sessions using rolling summaries"""

    def __init__(self):
        self.sessions: Dict[str, SessionData] = {}
        self.session_counter = 0

    def create_session(self) -> str:
        """Create a new conversation session"""
        self.session_counter += 1
        session_id = f"session_{self.session_counter}"
        self.sessions[session_id] = SessionData(
            summary="",
            title="New Chat",
            created_at=datetime.now().isoformat(),
        )
        return session_id

    def set_title(self, session_id: str, title: str):
        """Set the display title for a session (called on first user message)"""
        if session_id in self.sessions:
            self.sessions[session_id].title = title

    def update_summary(self, session_id: str, new_summary: str):
        """Store an updated conversation summary for a session"""
        if session_id in self.sessions:
            self.sessions[session_id].summary = new_summary

    def get_conversation_history(self, session_id: Optional[str]) -> Optional[str]:
        """Get the conversation summary for a session, or None if empty"""
        if not session_id or session_id not in self.sessions:
            return None
        summary = self.sessions[session_id].summary
        return summary if summary else None

    def get_all_sessions(self) -> List[Dict]:
        """Return metadata for all sessions that have at least one exchange"""
        return [
            {
                "session_id": sid,
                "title": data.title,
                "created_at": data.created_at,
                "summary": data.summary,
            }
            for sid, data in self.sessions.items()
            if data.summary  # only sessions with at least one completed exchange
        ]

    def delete_session(self, session_id: str):
        """Remove a session entirely"""
        self.sessions.pop(session_id, None)

    def clear_session(self, session_id: str):
        """Reset the summary for a session without deleting it"""
        if session_id in self.sessions:
            self.sessions[session_id].summary = ""
