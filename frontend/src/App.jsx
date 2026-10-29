import React, { useState } from 'react'
import AskView from './views/AskView'
import SearchView from './views/SearchView'
import SyncView from './views/SyncView'

const TABS = [
  { key: 'ask', label: '질문' },
  { key: 'search', label: '검색' },
  { key: 'sync', label: '동기화' },
]

export default function App() {
  const [tab, setTab] = useState('ask')
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Confluence KB</div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? 'tab active' : 'tab'} onClick={() => setTab(t.key)}>{t.label}</button>
          ))}
        </nav>
      </header>
      <main className="content">
        {tab === 'ask' && <AskView />}
        {tab === 'search' && <SearchView />}
        {tab === 'sync' && <SyncView />}
      </main>
    </div>
  )
}
