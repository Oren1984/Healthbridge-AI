import { Component, type ErrorInfo, type ReactNode } from "react";

/** Contains render errors to the page area instead of blanking the whole app. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("render error", error.message, info.componentStack?.split("\n").slice(0, 3).join(" "));
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="card m-6 p-6 max-w-xl">
        <h1 className="text-lg font-semibold">Something went wrong on this page · משהו השתבש בעמוד זה</h1>
        <p className="mt-2 text-sm text-muted">{this.state.error.message}</p>
        <button className="mt-4 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-on-brand" onClick={() => location.reload()}>Reload · טעינה מחדש</button>
      </div>
    );
  }
}
