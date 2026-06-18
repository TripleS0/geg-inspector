#!/usr/bin/env python3
"""Generate rich cross-linked mock Excel fixtures for DataFusionX fusion cockpit demos."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "mock-data"
sys_path = ROOT / "backend"
import sys

sys.path.insert(0, str(sys_path))

random.seed(20250603)

# 12 人：3 核心 + 9 关联，均可做姓名-手机-微信-银行卡关联
PEOPLE = [
    {
        "name": "林浩然", "role": "subject",
        "phone": "13810001001", "phone2": "13810001011",
        "card": "6217001000100010001", "card2": "6217001000100010002",
        "wechat": "林浩然", "id_no": "440103198503120001",
    },
    {
        "name": "苏婉清", "role": "subject",
        "phone": "13910002002", "phone2": "",
        "card": "6228481000200020001", "card2": "",
        "wechat": "苏婉清", "id_no": "440305198712080002",
    },
    {
        "name": "陈建国", "role": "subject",
        "phone": "13610003003", "phone2": "13610003013",
        "card": "6214851000300030001", "card2": "",
        "wechat": "陈建国", "id_no": "440106199008210003",
    },
    {
        "name": "黄志伟", "role": "linked",
        "phone": "13710004004", "phone2": "",
        "card": "6222021000400040001", "card2": "6222021000400040002",
        "wechat": "黄志伟", "id_no": "440104197906150004",
    },
    {
        "name": "刘芳", "role": "linked",
        "phone": "13510005005", "phone2": "13510005015",
        "card": "6212261000500050001", "card2": "",
        "wechat": "刘芳", "id_no": "440103198811020005",
    },
    {
        "name": "周明", "role": "linked",
        "phone": "13410006006", "phone2": "",
        "card": "6225881000600060001", "card2": "",
        "wechat": "周明", "id_no": "440105199204110006",
    },
    {
        "name": "吴思远", "role": "linked",
        "phone": "13310007007", "phone2": "",
        "card": "6217001000700070001", "card2": "",
        "wechat": "吴思远", "id_no": "440103198402260007",
    },
    {
        "name": "郑凯", "role": "linked",
        "phone": "13210008008", "phone2": "",
        "card": "6228481000800080001", "card2": "",
        "wechat": "郑凯", "id_no": "440104199506080008",
    },
    {
        "name": "孙丽", "role": "linked",
        "phone": "13110009009", "phone2": "",
        "card": "6214851000900090001", "card2": "",
        "wechat": "孙丽", "id_no": "440104199308090009",
    },
    {
        "name": "钱进", "role": "linked",
        "phone": "13010010010", "phone2": "",
        "card": "", "card2": "",
        "wechat": "钱进", "id_no": "",
    },
    {
        "name": "赵磊", "role": "linked",
        "phone": "13710011011", "phone2": "",
        "card": "6228481001100110001", "card2": "",
        "wechat": "赵磊", "id_no": "440104198701110010",
    },
    {
        "name": "马强", "role": "linked",
        "phone": "13610012012", "phone2": "",
        "card": "6217001001200120001", "card2": "",
        "wechat": "马强", "id_no": "440105199012120011",
    },
]

BY_NAME = {p["name"]: p for p in PEOPLE}

COMPANIES = [
    {"name": "广州瀚海科技有限公司", "code": "91440101MA5HAI001X", "legal": "林浩然", "capital": "1500万元", "date": "2015-06-18", "industry": "软件和信息技术服务", "region": "广东省广州市天河区", "shareholders": "刘芳（持股30%）", "key_persons": "周明（监事）"},
    {"name": "深圳锐进工程有限公司", "code": "91440300MA5RUI002L", "legal": "苏婉清", "capital": "3000万元", "date": "2012-03-22", "industry": "房屋建筑业", "region": "广东省深圳市南山区", "shareholders": "赵磊（持股10%）", "key_persons": "赵磊"},
    {"name": "广东远航物资供应有限公司", "code": "91440101MA5YUA003W", "legal": "陈建国", "capital": "800万元", "date": "2014-09-10", "industry": "批发业", "region": "广东省广州市番禺区", "shareholders": "马强（持股15%）", "key_persons": ""},
    {"name": "鑫达建设集团有限公司", "code": "91440101MA5XDA004Y", "legal": "黄志伟", "capital": "5000万元", "date": "2009-11-05", "industry": "土木工程建筑", "region": "广东省广州市越秀区", "shareholders": "", "key_persons": ""},
    {"name": "鼎盛管理咨询有限公司", "code": "91440101MA5DSG005Z", "legal": "周明", "capital": "500万元", "date": "2018-02-28", "industry": "商务服务业", "region": "广东省广州市海珠区", "shareholders": "", "key_persons": ""},
    {"name": "鸿运贸易发展有限公司", "code": "91440101MA5HYN006A", "legal": "吴思远", "capital": "1200万元", "date": "2016-07-14", "industry": "批发业", "region": "广东省广州市白云区", "shareholders": "郑凯（持股20%）", "key_persons": ""},
    {"name": "锦程办公设备有限公司", "code": "91440101MA5JCH007B", "legal": "郑凯", "capital": "600万元", "date": "2017-12-01", "industry": "零售业", "region": "广东省广州市黄埔区", "shareholders": "", "key_persons": ""},
    {"name": "岭南智能装备商行", "code": "92440101MA5LNG008C", "legal": "孙丽", "capital": "—", "date": "2019-05-20", "industry": "零售业", "region": "广东省广州市荔湾区", "shareholders": "", "key_persons": ""},
]

PURCHASER = "广东电力开发有限公司"

# 人物关系边（用于生成成对流水/通话/微信）
RELATION_EDGES = [
    ("林浩然", "苏婉清", 22),
    ("林浩然", "陈建国", 14),
    ("林浩然", "黄志伟", 18),
    ("林浩然", "刘芳", 10),
    ("林浩然", "吴思远", 12),
    ("苏婉清", "陈建国", 16),
    ("苏婉清", "周明", 11),
    ("苏婉清", "郑凯", 9),
    ("苏婉清", "赵磊", 8),
    ("陈建国", "黄志伟", 10),
    ("陈建国", "马强", 7),
    ("陈建国", "孙丽", 6),
    ("黄志伟", "吴思远", 8),
    ("黄志伟", "钱进", 5),
    ("周明", "刘芳", 6),
    ("郑凯", "孙丽", 7),
    ("赵磊", "马强", 5),
    ("钱进", "孙丽", 4),
]

BANK_SUMMARIES = [
    "货款", "材料款", "往来款", "借款", "还款", "报销", "劳务费", "咨询费", "设备款", "运费",
    "租金", "分红", "代付", "投标保证金", "退保证金", "项目款",
]

WECHAT_COLS = [
    "用户ID", "交易单号", "大单号", "用户侧账号名称", "借贷类型", "交易业务类型", "交易用途类型",
    "交易时间", "交易金额(分)", "账户余额(分)", "用户银行卡号", "用户侧网银联单号", "网联/银联",
    "第三方账户名称", "对手方ID", "对手侧账户名称", "对手方银行卡号", "对手侧银行名称",
    "对手侧网银联单号", "网联/银联.1", "基金公司信息", "间联/非间联交易", "第三方账户名称.1",
    "对手方接收时间", "对手方接收金额(分)", "备注1", "备注2",
]

TELECOM_COLS = list(
    __import__("app.services.integration.telecom.carrier_templates", fromlist=["CANONICAL_COLUMNS"]).CANONICAL_COLUMNS
)


def _rand_dt(start: datetime, end: datetime, *, work_hours_bias: float = 0.72) -> datetime:
    delta = end - start
    sec = random.randint(0, max(1, int(delta.total_seconds())))
    dt = start + timedelta(seconds=sec)
    if random.random() < work_hours_bias and dt.weekday() < 5:
        dt = dt.replace(hour=random.choice([9, 10, 11, 14, 15, 16, 17]), minute=random.randint(0, 59), second=random.randint(0, 59))
    return dt


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _company_by_legal(name: str) -> dict | None:
    for c in COMPANIES:
        if c["legal"] == name:
            return c
    return None


def generate_enterprise(path: Path) -> None:
    rows = []
    for c in COMPANIES:
        rows.append(
            {
                "企业名称": c["name"],
                "统一社会信用代码": c["code"],
                "法定代表人": c["legal"],
                "注册资本": c["capital"],
                "成立日期": c["date"],
                "经营状态": "存续（在营）",
                "所属行业": c["industry"],
                "所属地区": c["region"],
                "股东信息": c["shareholders"],
                "主要人员": c["key_persons"],
            }
        )
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="工商信息")


def _commercial_summary_sheet(meta: dict[str, str]) -> pd.DataFrame:
    pairs = list(meta.items())
    rows = []
    for i in range(0, len(pairs), 2):
        row = ["", "", "", "", "", "", "", ""]
        row[0] = pairs[i][0]
        row[1] = pairs[i][1]
        if i + 1 < len(pairs):
            row[2] = pairs[i + 1][0]
            row[3] = pairs[i + 1][1]
        rows.append(row)
    return pd.DataFrame(rows)


def _commercial_detail_sheet(items: list[dict], suppliers: list[dict]) -> pd.DataFrame:
    row0 = [
        "序号", "物资编码/来源采购申请代码--物资描述", "型号规格", "品牌/厂家/产地",
        "补充说明", "单位", "数量", "预估单价 (含税)", "预估总价 (含税)",
    ]
    row1 = [""] * 9
    for s in suppliers:
        row0.extend([s["name"], "", "", ""])
        row1.extend(["含税单价(元)", "总价(元)", "税率", "品牌"])
    body: list[list] = [row0, row1]
    for idx, item in enumerate(items, start=1):
        est_unit = item["est_unit"]
        qty = item["qty"]
        row = [
            str(idx), item["desc"], item["spec"], item.get("brand", ""), item.get("note", ""),
            item["unit"], str(qty), f"{est_unit:.2f}", f"{est_unit * qty:.2f}",
        ]
        for s in suppliers:
            q = s["quotes"][idx - 1]
            row.extend([f"{q['unit_price']:.2f}", f"{q['total']:.2f}", q["tax_rate"], q.get("brand", "—")])
        body.append(row)
    for label, key in [("不含税合计总价", "tax_excluded"), ("税金", "tax"), ("含税合计总价", "tax_included"), ("中标金额", "win")]:
        row = [label] + [""] * 8
        for s in suppliers:
            val = s["summary"].get(key, "")
            row.extend([str(val) if val != "" else "", "", "", ""])
        body.append(row)
    return pd.DataFrame(body)


def _supplier_quotes(items: list[dict], unit_prices: list[float], win: bool) -> dict:
    quotes = []
    for i, item in enumerate(items):
        up = unit_prices[i] * random.uniform(0.97, 1.03)
        total = up * item["qty"]
        quotes.append({"unit_price": round(up, 2), "total": round(total, 2), "tax_rate": "13%", "brand": item.get("brand", "—")})
    tax_included = sum(q["total"] for q in quotes)
    tax = round(tax_included * 0.13 / 1.13, 2)
    tax_excluded = round(tax_included - tax, 2)
    return {
        "quotes": quotes,
        "summary": {
            "tax_excluded": f"{tax_excluded:.2f}",
            "tax": f"{tax:.2f}",
            "tax_included": f"{tax_included:.2f}",
            "win": f"{tax_included:.2f}" if win else "",
        },
    }


def generate_commercial(path: Path) -> None:
    inquiries = [
        {
            "meta": {
                "询价单号": "XJ-GD-2025-0601-001",
                "摘要": "2025年本部信息化设备集中采购",
                "采购单位": PURCHASER,
                "联系人手机": BY_NAME["林浩然"]["phone"],
                "联系人邮箱": "linhaoran.procure@gdnyp.local",
                "报价截止时间": "2025-06-10 17:00:00",
                "状态": "已定标",
                "中标供应商": "广州瀚海科技有限公司",
                "中标原因": "综合评分最高",
            },
            "items": [
                {"desc": "台式计算机/i7/32G/1T SSD", "spec": "ThinkCentre M920t", "unit": "台", "qty": 20, "est_unit": 5280.0, "brand": "联想"},
                {"desc": "激光多功能一体机", "spec": "M428fdw", "unit": "台", "qty": 5, "est_unit": 3499.0, "brand": "惠普"},
                {"desc": "A4复印纸", "spec": "70g 500张/包", "unit": "箱", "qty": 60, "est_unit": 118.0, "brand": "得力"},
            ],
            "suppliers": [
                ("广州瀚海科技有限公司", [5180, 3350, 112], True),
                ("深圳锐进工程有限公司", [5250, 3420, 115], False),
                ("鑫达建设集团有限公司", [5220, 3380, 114], False),
                ("锦程办公设备有限公司", [5190, 3360, 113], False),
            ],
        },
        {
            "meta": {
                "询价单号": "XJ-GD-2025-0615-003",
                "摘要": "检修项目电缆及管材框架采购",
                "采购单位": PURCHASER,
                "联系人手机": BY_NAME["苏婉清"]["phone"],
                "联系人邮箱": "suwanqing.project@gdnyp.local",
                "报价截止时间": "2025-06-20 16:30:00",
                "状态": "已定标",
                "中标供应商": "深圳锐进工程有限公司",
                "中标原因": "单价优势及交付能力",
            },
            "items": [
                {"desc": "电缆 YJV-0.6/1KV-3*95+2*50", "spec": "国标铜芯", "unit": "米", "qty": 1200, "est_unit": 88.0},
                {"desc": "镀锌钢管 DN50", "spec": "6m/根", "unit": "根", "qty": 200, "est_unit": 43.0},
            ],
            "suppliers": [
                ("深圳锐进工程有限公司", [85.5, 40.5], True),
                ("广东远航物资供应有限公司", [86.8, 41.2], False),
                ("鸿运贸易发展有限公司", [87.2, 41.8], False),
            ],
        },
        {
            "meta": {
                "询价单号": "XJ-GD-2025-0702-008",
                "摘要": "办公家具及耗材补充采购",
                "采购单位": PURCHASER,
                "联系人手机": BY_NAME["陈建国"]["phone"],
                "联系人邮箱": "chenjianguo.procure@gdnyp.local",
                "报价截止时间": "2025-07-05 17:00:00",
                "状态": "已定标",
                "中标供应商": "岭南智能装备商行",
                "中标原因": "价格最低",
            },
            "items": [
                {"desc": "人体工学办公椅", "spec": "网布高背", "unit": "把", "qty": 30, "est_unit": 680.0},
                {"desc": "文件柜", "spec": "钢制三层", "unit": "组", "qty": 15, "est_unit": 420.0},
            ],
            "suppliers": [
                ("岭南智能装备商行", [650, 398], True),
                ("锦程办公设备有限公司", [665, 405], False),
                ("鼎盛管理咨询有限公司", [672, 410], False),
                ("广州瀚海科技有限公司", [680, 415], False),
            ],
        },
    ]

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for i, inq in enumerate(inquiries, start=1):
            suffix = f"{i:03d}"
            suppliers = []
            for name, prices, win in inq["suppliers"]:
                s = {"name": name, **_supplier_quotes(inq["items"], prices, win)}
                suppliers.append(s)
            _commercial_summary_sheet(inq["meta"]).to_excel(writer, index=False, header=False, sheet_name=f"询价概要{suffix}")
            _commercial_detail_sheet(inq["items"], suppliers).to_excel(writer, index=False, header=False, sheet_name=f"报价明细{suffix}")


def generate_bank(path: Path) -> None:
    account_holders = ["林浩然", "苏婉清", "陈建国", "黄志伟", "刘芳", "吴思远"]
    accounts = []
    for name in account_holders:
        p = BY_NAME[name]
        accounts.append({
            "账户名称": p["name"],
            "账号": p["card"],
            "证件号码": p["id_no"],
            "移动电话": p["phone"],
            "开户日期": "2016-04-12" if name == "林浩然" else "2018-09-03",
        })
        if p["card2"]:
            accounts.append({
                "账户名称": p["name"],
                "账号": p["card2"],
                "证件号码": p["id_no"],
                "移动电话": p.get("phone2") or p["phone"],
                "开户日期": "2020-01-18",
            })

    start = datetime(2025, 1, 6)
    end = datetime(2025, 7, 28)
    txns: list[dict] = []

    def add_txn(owner: dict, counterparty: str, cp_account: str, amount: float, direction: str, when: datetime, summary: str, card: str | None = None) -> None:
        txns.append({
            "客户名称": owner["name"],
            "交易卡号": card or owner["card"],
            "对方户名": counterparty,
            "对方账号": cp_account or "—",
            "交易日期": _fmt_date(when),
            "交易时间": when.strftime("%H:%M:%S"),
            "借贷方向": direction,
            "币种": "人民币",
            "交易金额": f"{amount:.2f}" if direction == "借" else f"-{amount:.2f}",
            "账户余额": f"{random.randint(50000, 900000)}.{random.randint(10, 99):02d}",
            "摘要": summary,
        })

    for a_name, b_name, count in RELATION_EDGES:
        pa, pb = BY_NAME[a_name], BY_NAME[b_name]
        for _ in range(max(2, count // 3)):
            when = _rand_dt(start, end)
            amt = round(random.uniform(2000, 88000) * random.uniform(0.9, 1.1), 2)
            add_txn(pa, pb["name"], pb["card"] or "—", amt, random.choice(["借", "贷"]), when, random.choice(BANK_SUMMARIES))
            if random.random() < 0.5:
                add_txn(pb, pa["name"], pa["card"] or "—", round(amt * random.uniform(0.3, 1.0), 2), random.choice(["借", "贷"]), when + timedelta(days=random.randint(0, 5)), random.choice(BANK_SUMMARIES))

    # 主体与企业往来
    for name in ["林浩然", "苏婉清", "陈建国"]:
        p = BY_NAME[name]
        comp = _company_by_legal(name) or random.choice(COMPANIES)
        for _ in range(8):
            when = _rand_dt(start, end)
            amt = round(random.uniform(30000, 220000), 2)
            add_txn(p, comp["name"], "—", amt, random.choice(["借", "贷"]), when, random.choice(["货款", "项目回款", "投标保证金"]))

    # 林浩然第二卡
    lin = BY_NAME["林浩然"]
    for _ in range(6):
        when = _rand_dt(start, end)
        add_txn(lin, BY_NAME["苏婉清"]["name"], BY_NAME["苏婉清"]["card"], round(random.uniform(1000, 15000), 2), "贷", when, "往来款", card=lin["card2"])

    # 固定特征金额
    for _ in range(4):
        add_txn(BY_NAME["林浩然"], BY_NAME["苏婉清"]["name"], BY_NAME["苏婉清"]["card"], 8888.88, "贷", _rand_dt(start, end), "往来款")
    add_txn(BY_NAME["林浩然"], BY_NAME["黄志伟"]["name"], BY_NAME["黄志伟"]["card"], 52000.0, "贷", _rand_dt(start, end).replace(hour=23, minute=15), "借款")

    txns.sort(key=lambda x: (x["交易日期"], x["交易时间"]))
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(accounts).to_excel(writer, index=False, sheet_name="开户信息")
        pd.DataFrame(txns).to_excel(writer, index=False, sheet_name="交易明细")


def _wechat_row(user: dict, peer: str, dc: str, amount_yuan: float, when: datetime, txn_no: str, remark: str, card: str | None = None) -> dict:
    fen = int(round(amount_yuan * 100))
    return {
        "用户ID": f"wx_{user['phone'][-8:]}",
        "交易单号": txn_no,
        "大单号": "",
        "用户侧账号名称": user["wechat"],
        "借贷类型": dc,
        "交易业务类型": "转账",
        "交易用途类型": "转账",
        "交易时间": _fmt_dt(when),
        "交易金额(分)": str(fen),
        "账户余额(分)": str(random.randint(80000, 9000000)),
        "用户银行卡号": card or user["card"] or "",
        "用户侧网银联单号": "", "网联/银联": "", "第三方账户名称": "",
        "对手方ID": "", "对手侧账户名称": peer,
        "对手方银行卡号": "", "对手侧银行名称": "", "对手侧网银联单号": "",
        "网联/银联.1": "", "基金公司信息": "", "间联/非间联交易": "非间联",
        "第三方账户名称.1": "",
        "对手方接收时间": _fmt_dt(when + timedelta(seconds=random.randint(1, 8))),
        "对手方接收金额(分)": str(fen),
        "备注1": remark, "备注2": "",
    }


def generate_wechat(path: Path) -> None:
    start = datetime(2025, 1, 8)
    end = datetime(2025, 7, 25)
    rows = []
    seq = 2001
    remarks = ["项目分成", "往来款", "餐费", "资料费", "借款", "还款", "代购", "咨询费", "分红预支"]

    for a_name, b_name, count in RELATION_EDGES:
        pa, pb = BY_NAME[a_name], BY_NAME[b_name]
        for _ in range(max(3, count // 2)):
            when = _rand_dt(start, end)
            amt = round(random.uniform(200, 45000) * random.uniform(0.85, 1.15), 2)
            if random.random() < 0.12:
                amt = random.choice([520, 521, 1314, 888, 666, 8888])
            rows.append(_wechat_row(pa, pb["wechat"], random.choice(["入", "出"]), amt, when, f"420000{when.strftime('%Y%m%d')}{seq:06d}", random.choice(remarks)))
            seq += 1
            if random.random() < 0.45:
                rows.append(_wechat_row(pb, pa["wechat"], random.choice(["入", "出"]), round(amt * random.uniform(0.2, 0.9), 2), when + timedelta(hours=random.randint(1, 48)), f"420000{when.strftime('%Y%m%d')}{seq:06d}", random.choice(remarks)))
                seq += 1

    # 林浩然副卡微信
    for _ in range(5):
        when = _rand_dt(start, end)
        rows.append(_wechat_row(BY_NAME["林浩然"], BY_NAME["刘芳"]["wechat"], "出", round(random.uniform(500, 8000), 2), when, f"420000{when.strftime('%Y%m%d')}{seq:06d}", "股东分红预支", card=BY_NAME["林浩然"]["card2"]))
        seq += 1

    rows.sort(key=lambda r: r["交易时间"])
    pd.DataFrame(rows, columns=WECHAT_COLS).to_excel(path, index=False, sheet_name="微信流水", engine="openpyxl")


def _telecom_row(local: dict, peer: dict, when: datetime, duration: int, bill: str, call_type: str = "VoLTE语音通话") -> dict:
    loc_map = {"林浩然": ("20", "385392734"), "苏婉清": ("755", "12918878"), "陈建国": ("20", "44291856")}
    local_loc, cell = loc_map.get(local["name"], ("20", str(random.randint(10000000, 99999999))))
    return {
        "序号": "", "通信记录唯一标识": "", "通话类型": call_type, "话单类型": bill,
        "本机号码": f"86{local['phone']}", "本机IMSI号": "", "本机IMEI号": "",
        "本机RAC号": "0", "本机LAC号": "0", "本机基站ID": "", "本机CELLID": cell,
        "本机归属运营商": "广东移动", "本机通话所在地": local_loc,
        "对方号码": f"86{peer['phone']}", "对方IMSI号": "", "对方IMEI号": "",
        "对方RAC号": "", "对方LAC号": "", "对方基站ID": "", "对方CELLID": "",
        "对方归属运营商": random.choice(["广东移动", "广东联通", "广东电信"]),
        "对方通话所在地": random.choice(["20", "755", "769"]),
        "对方号码归属地": random.choice(["20", "755"]),
        "前转主叫号码": "", "呼叫开始时间": _fmt_dt(when), "呼叫时长": str(duration),
        "是否群内呼叫": "", "群组编号": "", "群组名称": "", "短信发送接收时间": "",
    }


def generate_telecom(path: Path) -> None:
    start = datetime(2025, 2, 1)
    end = datetime(2025, 7, 30)
    rows = []
    seq = 1

    # 所有 12 人至少作为本机或对方出现
    for a_name, b_name, count in RELATION_EDGES:
        pa, pb = BY_NAME[a_name], BY_NAME[b_name]
        for _ in range(max(2, count // 2)):
            when = _rand_dt(start, end)
            if random.random() < 0.1:
                when = when.replace(hour=random.choice([7, 8, 22, 23]), minute=random.randint(0, 59))
            duration = random.choice([0, 15, 33, 58, 126, 280, 540, 980])
            bill = random.choice(["主叫话单", "被叫话单", "被叫话单"])
            row = _telecom_row(pa, pb, when, duration, bill)
            row["序号"] = str(seq)
            seq += 1
            rows.append(row)
            if random.random() < 0.35:
                row2 = _telecom_row(pb, pa, when + timedelta(hours=random.randint(1, 72)), random.choice([20, 45, 90]), bill)
                row2["序号"] = str(seq)
                seq += 1
                rows.append(row2)

    # 副号通话
    lin = BY_NAME["林浩然"]
    lin2_phone = BY_NAME["林浩然"]["phone2"]
    if lin2_phone:
        for _ in range(4):
            when = _rand_dt(start, end)
            row = _telecom_row(lin, BY_NAME["苏婉清"], when, random.choice([30, 60, 120]), "主叫话单")
            row["本机号码"] = f"86{lin2_phone}"
            row["序号"] = str(seq)
            seq += 1
            rows.append(row)

    for local, peer in [(BY_NAME["林浩然"], BY_NAME["刘芳"]), (BY_NAME["苏婉清"], BY_NAME["周明"])]:
        when = _rand_dt(start, end)
        row = _telecom_row(local, peer, when, 0, "主叫话单", call_type="点对点短信")
        row["呼叫开始时间"] = ""
        row["短信发送接收时间"] = _fmt_dt(when)
        row["序号"] = str(seq)
        seq += 1
        rows.append(row)

    rows.sort(key=lambda r: r["呼叫开始时间"] or r["短信发送接收时间"])
    for i, row in enumerate(rows, start=1):
        row["序号"] = str(i)

    pd.DataFrame(rows, columns=TELECOM_COLS).to_excel(path, index=False, sheet_name="运营商话单信息", engine="openpyxl")


def write_readme(path: Path) -> None:
    lines = [
        "# DataFusionX 融合关联演示数据（v2）",
        "",
        "12 人跨 5 类数据源，支持姓名-手机-微信-银行卡-企业关联与融合驾驶舱分析。",
        "",
        "## 人物速查",
        "",
        "| 角色 | 姓名 | 手机 | 副号 | 微信 | 银行卡 |",
        "|------|------|------|------|------|--------|",
    ]
    for p in PEOPLE:
        lines.append(
            f"| {('主体' if p['role']=='subject' else '关联')} | {p['name']} | {p['phone']} | {p.get('phone2') or '—'} | {p['wechat']} | {p['card'][:8]}… |"
        )
    lines.extend([
        "",
        "## 企业法人",
        "",
    ])
    for c in COMPANIES:
        lines.append(f"- {c['legal']} → {c['name']}")
    lines.extend([
        "",
        "## 数据规模（约）",
        "",
        "| 文件 | 内容 |",
        "|------|------|",
        "| 01_enterprise | 8 家工商主体 |",
        "| 02_commercial | 3 个询价单、多供应商同场 |",
        "| 03_bank | 6 人开户（含副卡）+ ~120 笔流水 |",
        "| 04_wechat | ~100 笔转账 |",
        "| 05_telecom | ~130 条话单（12 人通联） |",
        "",
        "## 推荐分析路径",
        "",
        "1. 导入全部文件并绑定到同一案件",
        "2. 点击「机器预关联」",
        "3. 驾驶舱选 **林浩然 ↔ 苏婉清** 查看银行/微信/通话/商务同场",
        "",
        "## 重新生成",
        "",
        "```bash",
        "python3 scripts/generate_mock_data.py",
        "python3 scripts/import_mock_data.py",
        "```",
        "",
        "数据均为虚构，请勿用于生产或对外披露。",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_enterprise(OUT_DIR / "01_enterprise_工商主体.xlsx")
    generate_commercial(OUT_DIR / "02_commercial_商务网询价.xlsx")
    generate_bank(OUT_DIR / "03_bank_多人流水_建设银行.xlsx")
    generate_wechat(OUT_DIR / "04_wechat_多人转账.xlsx")
    generate_telecom(OUT_DIR / "05_telecom_多人话单.xlsx")
    write_readme(OUT_DIR / "README.md")
    print(f"Generated rich mock data in {OUT_DIR}")


if __name__ == "__main__":
    main()
