export type SourceType = "bank" | "commercial" | "enterprise" | "wechat" | "telecom";

export const SOURCE_LABELS: Record<SourceType, string> = {
  bank: "银行流水",
  commercial: "商务网招投标",
  enterprise: "工商/企业基础信息",
  wechat: "微信转账流水",
  telecom: "运营商话单",
};

export const SOURCE_TYPE_OPTIONS = (Object.keys(SOURCE_LABELS) as SourceType[]).map((value) => ({
  value,
  label: SOURCE_LABELS[value],
}));
