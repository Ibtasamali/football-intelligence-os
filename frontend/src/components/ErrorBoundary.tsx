import { Component, type ReactNode } from "react";

/** Never show a black screen: any render error shows a friendly recover panel instead. */
export default class ErrorBoundary extends Component<{ children: ReactNode; name?: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error(`[${this.props.name ?? "app"}]`, error);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="grid h-full min-h-[200px] place-items-center p-6">
        <div className="glass-strong max-w-md p-6 text-center">
          <div className="font-display text-lg font-semibold text-white">This panel hit a problem</div>
          <div className="mt-1 text-[13px] text-slate-400">The rest of the app keeps running.</div>
          <button className="btn-primary mx-auto mt-4" onClick={() => this.setState({ error: null })}>Recover</button>
        </div>
      </div>
    );
  }
}
