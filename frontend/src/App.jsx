import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { Upload, X, Send, BarChart2, Activity, Calendar, Clock, User, Table as TableIcon, Search, ChevronLeft, ChevronRight, Filter, Eye, ListTree, Link as LinkIcon, Info, CheckCircle, Circle, Loader2, AlertTriangle, TrendingDown, Zap, Trash2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import logo from './assets/logo.png'

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
  const chatEndRef = useRef(null)

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, isTyping])

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
      const res = await axios.get(`/api/xer-data?table=${viewerTable}&page=${tablePage}&search=${tableSearch}&version_id=${selectedVersionId}`)
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
  }, [viewMode, viewerTable, tablePage, tableSearch, selectedVersionId])

  const handleAsk = async () => {
    if (!query || isTyping) return
    const userMsg = { role: 'user', content: query }
    setMessages(prev => [...prev, userMsg])
    setQuery('')
    setIsTyping(true)
    
    try {
      const res = await axios.post('/api/ask', new URLSearchParams({ query }))
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.response }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error connecting to the schedule analyzer.' }])
    } finally {
      setIsTyping(false)
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
      return new Intl.DateTimeFormat('en-US', { 
        month: 'short', 
        day: 'numeric', 
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
      {/* Sidebar */}
      <div className="w-[300px] bg-[#f8f9fa] border-r border-gray-200 p-6 flex flex-col overflow-y-auto">
        <div className="mb-10">
          <img src={logo} alt="EllisDon Logo" className="h-8 object-contain" />
        </div>
        
        <h3 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 flex items-center gap-2">
          <BarChart2 size={16} className="text-blue-500" />
          Project Repository
        </h3>
        
        <div className="flex-1 overflow-y-auto pr-1 space-y-8">
          {/* Baseline Section */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-black text-gray-900 uppercase tracking-wider">Baseline Schedule</span>
              {!versions.find(v => v.type === 'baseline') && (
                <span className="text-[9px] font-bold text-orange-500 bg-orange-50 px-2 py-0.5 rounded border border-orange-100 italic">Required</span>
              )}
            </div>
            
            {versions.filter(v => v.type === 'baseline').length > 0 ? (
              versions.filter(v => v.type === 'baseline').map((v) => (
                <div 
                  key={v.id} 
                  onClick={() => { setSelectedVersionId(v.id); setViewMode('viewer'); }}
                  className={`p-3.5 rounded-2xl border cursor-pointer transition-all relative group shadow-sm ${selectedVersionId === v.id ? 'bg-blue-600 border-blue-600 shadow-blue-200' : 'bg-white border-gray-100 hover:border-blue-200'}`}
                >
                  <button 
                    onClick={(e) => handleDeleteVersion(e, v.id)}
                    className={`absolute top-2.5 right-2.5 p-1.5 rounded-lg transition-all z-10 ${selectedVersionId === v.id ? 'bg-white/20 text-white hover:bg-red-500' : 'bg-gray-50 text-gray-400 hover:text-red-600 hover:bg-red-50 border border-gray-100'}`}
                    title="Delete baseline"
                  >
                    <Trash2 size={14} />
                  </button>
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${selectedVersionId === v.id ? 'bg-white animate-pulse' : 'bg-blue-600'}`}></div>
                    <span className={`text-[10px] font-bold font-mono ${selectedVersionId === v.id ? 'text-blue-100' : 'text-gray-400'}`}>{v.data_date}</span>
                  </div>
                  <div className={`text-xs font-black truncate leading-tight pr-6 ${selectedVersionId === v.id ? 'text-white' : 'text-gray-900'}`}>
                    {v.name}
                  </div>
                </div>
              ))
            ) : (
              <label className="flex flex-col items-center justify-center p-5 border-2 border-dashed border-blue-100 rounded-2xl cursor-pointer hover:bg-blue-50/50 transition-all bg-blue-50/20 group">
                <Upload size={20} className="text-blue-400 mb-2 group-hover:scale-110 transition-transform" />
                <p className="text-[10px] font-black text-blue-700 uppercase tracking-tighter">Upload Master Baseline</p>
                <input type="file" hidden accept=".xer" onChange={(e) => handleUpload(e, 'baseline')} disabled={loading} />
              </label>
            )}
          </section>

          {/* Monthly Updates Section */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-black text-gray-950 uppercase tracking-wider font-sans">Monthly Updates</span>
              <span className="text-[10px] font-bold text-gray-400 bg-gray-100 px-2 py-0.5 rounded-md">{versions.filter(v => v.type === 'update').length}</span>
            </div>
            
            <div className="space-y-3">
              {versions.filter(v => v.type === 'update').map((v) => (
                <div 
                  key={v.id} 
                  onClick={() => { setSelectedVersionId(v.id); setViewMode('viewer'); }}
                  className={`p-3.5 rounded-2xl border cursor-pointer transition-all relative group shadow-sm ${selectedVersionId === v.id ? 'bg-blue-600 border-blue-600 shadow-blue-200' : 'bg-white border-gray-100 hover:border-blue-200'}`}
                >
                  <button 
                    onClick={(e) => handleDeleteVersion(e, v.id)}
                    className={`absolute top-2.5 right-2.5 p-1.5 rounded-lg transition-all z-10 ${selectedVersionId === v.id ? 'bg-white/20 text-white hover:bg-red-500' : 'bg-gray-50 text-gray-400 hover:text-red-600 hover:bg-red-50 border border-gray-100 shadow-sm'}`}
                    title="Delete update"
                  >
                    <Trash2 size={14} />
                  </button>
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${selectedVersionId === v.id ? 'bg-white' : 'bg-green-500'}`}></div>
                    <span className={`text-[10px] font-bold font-mono ${selectedVersionId === v.id ? 'text-blue-100' : 'text-gray-400'}`}>{v.data_date}</span>
                  </div>
                  <div className={`text-xs font-black truncate leading-tight pr-8 ${selectedVersionId === v.id ? 'text-white' : 'text-gray-900'}`}>
                    {v.name}
                  </div>
                </div>
              ))}

              <label className="flex flex-col items-center justify-center p-4 border-2 border-dashed border-gray-100 rounded-2xl cursor-pointer hover:bg-gray-50 transition-all group">
                <div className="flex items-center gap-2">
                  <Upload size={16} className="text-gray-400 group-hover:text-blue-500 transition-colors" />
                  <span className="text-[10px] font-black text-gray-500 uppercase group-hover:text-blue-700 transition-colors">Add Monthly Update</span>
                </div>
                <input type="file" hidden accept=".xer" onChange={(e) => handleUpload(e, 'update')} disabled={loading} />
              </label>
            </div>
          </section>
        </div>

        <hr className="my-6 border-gray-200" />

        <div className="space-y-2 mt-auto">
          <button 
            onClick={() => setViewMode('audit')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all ${viewMode === 'audit' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-600 hover:bg-gray-100'}`}
          >
            <Activity size={18} /> Project Audit
          </button>
          <button 
            onClick={() => setViewMode('controller')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all ${viewMode === 'controller' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-600 hover:bg-gray-100'}`}
          >
            <TableIcon size={18} /> Project Controller
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col bg-white">
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
            {/* The Persistent Project Audit Dashboard */}
            <div className="mx-6 my-6 bg-gray-900 rounded-[2.5rem] shadow-2xl relative overflow-hidden flex flex-col border border-white/10 max-h-[500px]">
              <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none">
                <BarChart2 size={240} />
              </div>
              
              {/* Sticky Header */}
              <div className="p-8 pb-4 relative z-20 w-full border-b border-white/5 bg-gray-900/50 backdrop-blur-md">
                <div className="flex items-center justify-between">
                  <h4 className="text-2xl font-bold flex items-center gap-3 text-white">
                    <Activity size={24} className="text-blue-500" />
                    Project Audit Summary
                  </h4>
                </div>
              </div>

              {/* Scrollable Content Area */}
              <div className="flex-1 overflow-y-auto custom-scrollbar p-8 pt-6 relative z-10 w-full">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 pb-4">
                  {/* Left Column: Health and Score Metrics */}
                  <div className="col-span-1 border-r border-white/10 pr-8">
                    <h5 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-4">Core Metrics</h5>
                    <div className="flex flex-col gap-5">
                      <div className="flex justify-between items-center">
                         <span className="text-gray-400 text-xs font-bold uppercase tracking-wider">Project Delay:</span>
                         <span className={`text-xl font-black ${stats?.delay_matrix?.projectDelayDays > 0 ? 'text-red-400' : 'text-green-400'}`}>
                           {stats?.delay_matrix?.projectDelayDays || 0} Days
                         </span>
                      </div>
                      <div className="flex justify-between items-center">
                         <span className="text-gray-400 text-xs font-bold uppercase tracking-wider">Critical Tasks:</span>
                         <span className="text-xl font-black text-white">{stats?.critical_count || 0}</span>
                      </div>
                      <div className="flex justify-between items-center">
                         <span className="text-gray-400 text-xs font-bold uppercase tracking-wider">Constraint:</span>
                         <span className={`text-lg font-black ${stats?.delay_matrix?.isConstrained ? 'text-red-400' : 'text-green-400'}`}>
                           {stats?.delay_matrix?.isConstrained ? 'Fixed-Finish' : 'Dynamic'}
                         </span>
                      </div>
                      <div className="flex justify-between items-center">
                         <span className="text-gray-400 text-xs font-bold uppercase tracking-wider">Negative Float:</span>
                         <span className="text-xl font-black text-orange-400">{stats?.negative_float_count || 0}</span>
                      </div>
                    </div>

                    {stats?.delay_matrix?.qualityIssues?.length > 0 && (
                      <div className="mt-6 pt-5 border-t border-white/5">
                        <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-3 block">Detected Integrity Issues:</span>
                        <div className="space-y-2">
                          {stats.delay_matrix.qualityIssues.map((issue, idx) => (
                            <div key={idx} className="flex items-center gap-2 text-[11px] font-medium text-gray-300">
                              <div className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0"></div>
                              <span className="leading-tight">{issue}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Middle Column: Top Delay Drivers */}
                  <div className="col-span-1 border-r border-white/10 pr-8">
                    <h5 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                       <TrendingDown size={14} className="text-red-400" />
                       Top Delay Drivers
                    </h5>
                    <div className="space-y-2">
                       {stats?.topDrivers?.length > 0 ? (
                         stats.topDrivers.map((d, i) => (
                           <div key={i} className="flex items-center justify-between p-2.5 bg-red-950/30 rounded border border-red-500/10">
                             <div className="flex flex-col">
                               <span className="text-xs font-black text-blue-300 leading-tight">{d.task_code}</span>
                               <span className="text-[10px] font-medium text-gray-400 w-36 truncate">{d.task_name}</span>
                             </div>
                             <span className="text-sm font-black text-red-500">+{d.delay_days}d</span>
                           </div>
                         ))
                       ) : (
                         <div className="text-sm text-gray-500 italic mt-2">No active delay drivers detected.</div>
                       )}
                    </div>
                  </div>

                  {/* Right Column: Highest Risk (Negative Float) */}
                  <div className="col-span-1">
                    <h5 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                       <Zap size={14} className="text-orange-400" />
                       Highest Risk (Negative Float)
                    </h5>
                    <div className="space-y-2">
                       {stats?.topRisks?.length > 0 ? (
                         stats.topRisks.map((r, i) => (
                           <div key={i} className="flex items-center justify-between p-2.5 bg-orange-950/20 rounded border border-orange-500/10">
                             <div className="flex flex-col">
                               <span className="text-xs font-black text-blue-300 leading-tight">{r.task_code}</span>
                               <span className="text-[10px] font-medium text-gray-400 w-36 truncate">{r.task_name}</span>
                             </div>
                             <span className="text-sm font-black text-orange-400">{r.float_hrs}h</span>
                           </div>
                         ))
                       ) : (
                         <div className="text-sm text-gray-500 italic mt-2">No negative float detected.</div>
                       )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* --- AI CHAT SECTION --- */}
            <div className="max-w-6xl mx-auto px-6 py-6 pb-24">
               <div className="bg-white rounded-[2.5rem] border border-gray-200 shadow-sm p-10 relative flex flex-col min-h-[500px]">
                 <div className="flex items-center gap-3 mb-10 border-b border-gray-100 pb-5">
                    <div className="w-10 h-10 rounded-2xl bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-200">
                       <Send size={18} className="text-white" />
                    </div>
                    <div>
                      <h3 className="text-xl font-black text-gray-900 tracking-tight">AI Audit Assistant</h3>
                      <p className="text-xs text-gray-400 font-medium tracking-tight">Contextual P6 forensic analysis</p>
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-widest bg-gray-100 text-gray-500 px-3 py-1.5 rounded-xl ml-auto border border-gray-200/50">
                      Session: {stats?.data_source}
                    </span>
                 </div>
              
              <div className="space-y-6">
                {messages.length === 0 ? (
                   <div className="text-center py-12 bg-white rounded-3xl border border-gray-100 shadow-sm">
                     <p className="text-gray-500 font-medium max-w-md mx-auto text-sm leading-relaxed">
                       Ask me anything about your project's delays, risks, or schedule logic. I'll construct analytical reports directly from your latest project data.
                     </p>
                   </div>
                ) : (
                   Array.isArray(messages) && messages.map((m, i) => {
                    if (!m) return null;
                    return (
                      <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        {m.role === 'assistant' && (
                          <div className="w-8 h-8 rounded-full bg-blue-100 flex flex-shrink-0 items-center justify-center mt-1 outline outline-2 outline-white shadow-sm">
                            <Activity size={14} className="text-blue-600" />
                          </div>
                        )}
                        <div className={`
                          max-w-[85%] px-5 py-4 rounded-2xl text-sm leading-relaxed shadow-sm transition-all
                          ${m.role === 'user' 
                            ? 'bg-blue-600 text-white rounded-tr-none shadow-md' 
                            : 'bg-white border border-gray-100 text-gray-800 rounded-tl-none ring-1 ring-black/5'}
                        `}>
                          {m.role === 'assistant' ? (
                            typeof m.content === 'object' && m.content !== null ? (
                              <div className="ai-structured-response flex flex-col gap-4 w-full">
                                <div className="summary text-gray-800 font-medium leading-relaxed markdown-table-content">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content.summary || ''}</ReactMarkdown>
                                </div>
                                
                                {m.content.metrics && Object.keys(m.content.metrics).length > 0 && (
                                  <div className="grid grid-cols-2 gap-3 mt-1">
                                    {Object.entries(m.content.metrics).map(([k, v]) => (
                                      <div key={k} className="bg-blue-50 border border-blue-100/50 p-3 rounded-xl shadow-sm">
                                        <div className="text-[10px] text-blue-500 font-black uppercase tracking-widest mb-1">
                                          {k.replace(/([A-Z])/g, ' $1').trim()}
                                        </div>
                                        <div className="text-xl font-black text-blue-900">{v}</div>
                                      </div>
                                    ))}
                                  </div>
                                )}

                                {m.content.insights && m.content.insights.length > 0 && (
                                  <div className="insights mt-2 bg-gray-50 p-4 rounded-xl border border-gray-100">
                                    <h5 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
                                      <Activity size={12} /> Key Analytical Insights
                                    </h5>
                                    <ul className="space-y-2.5">
                                      {m.content.insights.map((insight, idx) => (
                                        <li key={idx} className="flex gap-2.5 text-sm text-gray-700">
                                           <div className="mt-0.5"><CheckCircle size={14} className="text-green-500" /></div>
                                           <span className="leading-snug">{insight}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {m.content.drivers && m.content.drivers.length > 0 && (
                                  <div className="drivers mt-1">
                                    <h5 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                                      <TrendingDown size={12} className="text-red-400"/> Critical Impact Drivers
                                    </h5>
                                    <div className="flex flex-wrap gap-2">
                                      {m.content.drivers.map((driver, idx) => (
                                        <span key={idx} className="px-2.5 py-1 bg-red-50 text-red-700 border border-red-100 rounded text-xs font-mono font-bold shadow-sm">
                                          {driver.length > 60 ? driver.substring(0, 60) + "..." : driver}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            ) : (
                              <div className="markdown-content text-gray-800 leading-relaxed markdown-table-content">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}</ReactMarkdown>
                              </div>
                            )
                          ) : (
                            String(m.content || '')
                          )}
                        </div>
                      </div>
                    )
                   })
                )}
                
                {isTyping && (
                  <div className="flex gap-3 justify-start">
                    <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center flex-shrink-0 mt-1">
                      <Loader2 size={16} className="text-blue-400 animate-spin" />
                    </div>
                    <div className="bg-white border border-gray-100 text-gray-500 px-5 py-3.5 rounded-2xl rounded-tl-none text-sm flex items-center gap-3 shadow-sm italic">
                      <div className="flex gap-1">
                        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-duration:0.8s]"></div>
                        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-duration:0.8s] [animation-delay:0.2s]"></div>
                        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-duration:0.8s] [animation-delay:0.4s]"></div>
                      </div>
                      AI is inspecting schedule logic...
                    </div>
                  </div>
                )}
                 <div ref={chatEndRef} className="h-4" />
               </div>
               
               {/* Floating Chat Input Anchor */}
               <div className="absolute bottom-10 left-1/2 -translate-x-1/2 w-full max-w-2xl px-8 pointer-events-none">
                 <div className="w-full relative group pointer-events-auto shadow-2xl rounded-2xl ring-1 ring-black/5">
                   <input 
                     className="w-full pl-6 pr-14 py-4.5 bg-white/95 backdrop-blur-md border border-gray-200 shadow-xl rounded-2xl focus:ring-4 focus:ring-blue-500/10 focus:border-blue-400 transition-all outline-none text-sm placeholder:text-gray-400 font-medium"
                     placeholder="Ask about schedule delays, critical path, or risks..." 
                     value={query}
                     onChange={(e) => setQuery(e.target.value)}
                     onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
                   />
                   <button 
                     onClick={handleAsk}
                     className="absolute right-2.5 top-1/2 -translate-y-1/2 p-2.5 bg-blue-600 hover:bg-blue-700 rounded-xl transition-all shadow-lg shadow-blue-200 text-white"
                   >
                     <Send size={18} />
                   </button>
                 </div>
               </div>
             </div>
           </div>
         </div>
        ) : viewMode === 'controller' ? (
          <div className="flex-1 flex flex-col overflow-hidden bg-gray-50/50">
            {/* P6 Style Toolbar */}
            <div className="px-8 py-5 border-b border-gray-200 bg-white flex flex-col gap-4">
              <div className="flex flex-col md:flex-row gap-6 items-center justify-between">
                <div className="flex gap-1.5 p-1 bg-gray-100/80 rounded-xl overflow-x-auto max-w-full">
                  {[
                    { id: 'TASK', label: 'Activities', icon: <Activity size={14} /> },
                    { id: 'WBS', label: 'WBS', icon: <ListTree size={14} /> },
                    { id: 'RELATIONSHIPS', label: 'Relationships', icon: <LinkIcon size={14} /> },
                    { id: 'PROJECT', label: 'Project Info', icon: <Info size={14} /> }
                  ].map(t => (
                    <button 
                      key={t.id}
                      onClick={() => { setViewerTable(t.id); setTablePage(1); }}
                      className={`px-4 py-2.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap flex items-center gap-2 ${viewerTable === t.id ? 'bg-white text-blue-700 shadow-sm border border-gray-200/50' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-200/50'}`}
                    >
                      {t.icon} {t.label}
                    </button>
                  ))}
                </div>

                <div className="flex flex-1 gap-4 w-full md:w-auto justify-end items-center">
                  {/* Version Selector Dropdown */}
                  <div className="relative group shrink-0">
                     <div className="flex items-center gap-2 px-4 py-2 bg-gray-50 border border-gray-200 rounded-xl text-xs font-bold text-gray-700 cursor-pointer hover:bg-white transition-all">
                       <span className="text-[10px] text-gray-400 uppercase">Viewing:</span>
                       <select 
                          value={selectedVersionId}
                          onChange={(e) => { setSelectedVersionId(e.target.value); setTablePage(1); }}
                          className="bg-transparent border-none outline-none cursor-pointer text-gray-900 pr-2"
                       >
                          {versions.map(v => (
                             <option key={v.id} value={v.id}>
                                {v.type === 'baseline' ? 'Baseline' : `Update (${v.data_date})`}
                             </option>
                          ))}
                       </select>
                     </div>
                  </div>

                  <div className="relative flex-1 min-w-[200px] md:max-w-xs ml-2">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input 
                      type="text"
                      placeholder="Search by name or ID..."
                      value={tableSearch}
                      onChange={(e) => { setTableSearch(e.target.value); setTablePage(1); }}
                      className="w-full pl-10 pr-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500/20 outline-none transition-all focus:bg-white"
                    />
                  </div>
                </div>
              </div>
              
              {viewerTable === 'TASK' && (
                <div className="flex flex-wrap gap-2 pt-2 pb-1">
                  {[
                    { id: 'ALL', label: 'All', color: 'border-gray-200 text-gray-600' },
                    { id: 'CRITICAL', label: 'Critical (≤0)', color: 'border-red-200 text-red-600 bg-red-50/30' },
                    { id: 'NEG_FLOAT', label: 'Neg Float', color: 'border-red-400 text-red-800 bg-red-100/50' },
                    { id: 'DELAYED', label: 'Delayed', color: 'border-orange-200 text-orange-700 bg-orange-50/50' },
                    { id: 'DELAYED_CRITICAL', label: 'Delay+Crit', color: 'border-red-600 text-red-900 bg-red-100' },
                    { id: 'DELAYED_NEGATIVE', label: 'Delay+Neg', color: 'border-red-800 text-white bg-red-900' }
                  ].map(f => (
                    <button 
                      key={f.id}
                      onClick={() => setViewerFilter(f.id)}
                      className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-tighter border transition-all ${viewerFilter === f.id ? f.color + ' ring-2 ring-offset-1 focus:ring-blue-500' : 'bg-white border-gray-100 text-gray-400 hover:border-gray-300'}`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* P6 Legend & Health Dashboard */}
            {viewMode === 'controller' && viewerTable === 'TASK' && tableData.projectAnalysis && (
              <div className="px-8 mt-4 flex flex-col gap-4">


                <div className="flex flex-wrap gap-4 items-center">
                  <div className="px-4 py-2 bg-white rounded-xl border border-gray-200 shadow-sm flex items-center gap-3">
                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Project Variance:</span>
                    <span className={`text-sm font-black ${tableData.projectAnalysis.projectDelayDays > 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {tableData.projectAnalysis.projectDelayDays} DAYS
                    </span>
                    {tableData.projectAnalysis.healthMetrics?.isConstrained && (
                      <span className="text-[10px] font-black text-red-700 bg-red-50 px-2 py-0.5 rounded border border-red-100 animate-pulse">
                        CONSTRAINED
                      </span>
                    )}
                  </div>
                  <div className="flex gap-6 items-center text-[10px] font-bold uppercase tracking-wider text-gray-400">
                    <span className="flex items-center gap-1.5"><CheckCircle size={12} className="text-green-500" /> {tableData.projectAnalysis.healthMetrics?.completedTasks} Completed</span>
                    <span className="flex items-center gap-1.5"><Loader2 size={12} className="text-blue-500" /> {tableData.projectAnalysis.healthMetrics?.inProgressTasks} In Progress</span>
                    <span className="flex items-center gap-1.5 text-red-500/80"><AlertTriangle size={12} className="text-red-500" /> {tableData.projectAnalysis.healthMetrics?.delayedTasks} Delayed</span>
                  </div>
                  
                  {/* Health Score Summary in Table View */}
                  <div className="flex items-center gap-2 ml-auto pr-2 border-r border-gray-200">
                    <span className="text-[9px] font-black text-gray-400 uppercase">Health Status:</span>
                    <span className={`text-[10px] font-black uppercase tracking-tighter px-2.5 py-1 rounded w-24 text-center ${
                      tableData.projectAnalysis.healthMetrics?.healthStatus === 'Good' ? 'bg-green-600 text-white' :
                      tableData.projectAnalysis.healthMetrics?.healthStatus === 'Warning' ? 'bg-orange-500 text-white' :
                      'bg-red-600 text-white'
                    }`}>
                      {tableData.projectAnalysis.healthMetrics?.healthStatus || 'N/A'}
                    </span>
                  </div>
                  
                  {/* Delay-Float Matrix Summary */}
                  <div className="flex items-center gap-2 ml-auto">
                    <span className="text-[9px] font-black text-gray-400 uppercase mr-2 mt-0.5">Delay Breakdown:</span>
                    <div className="flex rounded-lg overflow-hidden border border-gray-100 shadow-sm">
                      <div className="px-3 py-1.5 bg-green-50 text-green-700 flex flex-col items-center min-w-[60px] border-r border-gray-100">
                        <span className="text-[12px] font-black leading-none">{tableData.projectAnalysis.delayFloatMatrix?.delayed_safe}</span>
                        <span className="text-[7px] font-bold uppercase opacity-60">Safe</span>
                      </div>
                      <div className="px-3 py-1.5 bg-red-50 text-red-600 flex flex-col items-center min-w-[60px] border-r border-gray-100">
                        <span className="text-[12px] font-black leading-none">{tableData.projectAnalysis.delayFloatMatrix?.delayed_critical}</span>
                        <span className="text-[7px] font-bold uppercase opacity-60">Critical</span>
                      </div>
                      <div className="px-3 py-1.5 bg-red-900 text-white flex flex-col items-center min-w-[60px]">
                        <span className="text-[12px] font-black leading-none">{tableData.projectAnalysis.delayFloatMatrix?.delayed_negative}</span>
                        <span className="text-[7px] font-bold uppercase opacity-60">Negative</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* P6 Style Table Grid */}
            <div className="flex-1 overflow-auto px-8 py-4">
              <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col min-h-full">
                <div className="overflow-x-auto scrollbar-thin scrollbar-thumb-gray-200">
                  <table className="min-w-[1200px] w-full text-left border-collapse table-fixed">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200 sticky top-0 z-20">
                        {tableData.records.length > 0 && 
                          (viewerTable === 'TASK' 
                            ? ['task_code', 'task_name', 'status', 'target_start_date', 'target_end_date', 'act_start_date', 'act_end_date', 'total_float_hr_cnt']
                            : viewerTable === 'WBS'
                            ? ['wbs_short_name', 'wbs_name', 'parent_wbs_id', 'seq_num', 'est_wt']
                            : viewerTable === 'RELATIONSHIPS'
                            ? ['task_id', 'pred_task_id', 'pred_type', 'lag_hr_cnt']
                            : Object.keys(tableData.records[0]).filter(k => !k.startsWith('_') && k !== 'is_critical')
                          ).map(key => (
                          <th 
                            key={key} 
                            className={`px-6 py-4 text-[10px] font-black text-gray-400 uppercase tracking-widest whitespace-nowrap bg-gray-50 
                              ${key === 'task_name' || key === 'wbs_name' ? 'text-left w-1/3' : 'text-center w-36'}
                              ${['target_start_date', 'act_start_date', 'total_float_hr_cnt'].includes(key) ? 'border-l border-gray-200/60' : ''}`}
                          >
                            {getHeaderLabel(key)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {tableData.records.length > 0 ? tableData.records
                        .filter(row => {
                          if (viewerFilter === 'ALL') return true;
                          const analysis = row._analysis || {};
                          if (viewerFilter === 'CRITICAL') return analysis.is_critical;
                          if (viewerFilter === 'NEG_FLOAT') return (analysis.float_hrs || 0) < 0;
                          if (viewerFilter === 'POS_FLOAT') return (analysis.float_hrs || 0) > 0;
                          if (viewerFilter === 'DELAYED') return analysis.delay_days > 0;
                          if (viewerFilter === 'DELAYED_CRITICAL') return analysis.delay_float_category === 'DELAYED_CRITICAL';
                          if (viewerFilter === 'DELAYED_NEGATIVE') return analysis.delay_float_category === 'DELAYED_NEGATIVE';
                          return true;
                        })
                        .map((row, i) => {
                          // USE DETERMINISTIC ANALYTICS FROM BACKEND
                          const analysis = row._analysis || {};
                          const status = analysis.status;
                          const isDelayed = analysis.delay_days > 0;
                          const isCritical = analysis.is_critical;
                          const isNegativeFloat = (analysis.float_hrs || 0) < 0;
                          const category = analysis.delay_float_category;
                          
                          let statusConfig = { label: 'Not Started', color: 'bg-gray-100 text-gray-500', icon: <Circle size={12} /> };
                          
                          if (status === 'COMPLETED') {
                            statusConfig = { label: 'Completed', color: 'bg-green-100 text-green-700', icon: <CheckCircle size={12} /> };
                          } else if (status === 'IN_PROGRESS') {
                            statusConfig = { label: 'In Progress', color: 'bg-blue-100 text-blue-700 border border-blue-200', icon: <Loader2 size={12} className="animate-spin-slow" /> };
                          } else if (isDelayed) {
                            statusConfig = { label: 'Delayed', color: 'bg-orange-100 text-orange-700 border border-orange-200', icon: <AlertTriangle size={12} /> };
                          }

                          // Priority Styling
                          let rowClass = 'hover:bg-blue-50/40 transition-colors group';
                          if (category === 'DELAYED_NEGATIVE' || isNegativeFloat) rowClass += ' bg-red-100/40 border-l-4 border-red-900';
                          else if (category === 'DELAYED_CRITICAL') rowClass += ' bg-red-50';
                          else if (isDelayed) rowClass += ' bg-orange-50/20';

                          return (
                            <tr key={i} className={rowClass}>
                              {(viewerTable === 'TASK' 
                                ? ['task_code', 'task_name', 'status', 'target_start_date', 'target_end_date', 'act_start_date', 'act_end_date', 'total_float_hr_cnt']
                                : viewerTable === 'WBS'
                                ? ['wbs_short_name', 'wbs_name', 'parent_wbs_id', 'seq_num', 'est_wt']
                                : viewerTable === 'RELATIONSHIPS'
                                ? ['task_id', 'pred_task_id', 'pred_type', 'lag_hr_cnt']
                                : Object.entries(row).filter(([k]) => !k.startsWith('_') && k !== 'is_critical').map(([k]) => k)
                              ).map((key, j) => (
                                <td key={j} className={`px-6 py-2.5 text-xs whitespace-nowrap text-center 
                                  ${key === 'task_name' || key === 'wbs_name' ? 'font-medium text-gray-900 text-left max-w-sm' : 'text-gray-600'}
                                  ${['target_start_date', 'act_start_date', 'total_float_hr_cnt'].includes(key) ? 'border-l border-gray-100/50' : ''}`}>
                                  {key === 'status' ? (
                                    <div className="flex justify-center">
                                      <span title={`Delay: ${analysis.delay_days} days`} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-tight shadow-sm cursor-help ${statusConfig.color}`}>
                                        {statusConfig.icon}
                                        {statusConfig.label}
                                      </span>
                                    </div>
                                  ) : key === 'total_float_hr_cnt' ? (
                                    <span className={isDelayed ? 'text-red-700 font-black' : isCritical ? 'text-red-600 font-bold' : ''}>
                                      {row[key]}
                                    </span>
                                  ) : ['target_start_date', 'target_end_date', 'act_start_date', 'act_end_date'].includes(key) ? (
                                    <span 
                                      className={`font-semibold text-[11px] ${key === 'act_end_date' && analysis.is_predicted ? 'text-blue-500/70 italic cursor-help' : 'text-gray-700'}`}
                                      title={key === 'act_end_date' && analysis.is_predicted ? 'Using planned date (task not completed)' : ''}
                                    >
                                      {key === 'act_end_date' ? formatP6Date(analysis.current_end_date) : formatP6Date(row[key])}
                                    </span>
                                  ) : key === 'task_name' || key === 'wbs_name' ? (
                                    <div className="flex items-center gap-2 truncate">
                                      {key === 'wbs_name' && row.parent_wbs_id && <span className="text-gray-300">└─</span>}
                                      <span className="truncate">{row[key]}</span>
                                    </div>
                                  ) : (
                                    String(row[key] || '-')
                                  )}
                                </td>
                              ))}
                            </tr>
                          );
                        }) : (
                        <tr>
                          <td colSpan="100" className="px-6 py-32 text-center">
                            <div className="flex flex-col items-center gap-3 text-gray-400">
                              <Search size={48} className="opacity-20 mb-2" />
                              <p className="text-sm font-medium italic">No schedule data found for this specific criteria</p>
                              <button onClick={() => {setTableSearch(''); setViewerFilter('ALL');}} className="text-xs text-blue-600 font-bold hover:underline">Reset filters</button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* P6 Style Pagination Footer */}
            <div className="px-8 py-4 bg-white border-t border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-6">
                <p className="text-[11px] text-gray-400 font-bold uppercase tracking-wider">
                  Records: <span className="text-gray-900 font-black">{tableData.records.length}</span> / <span className="text-gray-500">{tableData.total}</span>
                </p>
                <div className="h-4 w-px bg-gray-200"></div>
                {viewerTable === 'TASK' && tableData.projectAnalysis && (
                   <div className="flex gap-4">
                     <p className="text-[11px] text-gray-400 font-bold uppercase tracking-wider">
                       Critical: <span className="text-red-500 font-black">{tableData.projectAnalysis.healthMetrics?.criticalCount}</span>
                     </p>
                     <p className="text-[11px] text-gray-400 font-bold uppercase tracking-wider">
                       In Progress: <span className="text-blue-500 font-black">{tableData.projectAnalysis.healthMetrics?.inProgressTasks}</span>
                     </p>
                   </div>
                )}
              </div>
              
              <div className="flex items-center gap-3">
                <button 
                  disabled={tablePage === 1}
                  onClick={() => setTablePage(p => p - 1)}
                  className="p-2.5 border border-gray-200 rounded-xl hover:bg-gray-50 disabled:opacity-30 transition-all shadow-sm flex items-center justify-center"
                >
                  <ChevronLeft size={16} className="text-gray-600" />
                </button>
                <div className="px-5 py-2 bg-gray-50 border border-gray-200 rounded-xl text-[11px] font-black text-gray-900 shadow-inner">
                  PAGE {tablePage}
                </div>
                <button 
                  disabled={tablePage * 100 >= tableData.total}
                  onClick={() => setTablePage(p => p + 1)}
                  className="p-2.5 border border-gray-200 rounded-xl hover:bg-gray-50 disabled:opacity-30 transition-all shadow-sm flex items-center justify-center"
                >
                  <ChevronRight size={16} className="text-gray-600" />
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default App
