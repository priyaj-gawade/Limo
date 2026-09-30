import { useEffect, useRef, useState } from 'react'
import { Home } from './Home'
import { Onboarding } from './Onboarding'
import { StarPromptCard } from './StarPromptCard'
import { TabBar } from './TabBar'

interface AppFrameProps {
  /** resolved before first paint (main.tsx) so home never flashes under the overlay */
  initialOnboardingSeen: boolean
}

export function AppFrame({ initialOnboardingSeen }: AppFrameProps) {
  const [homeActive, setHomeActive] = useState(true)
  const [showOnboarding, setShowOnboarding] = useState(!initialOnboardingSeen)
  const [starPromptDocOpens, setStarPromptDocOpens] = useState<number | null>(null)
  const [homeView, setHomeView] = useState<'limo' | 'office'>('limo')
  const [iframeKey, setIframeKey] = useState(0)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    const applyTabs = (tabs: Awaited<ReturnType<typeof window.aiOfficeTabs.list>>) => {
      const active = tabs.find((tab) => tab.active)
      setHomeActive(!active || active.kind === 'home')
    }
    void window.aiOfficeTabs.list().then(applyTabs)
    return window.aiOfficeTabs.onChanged(applyTabs)
  }, [])

  useEffect(() => {
    const handleMsg = (e: MessageEvent) => {
      if (e.data?.type === 'SWITCH_TO_OFFICE') {
        setHomeView('office')
      } else if (e.data?.type === 'SWITCH_TO_LIMO') {
        setHomeView('limo')
        iframeRef.current?.contentWindow?.postMessage({ type: 'SWITCH_TO_LIMO' }, '*')
      }
    }
    window.addEventListener('message', handleMsg)
    return () => window.removeEventListener('message', handleMsg)
  }, [])

  useEffect(() => {
    if (homeView === 'limo') {
      iframeRef.current?.contentWindow?.postMessage({ type: 'SWITCH_TO_LIMO' }, '*')
    }
  }, [homeView])

  // The "star us" invitation is decided (and counted as shown) by the main
  // process; ask once per session, and never while onboarding is up — a
  // first-run user can't have met the value threshold anyway.
  useEffect(() => {
    if (showOnboarding) return
    let alive = true
    void window.aiOffice.starPromptShouldShow?.().then((result) => {
      if (alive && result.show) setStarPromptDocOpens(result.docOpens)
    })
    return () => {
      alive = false
    }
  }, [showOnboarding])

  const finishOnboarding = async (): Promise<boolean> => {
    try {
      const persisted = await window.aiOffice.setOnboardingSeen()
      if (!persisted) return false
      setShowOnboarding(false)
      return true
    } catch {
      return false
    }
  }

  return (
    <div className="app-frame">
      <TabBar />
      {/* docs/sheets tabs render as WebContentsView children of this window, positioned
       * by the main process to cover this area — only Home paints its own content here. */}
      <div className="app-frame-content" style={{ visibility: homeActive ? 'visible' : 'hidden' }}>
        <div
          className="shell-content-container"
          style={{
            display: homeView === 'limo' ? 'block' : 'none',
            width: '100%',
            height: '100%',
          }}
        >
          <iframe
            ref={iframeRef}
            key={iframeKey}
            src="http://127.0.0.1:5190"
            className="limo-embedded-frame"
            title="Limo AI"
            onLoad={() => {
              if (homeView === 'limo') {
                iframeRef.current?.contentWindow?.postMessage({ type: 'SWITCH_TO_LIMO' }, '*')
              }
            }}
            style={{ width: '100%', height: '100%', border: 'none' }}
          />
        </div>

        <div
          className="shell-content-container"
          style={{
            display: homeView === 'office' ? 'block' : 'none',
            width: '100%',
            height: '100%',
            overflow: 'auto',
          }}
        >
          <Home
            currentView={homeView}
            onSwitchToLimo={() => {
              setHomeView('limo')
              iframeRef.current?.contentWindow?.postMessage({ type: 'SWITCH_TO_LIMO' }, '*')
            }}
          />
        </div>
      </div>
      {/* editor WebContentsViews paint above ALL shell DOM, so the overlay only
       * renders while the home tab is active — it comes back when home does */}
      {showOnboarding && homeActive && <Onboarding onDone={finishOnboarding} />}
      {starPromptDocOpens !== null && !showOnboarding && homeActive && (
        <StarPromptCard docOpens={starPromptDocOpens} onClose={() => setStarPromptDocOpens(null)} />
      )}
    </div>
  )
}
