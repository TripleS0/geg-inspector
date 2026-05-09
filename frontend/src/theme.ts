/**
 * 与 styles.css 中暖色界面一致的设计令牌，供 Ant Design ConfigProvider 与 ECharts 共用。
 */
export const appTheme = {
  colorPrimary: "#d94832",
  colorPrimaryHover: "#c73a26",
  colorPrimaryActive: "#b33222",
  colorLink: "#c14732",
} as const;

/** ECharts 多系列配色（暖色、低饱和，避免默认蓝绿） */
export const chartPalette = [
  "#e85d45",
  "#f0a84d",
  "#d94a35",
  "#e8b339",
  "#c85a4a",
  "#f4c26b",
  "#b85c4c",
  "#d9775e",
] as const;

export const chartPair = {
  /** 收入 / 主项 */
  primary: "#e85d45",
  /** 支出 / 对比项 */
  secondary: "#f0b95c",
} as const;

/** 风险等级柱状图用色（与 Tag 语义一致、偏暖色） */
export const riskLevelChartColors: Record<string, string> = {
  high: "#d23b26",
  medium: "#e8954a",
  low: "#c9a227",
};
