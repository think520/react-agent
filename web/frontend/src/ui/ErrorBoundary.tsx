import { Component, type ReactNode } from "react";

interface BlockErrorBoundaryProps {
  children: ReactNode;
  /** Optional custom fallback; defaults to a quiet placeholder. */
  fallback?: ReactNode;
  onError?: (error: Error) => void;
}

interface BlockErrorBoundaryState {
  hasError: boolean;
}

/**
 * Block-level error boundary (FE-1): one card/message block crashing never
 * takes down the whole message or conversation.
 */
export class BlockErrorBoundary extends Component<
  BlockErrorBoundaryProps,
  BlockErrorBoundaryState
> {
  state: BlockErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): BlockErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    this.props.onError?.(error);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? <span className="ui-block-error">此卡片暂时无法显示。</span>;
    }
    return this.props.children;
  }
}
