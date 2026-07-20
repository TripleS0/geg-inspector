"""Persistent bank catalog used by templates and imported files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.services.shared.db.sqlite_client import SqliteClient


BUILTIN_BANKS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("bank_ccb", "建设银行", ("建设银行", "建行", "ccb")),
    ("bank_icbc", "工商银行", ("工商银行", "工行", "icbc")),
    ("bank_cgb", "广发银行", ("广发银行", "广发行", "广发", "cgb")),
    ("bank_abc", "农业银行", ("农业银行", "农行", "abc")),
    ("bank_ceb", "光大银行", ("光大银行", "光大", "ceb", "cebbank")),
)


@dataclass(frozen=True)
class BankCatalogRecord:
    bank_id: str
    display_name: str
    aliases: list[str]
    is_builtin: int
    is_active: int
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class BankCatalogRepository:
    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS meta_bank_catalog (
                bank_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL UNIQUE,
                aliases_json TEXT NOT NULL DEFAULT '[]',
                is_builtin INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        for bank_id, name, aliases in BUILTIN_BANKS:
            self._client.execute(
                """
                INSERT OR IGNORE INTO meta_bank_catalog
                (bank_id, display_name, aliases_json, is_builtin, is_active)
                VALUES (?, ?, ?, 1, 1);
                """,
                (bank_id, name, json.dumps(list(aliases), ensure_ascii=False)),
            )
        self._ensure_column("meta_bank_files", "bank_id", "TEXT")
        self._ensure_column("meta_user_bank_template", "bank_id", "TEXT")
        self._ensure_column("meta_bank_sheets", "selected_template_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("meta_bank_sheets", "template_type", "TEXT NOT NULL DEFAULT 'txn_detail'")
        self._ensure_column("meta_bank_sheets", "template_snapshot_json", "TEXT NOT NULL DEFAULT '{}'")
        self._backfill_legacy_banks()

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        tables = {str(row[0]) for row in self._client.query_all("SELECT name FROM sqlite_master WHERE type='table';")}
        if table not in tables:
            return
        names = {str(row[1]) for row in self._client.query_all(f"PRAGMA table_info({table});")}
        if column not in names:
            self._client.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration};")

    def _backfill_legacy_banks(self) -> None:
        placeholder_names = {"默认来源", "银行数据", "默认银行"}
        names: set[str] = set()
        for table, column in (("meta_bank_files", "bank_name"), ("meta_user_bank_template", "bank_display_name")):
            try:
                names.update(str(row[0]).strip() for row in self._client.query_all(f"SELECT DISTINCT {column} FROM {table};") if row[0])
            except Exception:
                continue
        for name in sorted(names):
            if not self.get_by_name(name):
                created = self.create(name, [name])
                if name in placeholder_names:
                    self._client.execute("UPDATE meta_bank_catalog SET is_active=0 WHERE bank_id=?;", (created.bank_id,))
        for name in placeholder_names:
            self._client.execute("UPDATE meta_bank_catalog SET is_active=0 WHERE display_name=?;", (name,))
        try:
            self._client.execute(
                """UPDATE meta_bank_files
                   SET bank_id=(SELECT bank_id FROM meta_bank_catalog c WHERE c.display_name=meta_bank_files.bank_name)
                   WHERE COALESCE(bank_id, '')='';"""
            )
            self._client.execute(
                """UPDATE meta_user_bank_template
                   SET bank_id=(SELECT bank_id FROM meta_bank_catalog c WHERE c.display_name=meta_user_bank_template.bank_display_name)
                   WHERE COALESCE(bank_id, '')='';"""
            )
        except Exception:
            pass

    @staticmethod
    def _record(row: tuple[object, ...]) -> BankCatalogRecord:
        aliases = json.loads(str(row[2] or "[]"))
        return BankCatalogRecord(str(row[0]), str(row[1]), [str(x) for x in aliases], int(row[3]), int(row[4]), str(row[5]), str(row[6]))

    def list_all(self, active_only: bool = False) -> list[BankCatalogRecord]:
        where = "WHERE is_active=1" if active_only else ""
        rows = self._client.query_all(
            f"SELECT bank_id, display_name, aliases_json, is_builtin, is_active, created_at, updated_at FROM meta_bank_catalog {where} ORDER BY is_active DESC, is_builtin DESC, display_name;"
        )
        return [self._record(row) for row in rows]

    def get(self, bank_id: str) -> BankCatalogRecord | None:
        rows = self._client.query_all(
            "SELECT bank_id, display_name, aliases_json, is_builtin, is_active, created_at, updated_at FROM meta_bank_catalog WHERE bank_id=? LIMIT 1;",
            (bank_id,),
        )
        return self._record(rows[0]) if rows else None

    def get_by_name(self, name: str) -> BankCatalogRecord | None:
        target = name.strip()
        if not target:
            return None
        for item in self.list_all():
            if target == item.display_name or target.lower() in {x.lower() for x in item.aliases}:
                return item
        return None

    def create(self, display_name: str, aliases: list[str] | None = None) -> BankCatalogRecord:
        name = display_name.strip()
        if not name:
            raise ValueError("银行名称不能为空")
        if self.get_by_name(name):
            raise ValueError("银行名称或别名已存在")
        bank_id = f"bank_{uuid4().hex[:12]}"
        now = _now()
        values = list(dict.fromkeys([name, *(aliases or [])]))
        self._client.execute(
            "INSERT INTO meta_bank_catalog (bank_id, display_name, aliases_json, is_builtin, is_active, created_at, updated_at) VALUES (?, ?, ?, 0, 1, ?, ?);",
            (bank_id, name, json.dumps(values, ensure_ascii=False), now, now),
        )
        return self.get(bank_id)  # type: ignore[return-value]

    def update(self, bank_id: str, *, display_name: str | None = None, aliases: list[str] | None = None, is_active: int | None = None) -> BankCatalogRecord:
        current = self.get(bank_id)
        if not current:
            raise ValueError("银行不存在")
        name = (display_name if display_name is not None else current.display_name).strip()
        if current.is_builtin and name != current.display_name:
            raise ValueError("内置银行名称不能修改")
        other = self.get_by_name(name)
        if other and other.bank_id != bank_id:
            raise ValueError("银行名称或别名已存在")
        alias_values = list(dict.fromkeys([name, *(aliases if aliases is not None else current.aliases)]))
        active = int(is_active if is_active is not None else current.is_active)
        self._client.execute(
            "UPDATE meta_bank_catalog SET display_name=?, aliases_json=?, is_active=?, updated_at=? WHERE bank_id=?;",
            (name, json.dumps(alias_values, ensure_ascii=False), active, _now(), bank_id),
        )
        if name != current.display_name:
            for table, column in (("meta_user_bank_template", "bank_display_name"), ("meta_bank_files", "bank_name"), ("meta_schema_registry", "bank_name"), ("std_bank_txn", "bank_name"), ("std_bank_account", "bank_name")):
                try:
                    self._client.execute(f"UPDATE {table} SET {column}=? WHERE {column}=?;", (name, current.display_name))
                except Exception:
                    pass
        try:
            from app.services.integration.bank.template_library import clear_template_cache

            clear_template_cache()
        except Exception:
            pass
        return self.get(bank_id)  # type: ignore[return-value]
