import { Button, Empty, Typography } from "antd";
import { ExportOutlined } from "@ant-design/icons";

const { Paragraph, Text, Title } = Typography;

function FusionExportCasePanel() {
  return (
    <div className="fusion-hub-panel fusion-export-panel app-card">
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <div className="fusion-export-empty">
            <Title level={4}>导出案件</Title>
            <Paragraph type="secondary">
              将当前案件的分析结果、关联人物与批次数据打包导出。后端导出逻辑尚未接入，界面先预留入口。
            </Paragraph>
            <Text type="secondary">请在顶部选择当前案件后，再执行导出操作。</Text>
          </div>
        }
      />
      <Button type="primary" icon={<ExportOutlined />} disabled>
        导出当前案件（即将上线）
      </Button>
    </div>
  );
}

export default FusionExportCasePanel;
