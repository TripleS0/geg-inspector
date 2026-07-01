import type { EChartsOption } from "echarts";
import type { FusionRecord } from "../api";
import { formatFusionAmount } from "./graphRecordUtils";

export type BilateralFlowItem = {
  time: number;
  timeLabel: string;
  fromIndex: number;
  toIndex: number;
  valueLabel: string;
  recordType: string;
  summary: string;
  magnitude: number;
};

type TimeSlot =
  | { kind: "record"; slotIndex: number; itemIndex: number; label: string }
  | { kind: "gap"; slotIndex: number; label: string; gapDays: number };

const TYPE_COLORS: Record<string, string> = {
  bank_txn: "#e85d45",
  wechat: "#52c41a",
  telecom: "#1890ff",
};

const PARTY_COLUMN_BG = ["rgba(59, 130, 246, 0.07)", "rgba(245, 158, 11, 0.07)"];
const PARTY_COLUMN_BORDER = ["rgba(59, 130, 246, 0.18)", "rgba(245, 158, 11, 0.22)"];

function normalizeName(value: string) {
  return value.trim().toLowerCase();
}

function namesMatch(a: string, b: string) {
  const left = normalizeName(a);
  const right = normalizeName(b);
  if (!left || !right) return false;
  return left === right || left.includes(right) || right.includes(left);
}

function partyIndex(parties: string[], name?: string) {
  if (!name) return -1;
  return parties.findIndex((party) => namesMatch(party, name));
}

function isAdjacentHop(fromIndex: number, toIndex: number) {
  return fromIndex >= 0 && toIndex >= 0 && fromIndex !== toIndex && Math.abs(fromIndex - toIndex) === 1;
}

/** 根据 counterparty 推断记录属于路径上的哪一跳（相邻两节点） */
function inferAdjacentHopPair(record: FusionRecord, parties: string[]): [number, number] | null {
  const cpIdx = partyIndex(parties, record.counterparty);
  if (cpIdx < 0) return null;

  const candidates: Array<[number, number]> = [];
  if (cpIdx > 0) candidates.push([cpIdx - 1, cpIdx]);
  if (cpIdx < parties.length - 1) candidates.push([cpIdx, cpIdx + 1]);
  if (!candidates.length) return null;
  if (candidates.length === 1) return candidates[0];

  const hintA = partyIndex(parties, record.flow_party_a);
  const hintB = partyIndex(parties, record.flow_party_b);
  for (const pair of candidates) {
    const [left, right] = pair;
    if (hintA === left || hintA === right || hintB === left || hintB === right) {
      return pair;
    }
  }
  return candidates[0];
}

function resolveHopIndices(
  record: FusionRecord,
  parties: string[]
): { fromIndex: number; toIndex: number } | null {
  const idxA = partyIndex(parties, record.flow_party_a);
  const idxB = partyIndex(parties, record.flow_party_b);
  let left = -1;
  let right = -1;

  if (isAdjacentHop(idxA, idxB)) {
    left = Math.min(idxA, idxB);
    right = Math.max(idxA, idxB);
  } else {
    const pair = parties.length === 2 ? ([0, 1] as [number, number]) : inferAdjacentHopPair(record, parties);
    if (!pair) {
      if (parties.length === 2) {
        left = 0;
        right = 1;
      } else {
        return null;
      }
    } else {
      [left, right] = pair;
    }
  }

  const flow = inferBilateralFlow(record, parties[left], parties[right]);
  return flow === "a_to_b" ? { fromIndex: left, toIndex: right } : { fromIndex: right, toIndex: left };
}

export function inferBilateralFlow(
  record: FusionRecord,
  partyA: string,
  partyB: string
): "a_to_b" | "b_to_a" {
  const counterparty = record.counterparty || "";
  const direction = record.direction || "";

  if (namesMatch(counterparty, partyB)) {
    if (direction.includes("收") || direction === "入") return "b_to_a";
    return "a_to_b";
  }
  if (namesMatch(counterparty, partyA)) {
    if (direction.includes("收") || direction === "入") return "a_to_b";
    return "b_to_a";
  }
  if (direction.includes("收") || direction === "入") return "b_to_a";
  if (direction.includes("支") || direction === "出") return "a_to_b";
  return "a_to_b";
}

