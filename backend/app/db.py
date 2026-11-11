"""Banco de dados SQLite (SQLModel) e modelos."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = os.getenv("PRONTUARIO_DB", str(DATA_DIR / "prontuario.db"))
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    birth_date: str = ""
    phone: str = ""
    email: str = ""
    profession: str = ""
    consent_lgpd: bool = False
    consent_at: str = ""
    created_at: str = Field(default_factory=now)
    anamnese: dict = Field(default_factory=dict, sa_column=Column(JSON))   # {campo: {value, source, ...}}
    alerts: list = Field(default_factory=list, sa_column=Column(JSON))
    main_complaint: str = ""
    mtc_patterns: list = Field(default_factory=list, sa_column=Column(JSON))
    points: list = Field(default_factory=list, sa_column=Column(JSON))
    smoking: str = ""
    last_session_at: str = ""
    session_count: int = 0
    last_eva: Optional[int] = None
    search_text: str = ""


class ConsultaSession(SQLModel, table=True):
    __tablename__ = "consulta"
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: Optional[int] = Field(default=None, index=True)
    kind: str = "anamnese"            # anamnese | soap
    status: str = "draft"             # draft | saved
    started_at: str = Field(default_factory=now)
    saved_at: str = ""
    updated_at: str = Field(default_factory=now)
    duration_s: int = 0
    patient_data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    form: dict = Field(default_factory=dict, sa_column=Column(JSON))
    transcript: list = Field(default_factory=list, sa_column=Column(JSON))
    pipeline: dict = Field(default_factory=dict, sa_column=Column(JSON))
    summary: str = ""
    eva: Optional[int] = None
    llm_used: bool = False


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    at: str = Field(default_factory=now)
    patient_id: Optional[int] = None
    session_id: Optional[int] = None
    action: str = ""
    field: str = ""
    old: Any = Field(default=None, sa_column=Column(JSON))
    new: Any = Field(default=None, sa_column=Column(JSON))
    source: str = ""


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))


class LabCache(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))
    at: str = Field(default_factory=now)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as s:
        yield s


DEFAULT_SETTINGS = {"clinic_name": "Clínica Qi — Acupuntura", "professional_name": "Dr(a). Acupunturista", "speech_lang": "pt-BR",
                    "clinic_address": "", "clinic_phone": ""}


def get_setting(s: Session, key: str):
    row = s.get(AppSetting, key)
    return row.value if row else DEFAULT_SETTINGS.get(key)


def all_settings(s: Session) -> dict:
    return {k: get_setting(s, k) for k in DEFAULT_SETTINGS}


def audit(s: Session, action: str, patient_id=None, session_id=None, field="", old=None, new=None, source="manual") -> None:
    s.add(AuditLog(action=action, patient_id=patient_id, session_id=session_id, field=field, old=old, new=new, source=source))
