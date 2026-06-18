#!/usr/bin/env python3
"""Clear old mock batches, import mock-data fixtures, bind case, run auto-link."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.application.case_use_cases import CaseUseCase
from app.application.dataset_use_cases import DatasetUseCase
from app.application.fusion_use_cases import FusionUseCase
from app.application.import_use_cases import EnterpriseImportUseCase, ImportUseCase
from app.services.shared.db.sqlite_client import SqliteClient

MOCK_DIR = ROOT / "mock-data"
CASE_NAME = "融合调查演示案"

IMPORTS = [
    ("enterprise", EnterpriseImportUseCase, [MOCK_DIR / "01_enterprise_工商主体.xlsx"], None, None),
    ("commercial", ImportUseCase, [MOCK_DIR / "02_commercial_商务网询价.xlsx"], "广东电力商务网", "commercial"),
    ("bank", ImportUseCase, [MOCK_DIR / "03_bank_多人流水_建设银行.xlsx"], "建设银行", "bank"),
    ("wechat", ImportUseCase, [MOCK_DIR / "04_wechat_多人转账.xlsx"], "微信支付", "wechat"),
    ("telecom", ImportUseCase, [MOCK_DIR / "05_telecom_多人话单.xlsx"], "广东移动", "telecom"),
]


def _require_files() -> None:
    paths = [
        MOCK_DIR / "01_enterprise_工商主体.xlsx",
        MOCK_DIR / "02_commercial_商务网询价.xlsx",
        MOCK_DIR / "03_bank_多人流水_建设银行.xlsx",
        MOCK_DIR / "04_wechat_多人转账.xlsx",
        MOCK_DIR / "05_telecom_多人话单.xlsx",
    ]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"缺少 mock 文件，请先运行 generate_mock_data.py：\n" + "\n".join(missing))


def _wipe_cases_and_batches(client: SqliteClient) -> None:
    case_uc = CaseUseCase(client)
    dataset_uc = DatasetUseCase(client)
    for case in case_uc.list_cases():
        print(f"  删除案件: {case.case_name} (id={case.case_id})")
        case_uc.delete_case(case.case_id)
    for batch in dataset_uc.list_batches_merged(limit=500):
        print(f"  删除批次: {batch.import_batch_id} ({batch.source_type})")
        dataset_uc.delete_import_batch(batch.import_batch_id)


def main() -> None:
    _require_files()
    client = SqliteClient()
    print("清理旧案件与批次…")
    _wipe_cases_and_batches(client)

    batch_ids: list[str] = []
    print("\n导入 mock 数据…")
    for label, uc_cls, paths, bank_name, source_type in IMPORTS:
        paths_str = [str(p.resolve()) for p in paths]
        uc = uc_cls(client)
        if label == "enterprise":
            summary = uc.import_enterprise_profiles(paths_str)
        else:
            summary = uc.import_source(file_paths=paths_str, bank_name=bank_name or "", source_type=source_type or "bank")
        batch_ids.append(summary.import_batch_id)
        extra = ""
        if hasattr(summary, "standardized_rows") and summary.standardized_rows:
            extra = f", 标准化 {summary.standardized_rows} 行"
        print(f"  [{label}] batch={summary.import_batch_id}, rows={summary.rows_total}{extra}")

    case_uc = CaseUseCase(client)
    fusion_uc = FusionUseCase(client)
    case = case_uc.create_case(
        case_name=CASE_NAME,
        description="12人跨源关联演示剧本（工商/商务/银行/微信/话单）",
    )
    case_uc.bind_batches(case.case_id, batch_ids)
    print(f"\n创建案件: {case.case_name} (id={case.case_id}), 绑定 {len(batch_ids)} 个批次")

    discover = fusion_uc.discover(case.case_id)
    auto = fusion_uc.auto_link(case.case_id, rediscover=False)
    persons = fusion_uc.list_persons(case.case_id)
    pending = fusion_uc.list_candidates(case.case_id, review_status="pending")

    print("\n关联结果:")
    print(f"  候选发现: inserted={discover.get('inserted')}, skipped={discover.get('skipped')}")
    print(f"  机器预关联: 新建人物={auto.get('persons_created')}, 关联={auto.get('links_created')}, 剩余候选={auto.get('unresolved_pending')}")
    print(f"  人物数: {len(persons)}")
    for p in persons[:15]:
        links = p.get("links") or []
        kinds = sorted({str(lk.get("identifier_type") or "") for lk in links if lk})
        print(f"    - {p.get('display_name')}: {len(links)} 标识 ({', '.join(k for k in kinds if k)})")
    if len(persons) > 15:
        print(f"    … 共 {len(persons)} 人")
    print(f"  待处理候选: {len(pending)}")
    print(f"\n完成。案件 ID={case.case_id}，可在「人物关联」与「融合驾驶舱」查看。")


if __name__ == "__main__":
    main()
