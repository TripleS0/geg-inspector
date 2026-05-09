import { useState } from "react";
import { Alert, Button, Card, Progress, Space, Typography, Upload, message } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd";
import { api, pollTask } from "../api";

const { Dragger } = Upload;
const { Title, Paragraph } = Typography;

function DesensitizationPage() {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [progress, setProgress] = useState<{ percent: number; message: string }>({ percent: 0, message: "" });
  const [running, setRunning] = useState(false);
  const [resultLogs, setResultLogs] = useState<string[]>([]);
  const [outputs, setOutputs] = useState<string[]>([]);

  const onSubmit = async () => {
    if (running) return;
    if (files.length === 0) {
      message.warning("请先选择至少一个 .xlsx / .xls / .txt 文件");
      return;
    }

    try {
      setRunning(true);
      setResultLogs([]);
      setOutputs([]);
      setProgress({ percent: 5, message: "上传文件中…" });
      const realFiles = files
        .map((item) => item.originFileObj as File | undefined)
        .filter((file): file is File => Boolean(file));
      const { task_id } = await api.uploadDesensitizationFiles(realFiles);
      const status = await pollTask(task_id, (task) =>
        setProgress({ percent: Math.max(task.progress, 10), message: task.message })
      );
      const result = status.result || {};
      setProgress({ percent: 100, message: status.message });
      setResultLogs((result.logs as string[]) || []);
      setOutputs((result.outputs as string[]) || []);
      message.success("脱敏完成，结果已生成到“脱敏结果”文件夹");
    } catch (err) {
      message.error((err as Error).message || "脱敏失败");
    } finally {
      setRunning(false);
    }
  };

  const reset = () => {
    setFiles([]);
    setResultLogs([]);
    setOutputs([]);
    setProgress({ percent: 0, message: "" });
  };

  return (
    <Card className="app-card" bordered={false}>
      <Title level={4}>数据脱敏</Title>
      <Paragraph style={{ color: "#7c6d67", marginBottom: 16 }}>
        支持 .xlsx / .xls / .txt 文件批量脱敏，自动识别银行卡号和常见中文姓名，结果输出到文件所在目录下的“脱敏结果”文件夹。
      </Paragraph>
      <Dragger
        multiple
        beforeUpload={() => false}
        fileList={files}
        accept=".xlsx,.xls,.txt"
        onChange={(info) => setFiles(info.fileList)}
      >
        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
        <p className="ant-upload-text">点击或拖拽脱敏文件到此区域</p>
        <p className="ant-upload-hint">支持 txt、xlsx、xls，多文件会依次处理，数据仅在本机运行</p>
      </Dragger>
      <Space style={{ marginTop: 16 }}>
        <Button type="primary" loading={running} onClick={onSubmit}>开始脱敏</Button>
        <Button onClick={reset}>清空</Button>
      </Space>
      {progress.percent > 0 && (
        <div style={{ marginTop: 16 }}>
          <Progress percent={progress.percent} status={running ? "active" : "success"} />
          <div style={{ color: "#7c6d67", marginTop: 4 }}>{progress.message}</div>
        </div>
      )}
      {outputs.length > 0 && (
        <Alert
          type="success"
          style={{ marginTop: 16 }}
          message="脱敏结果"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {outputs.map((line) => (
                <li key={line} style={{ marginBottom: 4 }}>{line}</li>
              ))}
            </ul>
          }
          showIcon
        />
      )}
      {resultLogs.length > 0 && (
        <Alert
          type="info"
          style={{ marginTop: 16 }}
          message="处理日志"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {resultLogs.map((line) => (
                <li key={line} style={{ marginBottom: 4 }}>{line}</li>
              ))}
            </ul>
          }
          showIcon
        />
      )}
    </Card>
  );
}

export default DesensitizationPage;
