"""Simulation persistence.

Local development uses SQLite.  Set DATABASE_URL to a Neon/PostgreSQL URL for
Vercel or any other serverless deployment; serverless filesystems are ephemeral.
"""
import json
import os
import sqlite3
import uuid
from pathlib import Path

DB = Path(__file__).resolve().parents[3] / "policyripple.db"


def _database_url():
    return os.getenv("DATABASE_URL", "").strip()


def _is_postgres():
    return _database_url().startswith(("postgres://", "postgresql://"))


def _pg_connection():
    # Lazy import keeps the local SQLite path dependency-free at runtime.
    import psycopg
    return psycopg.connect(_database_url())


def init_db():
    if _is_postgres():
        with _pg_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS simulations (
                        id TEXT PRIMARY KEY,
                        config JSONB NOT NULL,
                        result JSONB
                    )
                    """
                )
        return
    with sqlite3.connect(DB) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS simulations(id TEXT PRIMARY KEY,config TEXT,result TEXT)"
        )


def create(cfg):
    simulation_id = str(uuid.uuid4())
    config = cfg.model_dump_json()
    if _is_postgres():
        with _pg_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO simulations(id, config, result) VALUES (%s, %s::jsonb, NULL)",
                    (simulation_id, config),
                )
        return simulation_id
    with sqlite3.connect(DB) as connection:
        connection.execute(
            "INSERT INTO simulations VALUES(?,?,?)", (simulation_id, config, None)
        )
    return simulation_id


def get(simulation_id):
    if _is_postgres():
        with _pg_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, config::text, result::text FROM simulations WHERE id=%s",
                    (simulation_id,),
                )
                return cursor.fetchone()
    with sqlite3.connect(DB) as connection:
        return connection.execute(
            "SELECT id,config,result FROM simulations WHERE id=?", (simulation_id,)
        ).fetchone()


def save(simulation_id, result):
    encoded_result = json.dumps(result)
    if _is_postgres():
        with _pg_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE simulations SET result=%s::jsonb WHERE id=%s",
                    (encoded_result, simulation_id),
                )
        return
    with sqlite3.connect(DB) as connection:
        connection.execute(
            "UPDATE simulations SET result=? WHERE id=?", (encoded_result, simulation_id)
        )
