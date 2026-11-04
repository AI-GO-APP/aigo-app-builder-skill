"""AI GO Custom App 專案腳手架生成器"""
import json
import os
from typing import Optional

PROTECTED_FILES = {"src/api.ts", "src/db.ts", "src/action.ts", "src/data.json", "src/db.json", "src/actions.json"}

# === 模板 ===
MAIN_TSX = '''import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./App.css";

function findRoot(): HTMLElement | null {
  const el = document.getElementById("root");
  if (el) return el;
  const hosts = document.querySelectorAll(
    "[data-custom-app-runtime], custom-app-runtime, [data-external-app-runtime]"
  );
  for (let i = 0; i < hosts.length; i++) {
    const sr = (hosts[i] as any).shadowRoot;
    if (sr) {
      const r = sr.getElementById("root") || sr.querySelector("div");
      if (r) return r as HTMLElement;
    }
  }
  return null;
}

const root = findRoot();
if (root) {
  ReactDOM.createRoot(root).render(<App />);
} else {
  console.error("[Custom App] 找不到 #root 元素");
}
'''

APP_CSS = ''':host, :root {
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --background: #f8fafc;
  --card-bg: #ffffff;
  --text: #1e293b;
  --text-muted: #64748b;
  --border: #e2e8f0;
  --danger: #ef4444;
  --success: #22c55e;
  font-family: "Inter", "Microsoft JhengHei", system-ui, sans-serif;
  font-size: 14px;
  color: var(--text);
  line-height: 1.6;
}

html, :host { box-sizing: border-box; }
*, *::before, *::after { box-sizing: inherit; margin: 0; padding: 0; }

.app-container { height: 100vh; overflow-y: auto; background: var(--background); }
.page-content { max-width: 1200px; margin: 0 auto; padding: 24px; }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.btn { padding: 8px 16px; border: none; border-radius: 6px; font-size: 14px; cursor: pointer; transition: all 0.15s; }
.btn-primary { background: var(--primary); color: #fff; }
.btn-primary:hover { background: var(--primary-hover); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* 資料狀態（核心規則 30）：載入中 skeleton、空資料／錯誤提示 */
.skeleton { height: 44px; margin-bottom: 12px; border-radius: 8px;
  background: linear-gradient(90deg, var(--border) 25%, #f1f5f9 50%, var(--border) 75%);
  background-size: 200% 100%; animation: skeleton-shimmer 1.2s ease-in-out infinite; }
@keyframes skeleton-shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
.state-box { padding: 32px 20px; text-align: center; color: var(--text-muted);
  background: var(--card-bg); border: 1px dashed var(--border); border-radius: 8px; }
.state-box .btn { margin-top: 12px; }
.state-error { color: var(--danger); border-color: var(--danger); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
'''

LAYOUT_TSX = '''import React from "react";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <div className="app-container">{children}</div>;
}
'''

SINGLE_APP_TSX = '''import React from "react";
import AppLayout from "./components/AppLayout";
import DashboardPage from "./pages/DashboardPage";

export default function App() {
  return (
    <AppLayout>
      <DashboardPage />
    </AppLayout>
  );
}
'''

MULTI_APP_TSX = '''import React, { Suspense, lazy } from "react";
import { HashRouter, Routes, Route } from "react-router-dom";
import AppLayout from "./components/AppLayout";

const Dashboard = lazy(() => import("./pages/DashboardPage"));
const NotFound = lazy(() => import("./pages/NotFoundPage"));

function Loading() {
  return <div style={{ padding: 40, textAlign: "center", color: "#888" }}>載入中...</div>;
}

export default function App() {
  return (
    <HashRouter>
      <AppLayout>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </AppLayout>
    </HashRouter>
  );
}
'''

DATA_STATE_TSX = '''import React from "react";

// 資料畫面的四態（核心規則 30）：載入中 → skeleton；錯誤 → 訊息＋重試；空資料 → 提示；其餘渲染 children
type Props = {
  loading: boolean;
  error?: string | null;
  empty?: boolean;
  emptyText?: string;
  onRetry?: () => void;
  rows?: number;
  children?: React.ReactNode;
};

export default function DataState({ loading, error, empty, emptyText = "目前沒有資料", onRetry, rows = 3, children }: Props) {
  if (loading) {
    return (
      <div aria-busy="true" aria-live="polite">
        {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" />)}
        <span className="sr-only">載入中…</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="state-box state-error" role="alert">
        <p>資料載入失敗：{error}</p>
        {onRetry && <button className="btn btn-primary" onClick={onRetry}>重試</button>}
      </div>
    );
  }
  if (empty) return <div className="state-box">{emptyText}</div>;
  return <>{children}</>;
}
'''

