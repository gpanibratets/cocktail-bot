"""
Простейшая система аналитики для Telegram-бота.

Сохраняет события в локальную базу SQLite (`analytics.db`), чтобы потом
можно было строить отчёты:
- количество уникальных пользователей;
- количество обращений;
- разрез по времени (по timestamp в событиях).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sqlite3
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Analytics:
    """Хранение простой аналитики в SQLite."""

    def __init__(self, db_path: str = "analytics.db") -> None:
        self._db_path = db_path
        # SQLite по умолчанию не потокобезопасен, поэтому:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

    def _init_db(self) -> None:
        """Создание таблиц, если их ещё нет."""
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at  TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    ts         TEXT NOT NULL,
                    payload    TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                """
            )

    def log_event(
        self,
        user_id: int,
        username: Optional[str],
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Сохранить событие в базу.

        :param user_id: Telegram user id
        :param username: @username, если есть
        :param event_type: тип события, например: "command_start", "command_random"
        :param payload: дополнительная информация (поисковый запрос и т.п.)
        """
        try:
            now = _dt.datetime.utcnow().isoformat(timespec="seconds")
            payload_json = (
                json.dumps(payload, ensure_ascii=False) if payload is not None else None
            )

            with self._lock, self._conn:
                # Обновляем информацию о пользователе
                self._conn.execute(
                    """
                    INSERT INTO users (user_id, username, first_seen_at, last_seen_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (user_id, username, now, now),
                )

                # Записываем событие
                self._conn.execute(
                    """
                    INSERT INTO events (user_id, event_type, ts, payload)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, event_type, now, payload_json),
                )
        except Exception as exc:
            # Не ломаем работу бота из‑за проблем с аналитикой
            logger.error("Failed to log analytics event: %s", exc)


# Глобальный экземпляр для удобного импорта
analytics = Analytics()

