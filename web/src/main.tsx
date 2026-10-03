import { Component, StrictMode } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './styles.css';

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* No raw records in logs. */ }
  render() {
    return this.state.failed ? <main className="fatal-error" role="alert"><h1>工作台界面未能完成显示</h1><p>当前结果已阻断。请刷新页面，重新核验选择。</p><button onClick={() => location.reload()}>重新加载</button></main> : this.props.children;
  }
}
createRoot(document.getElementById('root')!).render(<StrictMode><ErrorBoundary><App /></ErrorBoundary></StrictMode>);
