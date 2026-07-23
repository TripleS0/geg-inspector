import { useState } from "react";
import { Alert, Button, Form, Input, Typography, message } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const { Title, Paragraph, Text } = Typography;

function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) {
    return <Navigate to="/fusion-cockpit" replace />;
  }

  return (
    <div className="login-page">
      <div className="login-panel">
        <div className="login-brand">
          <img className="login-brand-mark" src="/logo.png" alt="智能数据分析平台" />
          <Title level={3} className="login-title">
            智能数据分析平台
          </Title>
          <Paragraph type="secondary" className="login-subtitle">
            请使用管理员分配的账号登录
          </Paragraph>
        </div>

        <Form
          layout="vertical"
          size="large"
          onFinish={async (values: { username: string; password: string }) => {
            setSubmitting(true);
            try {
              await login(values.username.trim(), values.password);
              message.success("登录成功");
              navigate("/fusion-cockpit", { replace: true });
            } catch (err) {
              message.error((err as Error).message.replace(/^\d+\s*/, "") || "登录失败");
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              autoComplete="current-password"
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            登录
          </Button>
        </Form>

        <Alert
          className="login-hint"
          type="info"
          showIcon
          message={
            <Text type="secondary">
              默认管理员账号：admin / admin123（首次启动自动创建，请尽快修改密码）
            </Text>
          }
        />
      </div>
    </div>
  );
}

export default LoginPage;
