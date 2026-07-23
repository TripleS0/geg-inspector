import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, theme as antdTheme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { HashRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { appTheme } from "./theme";
import "antd/dist/reset.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <ConfigProvider
    locale={zhCN}
    theme={{
      algorithm: antdTheme.defaultAlgorithm,
      token: {
        colorPrimary: appTheme.colorPrimary,
        colorInfo: appTheme.colorPrimary,
        colorLink: appTheme.colorLink,
        colorSuccess: "#52a368",
        colorWarning: "#e8a23c",
        colorError: "#d23b26",
        borderRadius: 10,
        wireframe: false,
      },
      components: {
        Button: {
          primaryShadow: "0 6px 16px rgba(217, 72, 50, 0.22)",
        },
        Progress: {
          defaultColor: appTheme.colorPrimary,
          remainingColor: "rgba(217, 72, 50, 0.12)",
        },
      },
    }}
  >
    <HashRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </HashRouter>
  </ConfigProvider>
);
