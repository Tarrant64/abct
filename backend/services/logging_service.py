"""
Centralized Logging Service

Provides centralized logging for the entire application with:
- In-memory circular buffer for recent logs (last 1000 entries)
- SQLite persistence for error logs
- Log levels: ERROR, WARNING, INFO, DEBUG
- Sanitized tracebacks (removes file paths, secrets)
- Real-time log streaming via SSE
- Automatic log rotation

Security features:
- Redacts sensitive data (API keys, passwords, wallet addresses)
- Removes absolute file paths
- Sanitizes environment variables
- Safe traceback formatting
"""

import re
import sys
import os
import traceback
import asyncio
import aiosqlite
from typing import List, Dict, Optional, Any
from datetime import datetime
from collections import deque
from pathlib import Path
from enum import Enum

# Add backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR


class LogLevel(str, Enum):
    """Log severity levels."""
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"


class LogEntry:
    """Represents a single log entry."""

    def __init__(
        self,
        level: LogLevel,
        source: str,
        message: str,
        traceback_str: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        self.id = None  # Set when stored in DB
        self.timestamp = datetime.utcnow()
        self.level = level
        self.source = source
        self.message = self._sanitize_message(message)
        self.traceback = self._sanitize_traceback(traceback_str) if traceback_str else None
        self.extra = extra or {}

    def _sanitize_message(self, message: str) -> str:
        """Remove sensitive data from log messages."""
        if not message:
            return ""

        # Remove API keys (patterns like: api_key=xxx, apiKey: xxx, etc.)
        message = re.sub(
            r'(api[_-]?key|token|secret|password|pwd)["\s:=]+["\']?[\w-]+["\']?',
            r'\1=***REDACTED***',
            message,
            flags=re.IGNORECASE
        )

        # Remove wallet addresses (Cardano, Bitcoin, Ethereum patterns)
        message = re.sub(r'addr1[a-z0-9]{50,}', 'addr1***REDACTED***', message)  # Cardano (50+ chars after addr1)
        message = re.sub(r'[13][a-km-zA-HJ-NP-Z1-9]{25,34}', '***BTC_ADDRESS***', message)  # Bitcoin
        message = re.sub(r'0x[a-fA-F0-9]{40}', '0x***ETH_ADDRESS***', message)  # Ethereum

        # Remove absolute file paths (keep relative paths for context)
        # Match any absolute path with backend/frontend in it
        message = re.sub(r'/[^"\s]+/(backend|frontend)/', r'.../\1/', message)
        message = re.sub(r'C:\\[^"\s]+\\(backend|frontend)\\', r'...\\\\\\1\\\\', message)
        message = re.sub(r'/[^"\s]+/(Deployment)/', r'.../\1/', message)  # Also handle Deployment paths

        return message

    def _sanitize_traceback(self, tb_str: str) -> str:
        """Sanitize traceback to remove sensitive paths and data."""
        if not tb_str:
            return ""

        # Remove absolute file paths, keep relative structure
        tb_str = re.sub(r'File "(/[^"]+/(backend|frontend)/)', r'File ".../\2/', tb_str)
        tb_str = re.sub(r'File "(/[^"]+/(Deployment)/)', r'File ".../\2/', tb_str)
        tb_str = re.sub(r'File "(C:\\[^"]+\\(backend|frontend)\\)', r'File "...\\\\\\2\\\\', tb_str)

        # Remove environment variable values
        tb_str = re.sub(r"os\.environ\[.*?\] = ['\"].*?['\"]", "os.environ[***] = ***", tb_str)

        # Sanitize the actual error messages in traceback
        tb_str = self._sanitize_message(tb_str)

        return tb_str

    def to_dict(self) -> Dict[str, Any]:
        """Convert log entry to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "source": self.source,
            "message": self.message,
            "traceback": self.traceback,
            "extra": self.extra
        }


class LoggingService:
    """Centralized logging service with in-memory buffer and persistent storage."""

    def __init__(self, db_path: Optional[Path] = None, buffer_size: int = 1000):
        """
        Initialize logging service.

        Args:
            db_path: Path to SQLite database for persistent logs
            buffer_size: Maximum number of entries to keep in memory
        """
        self.db_path = db_path or (DATA_DIR / "logs.db")
        self.buffer_size = buffer_size
        self.buffer: deque[LogEntry] = deque(maxlen=buffer_size)
        self.subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize database schema."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    traceback TEXT,
                    extra TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for faster queries
            await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_source ON logs(source)")

            await db.commit()

        self._initialized = True

    async def log(
        self,
        level: LogLevel,
        source: str,
        message: str,
        exc_info: Optional[Exception] = None,
        **extra
    ):
        """
        Log a message.

        Args:
            level: Log level (ERROR, WARNING, INFO, DEBUG)
            source: Source module/component (e.g., "wallets", "nft", "main")
            message: Log message
            exc_info: Exception object (will extract traceback)
            **extra: Additional context data
        """
        if not self._initialized:
            await self.initialize()

        # Format traceback if exception provided
        traceback_str = None
        if exc_info:
            traceback_str = ''.join(traceback.format_exception(
                type(exc_info),
                exc_info,
                exc_info.__traceback__
            ))

        entry = LogEntry(level, source, message, traceback_str, extra)

        # Add to in-memory buffer
        async with self._lock:
            self.buffer.append(entry)

            # Persist ERROR and WARNING to database
            if level in (LogLevel.ERROR, LogLevel.WARNING):
                await self._persist_entry(entry)

            # Notify subscribers (for real-time streaming)
            await self._notify_subscribers(entry)

    async def _persist_entry(self, entry: LogEntry):
        """Persist log entry to database."""
        import json

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO logs (timestamp, level, source, message, traceback, extra)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                entry.timestamp.isoformat(),
                entry.level.value,
                entry.source,
                entry.message,
                entry.traceback,
                json.dumps(entry.extra) if entry.extra else None
            ))

            entry.id = cursor.lastrowid
            await db.commit()

    async def _notify_subscribers(self, entry: LogEntry):
        """Notify all SSE subscribers of new log entry."""
        dead_queues = []

        for queue in self.subscribers:
            try:
                await queue.put(entry)
            except Exception:
                dead_queues.append(queue)

        # Clean up dead subscribers
        for queue in dead_queues:
            self.subscribers.remove(queue)

    async def get_recent(
        self,
        limit: int = 100,
        level: Optional[LogLevel] = None,
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent log entries from in-memory buffer.

        Args:
            limit: Maximum number of entries to return
            level: Filter by log level
            source: Filter by source

        Returns:
            List of log entry dictionaries
        """
        async with self._lock:
            entries = list(self.buffer)

        # Apply filters
        if level:
            entries = [e for e in entries if e.level == level]
        if source:
            entries = [e for e in entries if e.source == source]

        # Sort by timestamp (newest first) and limit
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        entries = entries[:limit]

        return [e.to_dict() for e in entries]

    async def get_from_db(
        self,
        limit: int = 100,
        offset: int = 0,
        level: Optional[LogLevel] = None,
        source: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Query logs from database with filtering and pagination.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            level: Filter by log level
            source: Filter by source
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            Dictionary with 'logs' list and 'total' count
        """
        import json

        if not self._initialized:
            await self.initialize()

        # Build WHERE clause
        where_clauses = []
        params = []

        if level:
            where_clauses.append("level = ?")
            params.append(level.value)
        if source:
            where_clauses.append("source = ?")
            params.append(source)
        if start_time:
            where_clauses.append("timestamp >= ?")
            params.append(start_time.isoformat())
        if end_time:
            where_clauses.append("timestamp <= ?")
            params.append(end_time.isoformat())

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        async with aiosqlite.connect(self.db_path) as db:
            # Get total count
            cursor = await db.execute(f"SELECT COUNT(*) FROM logs WHERE {where_sql}", params)
            row = await cursor.fetchone()
            total = row[0] if row else 0

            # Get paginated results
            query = f"""
                SELECT id, timestamp, level, source, message, traceback, extra
                FROM logs
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """
            cursor = await db.execute(query, params + [limit, offset])
            rows = await cursor.fetchall()

            logs = []
            for row in rows:
                logs.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "level": row[2],
                    "source": row[3],
                    "message": row[4],
                    "traceback": row[5],
                    "extra": json.loads(row[6]) if row[6] else {}
                })

            return {
                "logs": logs,
                "total": total,
                "limit": limit,
                "offset": offset
            }

    async def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to real-time log stream.

        Returns:
            Queue that will receive new log entries
        """
        queue = asyncio.Queue(maxsize=100)
        self.subscribers.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from log stream."""
        if queue in self.subscribers:
            self.subscribers.remove(queue)

    async def clear_buffer(self):
        """Clear in-memory log buffer."""
        async with self._lock:
            self.buffer.clear()

    async def clear_db(self, older_than_days: Optional[int] = None):
        """
        Clear database logs.

        Args:
            older_than_days: If provided, only delete logs older than this many days
        """
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            if older_than_days:
                cutoff = datetime.utcnow().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                cutoff = cutoff.replace(day=cutoff.day - older_than_days)
                await db.execute(
                    "DELETE FROM logs WHERE timestamp < ?",
                    (cutoff.isoformat(),)
                )
            else:
                await db.execute("DELETE FROM logs")

            await db.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """Get logging statistics."""
        async with self._lock:
            buffer_count = len(self.buffer)
            buffer_by_level = {}
            for entry in self.buffer:
                level = entry.level.value
                buffer_by_level[level] = buffer_by_level.get(level, 0) + 1

        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            # Total count in DB
            cursor = await db.execute("SELECT COUNT(*) FROM logs")
            row = await cursor.fetchone()
            db_count = row[0] if row else 0

            # Count by level
            cursor = await db.execute("""
                SELECT level, COUNT(*) as count
                FROM logs
                GROUP BY level
            """)
            rows = await cursor.fetchall()
            db_by_level = {row[0]: row[1] for row in rows}

            # Count by source
            cursor = await db.execute("""
                SELECT source, COUNT(*) as count
                FROM logs
                GROUP BY source
                ORDER BY count DESC
                LIMIT 10
            """)
            rows = await cursor.fetchall()
            top_sources = [{"source": row[0], "count": row[1]} for row in rows]

        return {
            "buffer": {
                "total": buffer_count,
                "max_size": self.buffer_size,
                "by_level": buffer_by_level
            },
            "database": {
                "total": db_count,
                "by_level": db_by_level,
                "top_sources": top_sources
            },
            "subscribers": len(self.subscribers)
        }

    # Convenience methods for different log levels
    async def error(self, source: str, message: str, exc_info: Optional[Exception] = None, **extra):
        """Log an error message."""
        await self.log(LogLevel.ERROR, source, message, exc_info, **extra)

    async def warning(self, source: str, message: str, exc_info: Optional[Exception] = None, **extra):
        """Log a warning message."""
        await self.log(LogLevel.WARNING, source, message, exc_info, **extra)

    async def info(self, source: str, message: str, **extra):
        """Log an info message."""
        await self.log(LogLevel.INFO, source, message, **extra)

    async def debug(self, source: str, message: str, **extra):
        """Log a debug message."""
        await self.log(LogLevel.DEBUG, source, message, **extra)


# Global singleton instance
_logging_service: Optional[LoggingService] = None


def get_logging_service() -> LoggingService:
    """Get the global logging service instance."""
    global _logging_service
    if _logging_service is None:
        _logging_service = LoggingService()
    return _logging_service