DASHBOARD_TSX = '''import React, { useCallback, useEffect, useState } from "react";
import DataState from "../components/DataState";

type Item = { id: string; name: string };
type Load<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string };

// TODO：換成實際的資料來源，例如
//   const { data } = await runAction("list_items", {});  return data?.items ?? [];
async function loadItems(): Promise<Item[]> {
  return [];
}

export default function DashboardPage() {
  const [state, setState] = useState<Load<Item[]>>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let stale = false;
    setState({ status: "loading" });
    loadItems()
      .then((data) => { if (!stale) setState({ status: "ready", data }); })
      .catch((e: Error) => { if (!stale) setState({ status: "error", message: e.message || "未知錯誤" }); });
    return () => { stale = true; };
  }, [reloadKey]);

  return (
    <div className="page-content">
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>總覽</h1>
      <DataState
        loading={state.status === "loading"}
        error={state.status === "error" ? state.message : null}
        empty={state.status === "ready" && state.data.length === 0}
        emptyText="還沒有資料，開始建立您的應用程式。"
        onRetry={reload}
      >
        {state.status === "ready" &&
          state.data.map((item) => <div key={item.id} className="card">{item.name}</div>)}
      </DataState>
    </div>
  );
}
'''

NOT_FOUND_TSX = '''import React from "react";

export default function NotFoundPage() {
  return (
    <div className="page-content" style={{ textAlign: "center", paddingTop: 80 }}>
      <h1 style={{ fontSize: 48, color: "var(--text-muted)" }}>404</h1>
      <p>找不到此頁面</p>
    </div>
  );
}
'''

HELLO_ACTION = '''def execute(ctx):
    """範例 Server-Side Action"""
    name = ctx.params.get("name", "World")
    ctx.response.json({"message": f"Hello, {name}!"})
'''

GITIGNORE = ".aigo/\nnode_modules/\n.venv/\n__pycache__/\n"


def _write_file(base: str, rel_path: str, content: str) -> None:
    """寫入檔案（自動建立目錄）"""
    full = os.path.join(base, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def scaffold_new_project(project_path: str, project_type: str = "single") -> list[str]:
    """生成全新專案結構"""
    created = []

    def write(rel: str, content: str):
        _write_file(project_path, rel, content)
        created.append(rel)

    write(".gitignore", GITIGNORE)
    pkg = json.dumps({
        "name": "my-custom-app", "private": True, "version": "0.0.1", "type": "module",
        "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0", "react-router-dom": "^6.22.3",
                         "react-hot-toast": "^2.4.1", "lucide-react": "^0.460.0"},
        "devDependencies": {"@types/react": "^18.2.0", "@types/react-dom": "^18.2.0", "typescript": "^5.0.0"},
    }, indent=2, ensure_ascii=False)
    write("package.json", pkg)
    write("src/main.tsx", MAIN_TSX)
    write("src/App.css", APP_CSS)
    write("src/components/AppLayout.tsx", LAYOUT_TSX)
    write("src/components/DataState.tsx", DATA_STATE_TSX)
    write("src/pages/DashboardPage.tsx", DASHBOARD_TSX)
    write("actions/manifest.json", json.dumps(
        {"hello_action": {"description": "範例 Action", "is_enabled": True, "timeout_ms": 10000}},
        indent=2, ensure_ascii=False))
    write("actions/hello_action.py", HELLO_ACTION)

    if project_type == "single":
        write("src/App.tsx", SINGLE_APP_TSX)
    else:
        write("src/App.tsx", MULTI_APP_TSX)
        write("src/pages/NotFoundPage.tsx", NOT_FOUND_TSX)
        write("src/pages/_manifest.json", json.dumps({"pages": [
            {"name": "DashboardPage", "path": "/", "title": "總覽"},
            {"name": "NotFoundPage", "path": "*", "title": "404"},
        ]}, indent=2, ensure_ascii=False))

    # 建立空 config
    from aigo_auth import init_config
    init_config(project_path)
    created.append(".aigo/config.json")

    return created


def download_vfs_to_local(vfs_state: dict, project_path: str) -> list[str]:
    """將雲端 VFS 下載為本地檔案結構"""
    created = []
    for path, content in vfs_state.items():
        if path in PROTECTED_FILES:
            continue
        _write_file(project_path, path, content)
        created.append(path)

    gi_path = os.path.join(project_path, ".gitignore")
    if not os.path.exists(gi_path):
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write(GITIGNORE)
        created.append(".gitignore")

    return created
