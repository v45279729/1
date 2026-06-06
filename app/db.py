from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import mysql.connector

from app.config import get_database_config


class Database:
    # Единый небольшой слой доступа к MySQL: открывает соединение на каждый запрос
    # и закрывает его сразу после выполнения.
    def __init__(self) -> None:
        self.config = get_database_config(include_database=True)

    def get_connection(self):
        return mysql.connector.connect(**self.config)

    # Используется для запросов, которые должны вернуть одну строку.
    def fetch_one(self, query: str, params: Iterable[Any] | None = None) -> dict | None:
        connection = self.get_connection()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query, tuple(params or ()))
            return cursor.fetchone()
        finally:
            connection.close()

    # Используется для списков: товары, заказы, справочники.
    def fetch_all(self, query: str, params: Iterable[Any] | None = None) -> list[dict]:
        connection = self.get_connection()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query, tuple(params or ()))
            return cursor.fetchall()
        finally:
            connection.close()

    # Выполняет INSERT/UPDATE/DELETE и возвращает id новой записи, если он есть.
    def execute(self, query: str, params: Iterable[Any] | None = None) -> int:
        connection = self.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(query, tuple(params or ()))
            connection.commit()
            return int(cursor.lastrowid or 0)
        finally:
            connection.close()
