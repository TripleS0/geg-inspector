import { Col, DatePicker, Form, TimePicker } from "antd";
import type { ColProps } from "antd";
import type { Dayjs } from "dayjs";

const { RangePicker: DateRangePicker } = DatePicker;
const { RangePicker: TimeRangePicker } = TimePicker;

/** 表单内日期段、日内时间段字段（提交前需序列化为 API 参数） */
export type AnalysisDateTimeFormFields = {
  date_range?: [Dayjs, Dayjs] | null;
  day_time_range?: [Dayjs, Dayjs] | null;
};

type SerializeResult = {
  start_time?: string;
  end_time?: string;
  day_time_start?: string;
  day_time_end?: string;
};

/**
 * 将 RangePicker / TimePicker 表单值转换为后端 start_time、end_time、day_time_start、day_time_end。
 */
export function serializeAnalysisDateTimeFilters<T extends AnalysisDateTimeFormFields>(
  values: T,
): Omit<T, "date_range" | "day_time_range"> & SerializeResult {
  const { date_range, day_time_range, ...rest } = values;
  const payload = { ...rest } as Omit<T, "date_range" | "day_time_range"> & SerializeResult;

  if (date_range?.[0] && date_range?.[1]) {
    payload.start_time = date_range[0].startOf("day").format("YYYY-MM-DD HH:mm:ss");
    payload.end_time = date_range[1].endOf("day").format("YYYY-MM-DD HH:mm:ss");
  }
  if (day_time_range?.[0] && day_time_range?.[1]) {
    payload.day_time_start = day_time_range[0].format("HH:mm:ss");
    payload.day_time_end = day_time_range[1].format("HH:mm:ss");
  }
  return payload;
}

interface AnalysisDateTimeFilterFieldsProps {
  /** 日期段列宽，默认 md=8 */
  dateCol?: ColProps;
  /** 时间段列宽，默认 md=8 */
  timeCol?: ColProps;
}

/**
 * 分析页通用：日期段（日历点选）+ 日内时间段（时分滚轮选择）。
 */
export function AnalysisDateTimeFilterFields({
  dateCol = { xs: 24, md: 8 },
  timeCol = { xs: 24, md: 8 },
}: AnalysisDateTimeFilterFieldsProps) {
  return (
    <>
      <Col {...dateCol}>
        <Form.Item label="日期段" name="date_range">
          <DateRangePicker
            style={{ width: "100%" }}
            allowClear
            format="YYYY-MM-DD"
            placeholder={["开始日期", "结束日期"]}
          />
        </Form.Item>
      </Col>
      <Col {...timeCol}>
        <Form.Item
          label="时间段"
          name="day_time_range"
          tooltip="按每日时分筛选；若起止跨越午夜，则匹配当日该时段或次日该时段之前的记录"
        >
          <TimeRangePicker
            style={{ width: "100%" }}
            allowClear
            format="HH:mm"
            placeholder={["开始时分", "结束时分"]}
            needConfirm={false}
          />
        </Form.Item>
      </Col>
    </>
  );
}