function parseRecordTime(time: string | null): number {
  if (!time) return 0;
  const parsed = Date.parse(time.replace(" ", "T"));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function formatRecordValue(record: FusionRecord) {
  if (record.record_type === "telecom") {
    const seconds = record.amount ?? 0;
    return seconds >= 60 ? `${Math.round(seconds / 60)} 分钟` : `${seconds} 秒`;
  }
  return formatFusionAmount(record.amount);
}

function recordMagnitude(record: FusionRecord) {
  if (record.record_type === "telecom") return Math.max(record.amount ?? 0, 1);
  return Math.max(Math.abs(record.amount ?? 0), 1);
}

function formatShortTime(timeLabel: string) {
  const normalized = timeLabel.replace("T", " ");
  if (normalized.length >= 16) return normalized.slice(5, 16);
  if (normalized.length >= 10) return normalized.slice(5, 10);
  return normalized;
}

function computeGapThresholdMs(items: BilateralFlowItem[]) {
  if (items.length < 2) return Number.POSITIVE_INFINITY;
  const intervals: number[] = [];
  for (let i = 1; i < items.length; i += 1) {
    intervals.push(items[i].time - items[i - 1].time);
  }
  intervals.sort((a, b) => a - b);
  const median = intervals[Math.floor(intervals.length / 2)] || 0;
  const week = 7 * 24 * 3_600_000;
  return Math.max(week, median * 2.5);
}

function buildTimeSlots(items: BilateralFlowItem[]): TimeSlot[] {
  const gapThreshold = computeGapThresholdMs(items);
  const slots: TimeSlot[] = [];
  let slotIndex = 0;

  items.forEach((item, itemIndex) => {
    if (itemIndex > 0) {
      const gapMs = item.time - items[itemIndex - 1].time;
      if (gapMs > gapThreshold) {
        const gapDays = Math.max(1, Math.round(gapMs / (24 * 3_600_000)));
        slots.push({
          kind: "gap",
          slotIndex,
          label: gapDays >= 30 ? `间隔约 ${Math.round(gapDays / 30)} 个月` : `间隔 ${gapDays} 天`,
          gapDays,
        });
        slotIndex += 1;
      }
    }
    slots.push({
      kind: "record",
      slotIndex,
      itemIndex,
      label: formatShortTime(item.timeLabel),
    });
    slotIndex += 1;
  });

  return slots;
}

function magnitudeToLineWidth(magnitude: number, min: number, max: number) {
  const logMin = Math.log10(Math.max(min, 1));
  const logMax = Math.log10(Math.max(max, 1));
  const logVal = Math.log10(Math.max(magnitude, 1));
  const t = logMax === logMin ? 0.55 : (logVal - logMin) / (logMax - logMin);
  return Number((1.8 + t * 3.4).toFixed(2));
}

function arrowPolygon(x: number, y: number, direction: "left" | "right", color: string, size: number) {
  const sign = direction === "right" ? 1 : -1;
  return {
    type: "polygon" as const,
    shape: {
      points: [
        [x, y],
        [x - sign * size, y - size * 0.52],
        [x - sign * size, y + size * 0.52],
      ],
    },
    style: { fill: color, stroke: "none" },
  };
}

export function buildBilateralFlowItems(records: FusionRecord[], partiesOrA: string[] | string, maybePartyB?: string): BilateralFlowItem[] {
  const parties = Array.isArray(partiesOrA) ? partiesOrA : [partiesOrA, maybePartyB || ""];

  return records
    .map((record) => {
      const time = parseRecordTime(record.time);
      const hop = resolveHopIndices(record, parties);
      if (!hop) return null;

      return {
        time,
        timeLabel: record.time?.replace("T", " ").slice(0, 19) || "—",
        fromIndex: hop.fromIndex,
        toIndex: hop.toIndex,
        valueLabel: formatRecordValue(record),
        recordType: record.record_type,
        summary: record.summary || record.title || "",
        magnitude: recordMagnitude(record),
      } satisfies BilateralFlowItem;
    })
    .filter((item): item is BilateralFlowItem => item !== null && item.time > 0)
    .sort((a, b) => a.time - b.time);
}

export function bilateralFlowSlotCount(items: BilateralFlowItem[]) {
  return buildTimeSlots(items).length;
}

export function buildBilateralFlowChartOption(
  items: BilateralFlowItem[],
  partiesOrA: string[] | string,
  maybePartyB?: string
): EChartsOption | null {
  const parties = Array.isArray(partiesOrA) ? partiesOrA.filter(Boolean) : [partiesOrA, maybePartyB || ""].filter(Boolean);
  if (!items.length || parties.length < 2) return null;

  const slots = buildTimeSlots(items);
  const slotLabels = slots.map((slot) => slot.label);
  const magnitudes = items.map((item) => item.magnitude);
  const minMag = Math.min(...magnitudes);
  const maxMag = Math.max(...magnitudes);
  const lastPartyIndex = parties.length - 1;

  const recordSlots = slots.filter((slot): slot is Extract<TimeSlot, { kind: "record" }> => slot.kind === "record");

  return {
    animation: true,
    animationDuration: 320,
    backgroundColor: "#fafbfc",
    grid: { left: 118, right: 118, top: 52, bottom: 28, containLabel: false },
    xAxis: {
      type: "category",
      data: parties,
      position: "top",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        fontSize: 13,
        fontWeight: 700,
        color: "#1f2937",
        margin: 14,
        formatter: (value: string, index: number) => {
          const short = value.length > 10 ? `${value.slice(0, 9)}…` : value;
          const token = index === 0 ? "p0" : index === lastPartyIndex ? "p1" : "pm";
          return `{${token}|${short}}`;
        },
        rich: {
          p0: {
            color: "#1d4ed8",
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            padding: [6, 10],
            borderRadius: 6,
            fontWeight: 700,
          },
          p1: {
            color: "#b45309",
            backgroundColor: "rgba(245, 158, 11, 0.12)",
            padding: [6, 10],
            borderRadius: 6,
            fontWeight: 700,
          },
          pm: {
            color: "#047857",
            backgroundColor: "rgba(16, 185, 129, 0.12)",
            padding: [6, 10],
            borderRadius: 6,
            fontWeight: 700,
          },
        },
      },
    },
    yAxis: {
      type: "category",
      data: slotLabels,
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        fontSize: 11,
        color: "#6b7280",
        margin: 10,
        formatter: (value: string) => {
          if (value.startsWith("间隔")) {
            return `{gap|${value}}`;
          }
          return value;
        },
        rich: {
          gap: {
            color: "#9ca3af",
            fontStyle: "italic",
            fontSize: 10,
          },
        },
      },
      splitLine: {
        show: true,
        lineStyle: { type: "dashed", color: "#e8ecf1" },
      },
    },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e5e7eb",
      textStyle: { color: "#374151", fontSize: 12 },
      formatter: (params) => {
        const payload = (params as { data?: { item?: BilateralFlowItem } }).data;
        const item = payload?.item;
        if (!item) return "";
        const from = parties[item.fromIndex] || "起点";
        const to = parties[item.toIndex] || "终点";
        const typeLabel =
          item.recordType === "bank_txn" ? "银行" : item.recordType === "wechat" ? "微信" : "通讯";
        return [
          `<strong>${item.timeLabel}</strong>`,
          `${from} → ${to}`,
          `${typeLabel} · ${item.valueLabel}`,
          item.summary || "",
        ]
          .filter(Boolean)
          .join("<br/>");
      },
    },
    series: [
      {
        type: "custom",
        silent: true,
        z: 1,
        renderItem: (_params, api) => {
          const slotCount = slots.length;
          if (slotCount === 0) return null;

          const topLeft = api.coord([0, 0]);
          const bottomRight = api.coord([lastPartyIndex, slotCount - 1]);
          const stepWidth = parties.length > 1 ? Math.abs(api.coord([1, 0])[0] - api.coord([0, 0])[0]) : 180;
          const colWidth = Math.min(220, stepWidth * 0.86);
          const children: Array<Record<string, unknown>> = [];

          parties.forEach((_party, col) => {
            const x = api.coord([col, 0])[0] - colWidth / 2;
            const colorIndex = col === 0 ? 0 : col === lastPartyIndex ? 1 : col % 2;
            children.push({
              type: "rect",
              shape: {
                x,
                y: topLeft[1] - 8,
                width: colWidth,
                height: bottomRight[1] - topLeft[1] + 16,
                r: 10,
              },
              style: {
                fill: PARTY_COLUMN_BG[colorIndex],
                stroke: PARTY_COLUMN_BORDER[colorIndex],
                lineWidth: 1,
              },
            });
          });

          slots.forEach((slot) => {
            if (slot.kind !== "gap") return;
            const y = api.coord([0, slot.slotIndex])[1];
            const x0 = api.coord([0, slot.slotIndex])[0] - colWidth / 2;
            const x1 = api.coord([lastPartyIndex, slot.slotIndex])[0] + colWidth / 2;
            const midX = (x0 + x1) / 2;
            children.push({
              type: "group",
              children: [
                {
                  type: "line",
                  shape: { x1: x0 + 12, y1: y, x2: midX - 28, y2: y },
                  style: { stroke: "#d1d5db", lineWidth: 1, lineDash: [4, 4] },
                },
                {
                  type: "line",
                  shape: { x1: midX + 28, y1: y, x2: x1 - 12, y2: y },
                  style: { stroke: "#d1d5db", lineWidth: 1, lineDash: [4, 4] },
                },
                {
                  type: "text",
                  style: {
                    text: "⋮",
                    x: midX,
                    y,
                    fill: "#9ca3af",
                    fontSize: 14,
                    textAlign: "center",
                    textVerticalAlign: "middle",
                  },
                },
              ],
            });
          });

          return { type: "group", children } as unknown as NonNullable<import("echarts").CustomSeriesRenderItemReturn>;
        },
        data: [0],
      },
      {
        type: "custom",
        z: 3,
        renderItem: (params, api) => {
          const slot = recordSlots[params.dataIndex];
          if (!slot) return null;
          const item = items[slot.itemIndex];
          if (!item) return null;

          const fromPoint = api.coord([item.fromIndex, slot.slotIndex]);
          const toPoint = api.coord([item.toIndex, slot.slotIndex]);
          const color = TYPE_COLORS[item.recordType] || "#64748b";
          const lineWidth = magnitudeToLineWidth(item.magnitude, minMag, maxMag);
          const direction: "left" | "right" = item.toIndex > item.fromIndex ? "right" : "left";
          const arrowSize = 7 + lineWidth * 0.35;
          const shorten = arrowSize + 6;
          const dx = toPoint[0] - fromPoint[0];
          const dy = toPoint[1] - fromPoint[1];
          const len = Math.hypot(dx, dy) || 1;
          const endX = toPoint[0] - (dx / len) * shorten;
          const endY = toPoint[1] - (dy / len) * shorten;
          const startPad = 8;
          const startX = fromPoint[0] + (dx / len) * startPad;
          const startY = fromPoint[1] + (dy / len) * startPad;
          const midX = (startX + endX) / 2;
          const midY = (startY + endY) / 2;
          const labelOffset = params.dataIndex % 2 === 0 ? -14 : 14;

          return {
            type: "group",
            children: [
              {
                type: "line",
                shape: { x1: startX, y1: startY, x2: endX, y2: endY },
                style: {
                  stroke: color,
                  lineWidth,
                  opacity: 0.88,
                  lineCap: "round",
                },
              },
              arrowPolygon(endX, endY, direction, color, arrowSize),
              {
                type: "circle",
                shape: { cx: fromPoint[0], cy: fromPoint[1], r: 4 + lineWidth * 0.15 },
                style: { fill: color, stroke: "#fff", lineWidth: 1.5 },
              },
              {
                type: "rect",
                shape: {
                  x: midX - 36,
                  y: midY + labelOffset - 10,
                  width: 72,
                  height: 20,
                  r: 4,
                },
                style: {
                  fill: "rgba(255,255,255,0.92)",
                  stroke: "rgba(0,0,0,0.06)",
                  lineWidth: 1,
                },
              },
              {
                type: "text",
                style: {
                  text: item.valueLabel,
                  x: midX,
                  y: midY + labelOffset,
                  fill: "#374151",
                  fontSize: 11,
                  fontWeight: 600,
                  textAlign: "center",
                  textVerticalAlign: "middle",
                },
              },
            ],
          } as unknown as NonNullable<import("echarts").CustomSeriesRenderItemReturn>;
        },
        data: recordSlots.map((slot) => ({ slot, item: items[slot.itemIndex] })),
      },
    ],
  };
}

export function parsePartiesFromTitle(title: string): { partyA: string; partyB: string } | null {
  const parts = title.split(/\s*→\s*/).map((part) => part.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  return { partyA: parts[0], partyB: parts[parts.length - 1] };
}
