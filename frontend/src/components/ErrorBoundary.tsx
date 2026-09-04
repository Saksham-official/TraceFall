import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

import { Banner, Button } from './ui'

/**
 * Last line of defence. A rendering bug must not leave an investigator staring at a blank
 * screen wondering whether the analysis is still running.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto max-w-lg p-6">
        <Banner tone="error" title="This screen failed to render">
          <p>Your session and your case data are unaffected. Reload to continue.</p>
          <Button variant="secondary" className="mt-2" onClick={() => location.reload()}>
            Reload
          </Button>
        </Banner>
      </div>
    )
  }
}
