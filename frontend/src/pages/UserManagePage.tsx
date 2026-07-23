import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { Navigate } from "react-router-dom";
import { api, AuthUser } from "../api";
import { useAuth } from "../auth/AuthContext";

const { Title, Paragraph } = Typography;

type UserFormValues = {
  username: string;
  password?: string;
  display_name?: string;
  role: "admin" | "user";
  is_active: boolean;
};

function UserManagePage() {
  const { user: currentUser, isAdmin } = useAuth();
  const [items, setItems] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AuthUser | null>(null);
  const [form] = Form.useForm<UserFormValues>();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listUsers();
      setItems(data.items);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void refresh();
  }, [isAdmin, refresh]);

  if (!isAdmin) {
    return <Navigate to="/fusion-cockpit" replace />;
  }

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({
      username: "",
      password: "",
      display_name: "",
      role: "user",
      is_active: true,
    });
    setModalOpen(true);
  };

  const openEdit = (row: AuthUser) => {
    setEditing(row);
    form.setFieldsValue({
      username: row.username,
      password: "",
      display_name: row.display_name,
      role: row.role === "admin" ? "admin" : "user",
      is_active: row.is_active,
    });
    setModalOpen(true);
  };

  const submit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await api.updateUser(editing.user_id, {
          display_name: values.display_name,
          role: values.role,
          is_active: values.is_active,
          password: values.password?.trim() || undefined,
        });
        message.success("用户已更新");
      } else {
        await api.createUser({
          username: values.username.trim(),
          password: values.password || "",
          display_name: values.display_name,
          role: values.role,
          is_active: values.is_active,
        });
        message.success("用户已创建");
      }
      setModalOpen(false);
      await refresh();
    } catch (err) {
      message.error((err as Error).message.replace(/^\d+\s*/, ""));
    }
  };

  return (
    <div className="app-card">
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            用户管理
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            仅管理员可创建、编辑、禁用或删除账号。无公开注册。
          </Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建用户
        </Button>
      </Space>

      <Table
        rowKey="user_id"
        loading={loading}
        dataSource={items}
        pagination={false}
        columns={[
          { title: "用户名", dataIndex: "username" },
          { title: "显示名", dataIndex: "display_name" },
          {
            title: "角色",
            dataIndex: "role",
            render: (role: string) =>
              role === "admin" ? <Tag color="volcano">管理员</Tag> : <Tag>普通用户</Tag>,
          },
          {
            title: "状态",
            dataIndex: "is_active",
            render: (active: boolean) =>
              active ? <Tag color="success">启用</Tag> : <Tag color="default">禁用</Tag>,
          },
          { title: "创建时间", dataIndex: "created_at", width: 180 },
          {
            title: "操作",
            width: 180,
            render: (_, row) => (
              <Space>
                <Button type="link" onClick={() => openEdit(row)}>
                  编辑
                </Button>
                <Popconfirm
                  title="确认删除该用户？"
                  disabled={row.user_id === currentUser?.user_id}
                  onConfirm={async () => {
                    try {
                      await api.deleteUser(row.user_id);
                      message.success("已删除");
                      await refresh();
                    } catch (err) {
                      message.error((err as Error).message.replace(/^\d+\s*/, ""));
                    }
                  }}
                >
                  <Button type="link" danger disabled={row.user_id === currentUser?.user_id}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? "编辑用户" : "新建用户"}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void submit()}
        destroyOnClose
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: "请输入用户名" }, { min: 2, message: "至少 2 个字符" }]}
          >
            <Input disabled={!!editing} autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="password"
            label={editing ? "新密码（留空不修改）" : "密码"}
            rules={
              editing
                ? [{ min: 6, message: "至少 6 个字符" }]
                : [
                    { required: true, message: "请输入密码" },
                    { min: 6, message: "至少 6 个字符" },
                  ]
            }
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名">
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "user", label: "普通用户" },
                { value: "admin", label: "管理员" },
              ]}
            />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default UserManagePage;
