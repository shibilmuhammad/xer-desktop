import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { Upload, X, Send, BarChart2, Activity, Calendar, Clock, User, Table as TableIcon, Search, ChevronLeft, ChevronRight, Filter, Eye, ListTree, Link as LinkIcon, Info, CheckCircle, Circle, Loader2, AlertTriangle, TrendingDown, Zap, Trash2, Globe, Cpu, Maximize2, Minimize2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import logo from './assets/logo.png'

import VersionManagerSection from './components/VersionManagerSection'
import OptimizedChatInput from './components/OptimizedChatInput'
import Sidebar from './components/ui/Sidebar'
import AuditDashboard from './components/audit/AuditDashboard'
import AssessmentTable from './components/audit/AssessmentTable'
import AuditAiChat from './components/audit/AuditAiChat'
import ControllerToolbar from './components/controller/ControllerToolbar'
import ControllerTable from './components/controller/ControllerTable'
import ControllerFloatingChat from './components/controller/ControllerFloatingChat'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authError, setAuthError] = useState(null)
  const [userName, setUserName] = useState('')
  
  const [setupStatus, setSetupStatus] = useState('Initializing Application...')
  const [setupError, setSetupError] = useState(null)
  const [isSetupComplete, setIsSetupComplete] = useState(false)

  const [baselineLoaded, setBaselineLoaded] = useState(false)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [viewMode, setViewMode] = useState('audit') // 'audit' or 'controller'
  const [viewerTable, setViewerTable] = useState('TASK')
  const [tableData, setTableData] = useState({ records: [], total: 0 })
  const [tablePage, setTablePage] = useState(1)
  const [tableSearch, setTableSearch] = useState('')
  const [viewerFilter, setViewerFilter] = useState('ALL') // 'ALL', 'CRITICAL', 'NEG_FLOAT', 'POS_FLOAT', 'DELAYED', 'DELAYED_CRITICAL', 'DELAYED_NEGATIVE'
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [versions, setVersions] = useState([])
  const [selectedVersionId, setSelectedVersionId] = useState('baseline')
  const [aiConfig, setAiConfig] = useState({ provider: 'openai', model: 'gpt-4o', has_openai_key: false })
  const [isUpdatingAI, setIsUpdatingAI] = useState(false)
  
  // Independent Controller Chat State
  const [controllerMessages, setControllerMessages] = useState([])
  const [controllerQuery, setControllerQuery] = useState('')
  const [isControllerChatOpen, setIsControllerChatOpen] = useState(false)
  const [isControllerTyping, setIsControllerTyping] = useState(false)
  const [isControllerChatExpanded, setIsControllerChatExpanded] = useState(false)
  const [controllerChatPos, setControllerChatPos] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const dragStartPos = useRef({ x: 0, y: 0 })
  
  const chatEndRef = useRef(null)
  const controllerChatEndRef = useRef(null)

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }
  
  const scrollControllerToBottom = () => {
    controllerChatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, isTyping])

  useEffect(() => {
    if (isControllerChatOpen) {
      scrollControllerToBottom()
    }
  }, [controllerMessages, isControllerTyping, isControllerChatOpen])

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return
      setControllerChatPos({
        x: e.clientX - dragStartPos.current.x,
        y: e.clientY - dragStartPos.current.y
      })
    }
    const handleMouseUp = () => setIsDragging(false)
    
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging])

  const handleDragStart = (e) => {
    // Only allow drag on the header itself, not children buttons
    if (e.target.closest('button')) return
    setIsDragging(true)
    dragStartPos.current = { 
      x: e.clientX - controllerChatPos.x, 
      y: e.clientY - controllerChatPos.y 
    }
  }

  const handleUpload = async (e, type = 'baseline') => {
    const file = e.target.files[0]
    if (!file) return

    setLoading(true)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('file_type', type)

    try {
      const res = await axios.post('/api/upload-xer', formData)
      if (res.data.success) {
        setStats(res.data.stats)
        if (type === 'baseline') setBaselineLoaded(true)
        setSelectedVersionId(res.data.version_id)
        fetchVersions()
      }
    } catch (err) {
      console.error(err)
      alert('Upload failed: ' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }

  const fetchTableData = async () => {
    try {
      let reqTable = viewerTable
      if (viewerTable === 'TASK') reqTable = 'HIERARCHY'
      if (viewerTable === 'WBS') reqTable = 'WBS_HIERARCHY'
      
      const res = await axios.get(`/api/xer-data?table=${reqTable}&page=${tablePage}&search=${tableSearch}&version_id=${selectedVersionId}&filter=${viewerFilter}`)
      setTableData(res.data)
    } catch (err) {
      console.error('Failed to fetch table data', err)
    }
  }

  const fetchVersions = async () => {
    try {
      const res = await axios.get('/api/versions')
      setVersions(res.data)
    } catch (err) {
      console.error('Failed to fetch versions', err)
    }
  }

  const fetchAIConfig = async () => {
    try {
      const res = await axios.get('/api/settings')
      setAiConfig(res.data)
    } catch (err) {
      console.error('Failed to fetch AI config', err)
    }
  }

  const handleUpdateAI = async (provider) => {
    setIsUpdatingAI(true)
    try {
      const formData = new FormData()
      formData.append('provider', provider)
      const res = await axios.post('/api/settings/update', formData)
      setAiConfig(res.data)
    } catch (err) {
      console.error('Failed to update AI config', err)
    } finally {
      setIsUpdatingAI(false)
    }
  }

  useEffect(() => {
    const checkExistingData = async () => {
      try {
        const res = await axios.get('/api/versions')
        if (res.data && res.data.length > 0) {
          setVersions(res.data)
          const hasBaseline = res.data.some(v => v.type === 'baseline')
          if (hasBaseline) {
            setBaselineLoaded(true)
            const bl = res.data.find(v => v.type === 'baseline')
            setSelectedVersionId(bl.id)
          }
        }
        fetchAIConfig()
      } catch (err) {
        console.error('Initialization check failed', err)
      }
    }
    
    if (isSetupComplete) {
      checkExistingData()
    }
  }, [isSetupComplete])

  // Sync stats when version changes
  useEffect(() => {
    const syncStats = async () => {
      if (!selectedVersionId) return
      try {
        const res = await axios.get(`/api/health?version_id=${selectedVersionId}`)
        setStats(res.data)
      } catch (err) {
        console.error('Failed to sync health stats', err)
      }
    }
    syncStats()
  }, [selectedVersionId])

  // Setup Effect (IPC Listeners)
  useEffect(() => {
    if (typeof window !== 'undefined' && window.require) {
      try {
        const { ipcRenderer } = window.require('electron')
        
        const removeStatus = ipcRenderer.on('setup-status', (e, msg) => setSetupStatus(msg))
        const removeError = ipcRenderer.on('setup-error', (e, err) => setSetupError(err))
        const removeComplete = ipcRenderer.on('setup-complete', (e, data) => {
          if (data && data.apiPort) {
             // Point axios directly at the backend — no /api prefix needed (Vite proxy handles that in browser)
             axios.defaults.baseURL = `http://127.0.0.1:${data.apiPort}`
             // Override all calls to strip /api prefix for direct backend access
             axios.interceptors.request.use((config) => {
               if (config.url && config.url.startsWith('/api/')) {
                 config.url = config.url.replace('/api/', '/')
               }
               return config
             })
          }
          setIsSetupComplete(true)
        })

        return () => {
          if (ipcRenderer.removeAllListeners) {
            ipcRenderer.removeAllListeners('setup-status')
            ipcRenderer.removeAllListeners('setup-error')
            ipcRenderer.removeAllListeners('setup-complete')
          }
        }
      } catch (err) {
         setIsSetupComplete(true)
      }
    } else {
      // Browser fallback (use proxy or default 8000)
      setIsSetupComplete(true)
    }
  }, [])

  // Authentication Effect
  useEffect(() => {
    let domainMatch = false;
    let uName = 'User';
    
    try {
      // Pull allowed domains from env (comma-separated), and add fallbacks dynamically
      const envDomains = import.meta.env.VITE_ALLOWED_DOMAIN 
        ? import.meta.env.VITE_ALLOWED_DOMAIN.split(',').map(d => d.trim().toLowerCase())
        : [];
      
      const allowedDomains = [...envDomains, "ellisdon", "desktop-0qlhho9", "ellisdon.com"];
      
      if (typeof window !== 'undefined' && window.process && window.process.env) {
        const platform = window.process.platform;
        const uDomain = window.process.env.USERDOMAIN || '';
        
        if (window.require) {
           try {
             uName = window.require('os').userInfo().username;
           } catch(e) {}
        }
        
        // Allow bypass on Mac for development, otherwise strict array domain check
        if (platform === 'darwin' || allowedDomains.includes(uDomain.toLowerCase()) || import.meta.env.DEV) {
          domainMatch = true;
        }
      } else {
        // Browser fallback
        domainMatch = import.meta.env.DEV ? true : false;
      }
    } catch (err) {
      console.error('Auth verification error', err);
    }

    if (!domainMatch) {
      setAuthError('Access restricted to EllisDon domain users');
    } else {
      setUserName(uName);
      setIsAuthenticated(true);
    }
  }, []);

  useEffect(() => {
    if (baselineLoaded) {
      fetchVersions()
    }
  }, [baselineLoaded])

  useEffect(() => {
    if (viewMode === 'controller' && baselineLoaded) {
      fetchTableData()
    }
  }, [viewMode, viewerTable, tablePage, tableSearch, selectedVersionId, viewerFilter])

  const handleAsk = async (submittedQuery) => {
    const q = typeof submittedQuery === 'string' ? submittedQuery : query;
    if (!q || isTyping) return
    const userMsg = { role: 'user', content: q }
    setMessages(prev => [...prev, userMsg])
    setQuery('')
    setIsTyping(true)
    
    try {
      const res = await axios.post('/api/ask', new URLSearchParams({ query: q }))
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.response }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error connecting to the schedule analyzer.' }])
    } finally {
      setIsTyping(false)
    }
  }

  const handleControllerAsk = async (submittedQuery) => {
    const q = typeof submittedQuery === 'string' ? submittedQuery : controllerQuery;
    if (!q || isControllerTyping) return
    const userMsg = { role: 'user', content: q }
    setControllerMessages(prev => [...prev, userMsg])
    setControllerQuery('')
    setIsControllerTyping(true)
    
    try {
      // Pass a context hint that we are in the Controller/Table view for comparisons
      const res = await axios.post('/api/ask', new URLSearchParams({ query: q }))
      setControllerMessages(prev => [...prev, { role: 'assistant', content: res.data.response }])
    } catch (err) {
      setControllerMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error connecting to the controller intelligence engine.' }])
    } finally {
      setIsControllerTyping(false)
    }
  }

  const handleDeleteVersion = async (e, versionId) => {
    e.stopPropagation()
    if (!window.confirm('Are you sure you want to delete this version?')) return
    
    try {
      await axios.delete(`/api/versions/${versionId}`)
      if (versionId === 'baseline') {
        setBaselineLoaded(false)
        setVersions([])
        setStats(null)
        setTableData({ records: [], total: 0 })
        setMessages([])
      } else {
        fetchVersions()
        if (selectedVersionId === versionId) {
          setSelectedVersionId('baseline')
        }
      }
    } catch (err) {
      console.error('Failed to delete version', err)
      alert('Failed to delete version')
    }
  }
  
  if (!isSetupComplete) {
     return (
       <div className="flex flex-col items-center justify-center h-screen bg-white text-center p-4">
         <img src={logo} alt="EllisDon Logo" className="h-12 mb-8 object-contain opacity-50" />
         {!setupError ? (
           <>
             <Loader2 size={40} className="text-blue-500 animate-spin mb-4" />
             <h2 className="text-xl font-bold mb-2 text-gray-900">Preparing Enterprise Environment</h2>
             <p className="text-xs font-bold text-gray-500 uppercase tracking-widest max-w-lg mt-4 px-4 py-2 bg-gray-50 rounded-lg">{setupStatus}</p>
           </>
         ) : (
           <>
             <AlertTriangle size={48} className="text-red-500 mb-4 animate-bounce" />
             <h2 className="text-red-600 text-xl font-bold mb-2">Startup Failed</h2>
             <p className="text-gray-700 mb-8 max-w-md bg-red-50 p-4 rounded-xl border border-red-100">{setupError}</p>
             <button onClick={() => window.location.reload()} className="px-6 py-2 bg-blue-600 text-white rounded-lg shadow font-medium">Retry Verification</button>
           </>
         )}
       </div>
     )
  }

  if (authError) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-gray-50 text-center p-4">
        <AlertTriangle size={64} className="text-red-500 mb-6" />
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Access Denied</h1>
        <p className="text-gray-600 font-medium">{authError}</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-white">
        <Loader2 size={40} className="text-blue-500 animate-spin mb-4" />
        <p className="text-sm font-semibold text-gray-500 uppercase tracking-widest">Verifying Domain Architecture...</p>
      </div>
    )
  }

  if (!baselineLoaded) {
    return (
      <div className="flex flex-col items-center justify-center h-screen text-center p-4 bg-white relative overflow-hidden">
        {loading && (
          <div className="absolute inset-0 z-50 bg-white/90 flex flex-col items-center justify-center backdrop-blur-sm animate-in fade-in duration-300">
            <div className="relative">
              <div className="absolute -inset-4 bg-blue-500/10 rounded-full animate-ping [animation-duration:2s]"></div>
              <img src={logo} alt="Loading..." className="h-16 relative z-10 animate-pulse" />
            </div>
            <p className="mt-8 text-blue-600 font-bold tracking-widest text-xs uppercase animate-pulse">Processing Schedule Data</p>
          </div>
        )}
        
        <img src={logo} alt="EllisDon Logo" className="h-12 mb-8 object-contain" />
        <h1 className="text-4xl font-bold mb-2">Welcome, {userName}</h1>
        <p className="text-gray-500 mb-10">Upload your Primavera P6 baseline XER file to begin analysis</p>
        
        <div className="w-full max-w-md p-10 border-2 border-dashed border-gray-200 rounded-2xl bg-white shadow-sm">
          <h3 className="text-xl font-semibold mb-6">Upload Baseline File</h3>
          <div className="bg-gray-50 p-8 rounded-xl relative flex flex-col items-center">
             <Upload size={48} className="text-gray-400 mb-4" />
             <p className="text-gray-700 font-medium">Drag and drop file here</p>
             <p className="text-xs text-gray-400 mb-6">Limit 200MB per file • XER</p>
             <label className="bg-white border border-gray-300 px-6 py-2.5 rounded-lg cursor-pointer text-sm font-medium hover:bg-gray-50 transition-colors shadow-sm">
               {loading ? 'Uploading...' : 'Browse files'}
               <input type="file" hidden accept=".xer" onChange={handleUpload} disabled={loading} />
             </label>
          </div>
        </div>
      </div>
    )
  }

  // P6 Style Date Formatter
  const formatP6Date = (dateStr) => {
    if (!dateStr || dateStr === 'None' || dateStr === 'nan' || dateStr === '-') return '-'
    try {
      const date = new Date(dateStr.split(' ')[0])
      if (isNaN(date.getTime())) return dateStr
      return new Intl.DateTimeFormat('en-GB', { 
        day: '2-digit',
        month: 'short', 
        year: 'numeric' 
      }).format(date)
    } catch (e) {
      return dateStr
    }
  }

  // Header Label Mapping
  const getHeaderLabel = (key) => {
    const labels = {
      'task_code': 'Activity ID',
      'task_name': 'Activity Name',
      'status': 'Status',
      'target_start_date': 'Planned Start',
      'target_end_date': 'Planned Finish',
      'act_start_date': 'Actual Start',
      'act_end_date': 'Actual Finish',
      'total_float_hr_cnt': 'Total Float (h)'
    }
    return labels[key] || key.replace(/_/g, ' ').replace('hr cnt', '(hrs)').replace('pred type', 'Type').toUpperCase()
  }

  return (
    <div className="flex h-screen w-screen bg-gray-50 overflow-hidden font-sans text-gray-950">
      <Sidebar 
        viewMode={viewMode}
        setViewMode={setViewMode}
        userName={userName}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col bg-white overflow-hidden">
        <div className="h-14 border-b border-gray-100 flex items-center px-6 gap-4 text-sm bg-gray-50/50">
          <div className="h-2 w-2 rounded-full bg-blue-500"></div>
          <span className="font-medium text-gray-600">Project:</span>
          <span className="font-bold text-gray-900">{stats?.data_source}</span>
          <span className="text-gray-300">|</span>
          <span className="font-medium text-gray-600">Period:</span>
          <span className="font-bold text-gray-900">{stats?.project_start} to {stats?.project_finish}</span>
        </div>

        {viewMode === 'audit' ? (
          <div className="flex-1 overflow-y-auto bg-gray-50/50 relative pb-48">
            <VersionManagerSection 
              versions={versions}
              selectedVersionId={selectedVersionId}
              setSelectedVersionId={setSelectedVersionId}
              handleDeleteVersion={handleDeleteVersion}
              handleUpload={handleUpload}
              loading={loading}
              mode="compact_row"
            />

            <AuditDashboard stats={stats} />
            {/* --- AI CHAT SECTION --- */}
            <div className="max-w-6xl mx-auto px-6 py-6 pb-24">
               {/* 14-Point Assessment Table (DCMA Standard) */}
               <AssessmentTable stats={stats} />
               {/* AI Audit Assistant */}
               <AuditAiChat 
                 messages={messages} 
                 isTyping={isTyping} 
                 handleAsk={handleAsk} 
                 chatEndRef={chatEndRef}
                 isUpdatingAI={isUpdatingAI}
                 handleUpdateAI={handleUpdateAI}
                 aiConfig={aiConfig}
                 stats={stats}
               />
            </div>
          </div>
        ) : viewMode === 'controller' ? (
          <div className="flex-1 flex flex-col overflow-hidden bg-gray-50/50">
            <ControllerToolbar 
              viewerTable={viewerTable}
              setViewerTable={setViewerTable}
              setTablePage={setTablePage}
              viewerFilter={viewerFilter}
              setViewerFilter={setViewerFilter}
              versions={versions}
              selectedVersionId={selectedVersionId}
              setSelectedVersionId={setSelectedVersionId}
              handleDeleteVersion={handleDeleteVersion}
              handleUpload={handleUpload}
              loading={loading}
              tableSearch={tableSearch}
              setTableSearch={setTableSearch}
              isControllerChatOpen={isControllerChatOpen}
              setIsControllerChatOpen={setIsControllerChatOpen}
              tableData={tableData}
            />
            <ControllerTable 
              tableData={tableData}
              viewerTable={viewerTable}
              viewerFilter={viewerFilter}
              setViewerFilter={setViewerFilter}
              tableSearch={tableSearch}
              setTableSearch={setTableSearch}
              tablePage={tablePage}
              setTablePage={setTablePage}
              formatP6Date={formatP6Date}
              getHeaderLabel={getHeaderLabel}
            />
            
            {/* Controller Intelligence - Independent Floating Chat */}
            <ControllerFloatingChat 
              controllerChatPos={controllerChatPos}
              isDragging={isDragging}
              isControllerChatExpanded={isControllerChatExpanded}
              isControllerChatOpen={isControllerChatOpen}
              handleDragStart={handleDragStart}
              setIsControllerChatExpanded={setIsControllerChatExpanded}
              setIsControllerChatOpen={setIsControllerChatOpen}
              controllerMessages={controllerMessages}
              isControllerTyping={isControllerTyping}
              controllerChatEndRef={controllerChatEndRef}
              handleControllerAsk={handleControllerAsk}
            />
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default App
