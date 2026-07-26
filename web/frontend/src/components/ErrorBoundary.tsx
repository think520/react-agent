import { Component, type ErrorInfo, type ReactNode } from "react";
import { RotateCcw } from "lucide-react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * 路由层兜底：任何页面渲染异常都不再白屏，而是给出可恢复的提示。
 * 样式贴合 warm-paper 主题（复用 styles.css 中的 --paper/--ink 变量）。
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[bobodan] 页面渲染出现异常", error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="error-boundary" role="alert">
        <img
          className="brand-expression"
          src="/assets/brand/expressions/bobodan-expression-curious.webp"
          width="64"
          height="64"
          alt=""
        />
        <h1>页面出了点问题</h1>
        <p>这不影响你已保存的学习数据。重新加载通常就能恢复；如果反复出现，请重启 Bobodan 后端后再试。</p>
        <button type="button" className="primary-button" onClick={this.handleReload}>
          <RotateCcw size={16} />重新加载
        </button>
        <details>
          <summary>技术细节</summary>
          <pre>{this.state.error.message || String(this.state.error)}</pre>
        </details>
      </div>
    );
  }
}
