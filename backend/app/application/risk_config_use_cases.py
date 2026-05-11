"""Commercial risk rule configuration (cfg_risk_rule)."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.application.bootstrap import bootstrap_database
from app.services.shared.db.sqlite_client import SqliteClient


class RiskConfigUseCase:
    """List and update risk rule parameters for commercial analysis."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def list_rules(self) -> list[dict[str, Any]]:
        rows = self._client.query_all(
            """
            SELECT rule_code, rule_name, enabled, weight, params_json, version
            FROM cfg_risk_rule ORDER BY rule_code;
            """
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                params = json.loads(r[4] or "{}")
            except json.JSONDecodeError:
                params = {}
            out.append(
                {
                    "rule_code": str(r[0]),
                    "rule_name": str(r[1]),
                    "enabled": int(r[2]),
                    "weight": float(r[3]),
                    "params": params,
                    "version": int(r[5]),
                }
            )
        return out

    def patch_rule(
        self,
        rule_code: str,
        *,
        params: Optional[dict[str, Any]] = None,
        weight: Optional[float] = None,
        enabled: Optional[int] = None,
    ) -> dict[str, Any]:
        code = (rule_code or "").strip()
        if not code:
            raise ValueError("rule_code 不能为空")
        existing = self._client.query_all(
            "SELECT params_json, weight, enabled FROM cfg_risk_rule WHERE rule_code=?;",
            (code,),
        )
        if not existing:
            raise ValueError(f"规则不存在: {code}")
        cur_p, cur_w, cur_e = existing[0]
        try:
            merged: dict[str, Any] = json.loads(cur_p or "{}")
        except json.JSONDecodeError:
            merged = {}
        if params is not None:
            merged = dict(params)
        w = float(cur_w) if weight is None else float(weight)
        e = int(cur_e) if enabled is None else (1 if int(enabled) else 0)
        self._client.execute(
            """
            UPDATE cfg_risk_rule
            SET params_json=?, weight=?, enabled=?, updated_at=CURRENT_TIMESTAMP, version=version+1
            WHERE rule_code=?;
            """,
            (json.dumps(merged, ensure_ascii=False), w, e, code),
        )
        return {"rule_code": code, "weight": w, "enabled": e, "params": merged}
