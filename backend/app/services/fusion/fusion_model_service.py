"""Case-level fusion model configuration."""

from __future__ import annotations

import json
from typing import Any

from app.services.fusion.model_catalog import CATALOG_BY_KEY, FUSION_MODEL_CATALOG, FusionModelDef
from app.services.shared.db.sqlite_client import SqliteClient


class FusionModelService:
    def __init__(self, client: SqliteClient) -> None:
        self._client = client

    def list_models(self, case_id: int) -> dict[str, Any]:
        saved = self._load_saved(case_id)
        risk_rules = self._load_risk_rules()
        items: list[dict[str, Any]] = []
        categories: dict[str, dict[str, Any]] = {}

        for model_def in FUSION_MODEL_CATALOG:
            saved_row = saved.get(model_def.key)
            enabled = bool(saved_row["enabled"]) if saved_row else model_def.default_enabled
            params = dict(model_def.default_params)
            if saved_row and saved_row.get("params"):
                params.update(saved_row["params"])

            if model_def.key.startswith("risk_"):
                rule_code = model_def.key.replace("risk_", "")
                rule = risk_rules.get(rule_code)
                if rule:
                    if not saved_row:
                        enabled = bool(rule.get("enabled", 1))
                    params = dict(rule.get("params") or {})
                    if rule.get("weight") is not None:
                        params["weight"] = rule["weight"]
                if saved_row and saved_row.get("params"):
                    params.update(saved_row["params"])

            item = {
                "model_key": model_def.key,
                "name": model_def.name,
                "category": model_def.category,
                "category_label": model_def.category_label,
                "description": model_def.description,
                "event_type_label": model_def.event_type_label,
                "param_schema": list(model_def.param_schema),
                "enabled": enabled,
                "params": params,
            }
            items.append(item)

            cat = categories.setdefault(
                model_def.category,
                {"category": model_def.category, "category_label": model_def.category_label, "models": []},
            )
            cat["models"].append(item)

        return {
            "case_id": case_id,
            "items": items,
            "categories": list(categories.values()),
        }

    def save_models(self, case_id: int, updates: list[dict[str, Any]]) -> dict[str, Any]:
        for update in updates:
            model_key = str(update.get("model_key") or "")
            if model_key not in CATALOG_BY_KEY:
                continue
            enabled = 1 if update.get("enabled", True) else 0
            params = update.get("params") or {}
            params_json = json.dumps(params, ensure_ascii=False)
            self._client.execute(
                """
                INSERT INTO cfg_fusion_model(case_id, model_key, enabled, params_json, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(case_id, model_key) DO UPDATE SET
                    enabled=excluded.enabled,
                    params_json=excluded.params_json,
                    updated_at=datetime('now');
                """,
                (case_id, model_key, enabled, params_json),
            )

            if model_key.startswith("risk_"):
                rule_code = model_key.replace("risk_", "")
                weight = params.get("weight")
                patch_params = {k: v for k, v in params.items() if k != "weight"}
                sets = ["enabled=?"]
                args: list[Any] = [enabled]
                if patch_params:
                    sets.append("params_json=?")
                    args.append(json.dumps(patch_params, ensure_ascii=False))
                if weight is not None:
                    sets.append("weight=?")
                    args.append(float(weight))
                sets.append("version=version+1")
                sets.append("updated_at=datetime('now')")
                args.append(rule_code)
                self._client.execute(
                    f"UPDATE cfg_risk_rule SET {', '.join(sets)} WHERE rule_code=?;",
                    tuple(args),
                )

        return self.list_models(case_id)

    def enabled_model_map(self, case_id: int) -> dict[str, dict[str, Any]]:
        payload = self.list_models(case_id)
        return {
            str(item["model_key"]): item
            for item in payload["items"]
            if item.get("enabled")
        }

    def _load_saved(self, case_id: int) -> dict[str, dict[str, Any]]:
        rows = self._client.query_all(
            "SELECT model_key, enabled, params_json FROM cfg_fusion_model WHERE case_id=?;",
            (case_id,),
        )
        out: dict[str, dict[str, Any]] = {}
        for key, enabled, params_json in rows:
            try:
                params = json.loads(params_json or "{}")
            except json.JSONDecodeError:
                params = {}
            out[str(key)] = {"enabled": int(enabled or 0), "params": params}
        return out

    def _load_risk_rules(self) -> dict[str, dict[str, Any]]:
        rows = self._client.query_all(
            "SELECT rule_code, enabled, weight, params_json FROM cfg_risk_rule ORDER BY rule_code;"
        )
        out: dict[str, dict[str, Any]] = {}
        for code, enabled, weight, params_json in rows:
            try:
                params = json.loads(params_json or "{}")
            except json.JSONDecodeError:
                params = {}
            out[str(code)] = {
                "enabled": int(enabled or 0),
                "weight": float(weight or 1.0),
                "params": params,
            }
        return out

    @staticmethod
    def params_to_module_params(params: dict[str, Any]) -> Any:
        from app.services.integration.bank.analysis_modules import ModuleParams

        whitelist = params.get("special_amount_whitelist")
        if isinstance(whitelist, list):
            whitelist_tuple = tuple(float(v) for v in whitelist)
        else:
            whitelist_tuple = ModuleParams().special_amount_whitelist
        return ModuleParams(
            large_amount_threshold=float(params.get("large_amount_threshold", 100_000.0)),
            top_n=int(params.get("top_n", 15)),
            repeat_amount_min_count=int(params.get("repeat_amount_min_count", 3)),
            special_amount_whitelist=whitelist_tuple,
        )
