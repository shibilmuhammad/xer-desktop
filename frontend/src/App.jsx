import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { Upload, X, Send, BarChart2, Activity, Calendar, Clock, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

function App() {
  const [baselineLoaded, setBaselineLoaded] = useState(false)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [updates, setUpdates] = useState([])
  const [isTyping, setIsTyping] = useState(false)
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
        if (type === 'baseline') {
          setBaselineLoaded(true)
        } else {
          setUpdates([...updates, { name: file.name, date: res.data.stats.data_date }])
        }
      }
    } catch (err) {
      console.error(err)
      alert('Upload failed: ' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }

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

  if (!baselineLoaded) {
    return (
      <div className="flex flex-col items-center justify-center h-screen text-center p-4">
        <h1 className="text-4xl font-bold mb-2">XER Schedule Assistant</h1>
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

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <div className="w-[300px] bg-[#f8f9fa] border-r border-gray-200 p-6 flex flex-col overflow-y-auto">
        <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
          <BarChart2 size={20} className="text-blue-600" />
          Project Files
        </h3>
        
        <p className="text-sm font-semibold text-gray-700 mb-2">Baseline:</p>
        <div className="bg-blue-50 p-4 rounded-lg mb-6 border border-blue-100">
          <div className="font-semibold text-sm text-blue-900 truncate">{stats?.data_source}</div>
          <div className="text-xs text-blue-700 mt-1 flex items-center gap-1">
            <Calendar size={12} />
            Data Date: {stats?.data_date || 'N/A'}
          </div>
        </div>

        <hr className="mb-6 border-gray-200" />

        <p className="text-sm font-semibold text-gray-700 mb-2">Update Files:</p>
        <div className="flex-1 space-y-3">
          {updates.length === 0 ? (
            <p className="text-xs text-gray-400 italic">No updates loaded</p>
          ) : (
            updates.map((u, i) => (
              <div key={i} className="bg-green-50 p-3 rounded-lg border border-green-100 flex justify-between items-center group">
                <div className="min-w-0">
                  <div className="font-semibold text-xs text-green-900 truncate">{u.name}</div>
                  <div className="text-[10px] text-green-700 mt-1">Data Date: {u.date}</div>
                </div>
                <button 
                  onClick={() => setUpdates(updates.filter((_, idx) => idx !== i))}
                  className="p-1 hover:bg-green-200 rounded-full text-green-700 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X size={14} />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="mt-6">
          <p className="text-sm font-semibold text-gray-700 mb-3">Add Update:</p>
          <label className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-gray-200 rounded-xl cursor-pointer hover:bg-gray-50 transition-all border-green-100 bg-green-50/30">
             <Upload size={24} className="text-green-600 mb-2" />
             <p className="text-[11px] font-medium text-green-800">Drag & drop update file</p>
             <p className="text-[10px] text-green-600/60 mb-3">Limit 200MB • XER</p>
             <span className="bg-white border border-green-200 px-4 py-1.5 rounded-md text-[11px] font-semibold text-green-700 shadow-sm">
               Browse
             </span>
             <input type="file" hidden accept=".xer" onChange={(e) => handleUpload(e, 'update')} disabled={loading} />
          </label>
        </div>

        <hr className="my-6 border-gray-200" />

        <h3 className="text-sm font-bold text-gray-700 mb-4 uppercase tracking-wider">Schedule Health</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 flex items-center gap-2"><Activity size={14} /> Activities</span>
            <span className="font-bold">{stats?.total_activities || 0}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 flex items-center gap-2"><Clock size={14} /> Critical</span>
            <span className="font-bold text-red-600">{stats?.critical_pct || 0}%</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 flex items-center gap-2"><Activity size={14} /> Neg Float</span>
            <span className="font-bold text-red-700">{stats?.negative_float_count || 0}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 flex items-center gap-2"><X size={14} /> Open-Ended</span>
            <span className="font-bold text-orange-600">{stats?.open_ended_count || 0}</span>
          </div>
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

        <div className="flex-1 overflow-y-auto p-8">
          {messages.length === 0 ? (
            <div className="max-w-3xl mx-auto py-12">
              <h1 className="text-4xl font-extrabold text-gray-900 mb-4 tracking-tight">Welcome to XER Schedule Assistant</h1>
              <p className="text-lg text-gray-600 mb-8 leading-relaxed">I'm your Primavera P6 schedule analyst. I can help you with:</p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
                <div className="p-5 rounded-2xl border border-gray-100 bg-white shadow-sm hover:shadow-md transition-shadow">
                  <h4 className="font-bold text-gray-900 mb-3 flex items-center gap-2">
                    <Activity size={18} className="text-blue-500" />
                    Quality Analysis
                  </h4>
                  <ul className="text-sm text-gray-600 space-y-2">
                    <li>• Long duration activities</li>
                    <li>• Open-ended & dangling tasks</li>
                    <li>• Critical path identification</li>
                  </ul>
                </div>
                <div className="p-5 rounded-2xl border border-gray-100 bg-white shadow-sm hover:shadow-md transition-shadow">
                  <h4 className="font-bold text-gray-900 mb-3 flex items-center gap-2">
                    <BarChart2 size={18} className="text-green-500" />
                    Comparisons
                  </h4>
                  <ul className="text-sm text-gray-600 space-y-2">
                    <li>• Baseline vs update analysis</li>
                    <li>• Monthly progress tracking</li>
                    <li>• Delay & variance reporting</li>
                  </ul>
                </div>
              </div>
              
              <div className="bg-gray-900 text-white rounded-3xl p-8 shadow-2xl relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8 opacity-10">
                  <Activity size={120} />
                </div>
                <h4 className="text-xl font-bold mb-6 flex items-center gap-2">
                  Current Schedule Health:
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-6 gap-x-12 relative z-10">
                   <div className="flex flex-col">
                     <span className="text-gray-400 text-xs uppercase font-bold tracking-wider mb-1">Critical Activities</span>
                     <span className="text-2xl font-black">{stats?.critical_count || 0} <span className="text-sm font-normal text-gray-400">({stats?.critical_pct || 0}%)</span></span>
                   </div>
                   <div className="flex flex-col">
                     <span className="text-gray-400 text-xs uppercase font-bold tracking-wider mb-1">Negative Float</span>
                     <span className="text-2xl font-black text-red-400">{stats?.negative_float_count || 0}</span>
                   </div>
                   <div className="flex flex-col">
                     <span className="text-gray-400 text-xs uppercase font-bold tracking-wider mb-1">&gt; 30d Duration</span>
                     <span className="text-2xl font-black">{stats?.long_duration_count || 0}</span>
                   </div>
                   <div className="flex flex-col">
                     <span className="text-gray-400 text-xs uppercase font-bold tracking-wider mb-1">Open-Ended</span>
                     <span className="text-2xl font-black text-orange-400">{stats?.open_ended_count || 0}</span>
                   </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6 pb-4">
              {Array.isArray(messages) && messages.map((m, i) => {
                if (!m) return null;
                return (
                  <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {m.role === 'assistant' && (
                      <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0 mt-1">
                        <Activity size={16} className="text-blue-600" />
                      </div>
                    )}
                    <div className={`
                      max-w-[85%] px-5 py-3.5 rounded-2xl text-sm leading-relaxed shadow-sm
                      ${m.role === 'user' 
                        ? 'bg-blue-600 text-white rounded-tr-none' 
                        : 'bg-white border border-gray-100 text-gray-800 rounded-tl-none'}
                    `}>
                      {m.role === 'assistant' ? (
                        <div className="markdown-content">
                          <ReactMarkdown>
                            {typeof m.content === 'string' ? m.content : ''}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        String(m.content || '')
                      )}
                    </div>
                  </div>
                );
              })}
              
              {isTyping && (
                <div className="flex gap-3 justify-start">
                  <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center flex-shrink-0 mt-1">
                    <Activity size={16} className="text-blue-400" />
                  </div>
                  <div className="bg-white border border-gray-100 text-gray-500 px-5 py-3.5 rounded-2xl rounded-tl-none text-sm flex items-center gap-3 shadow-sm italic">
                    <div className="flex gap-1">
                      <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-duration:0.8s]"></div>
                      <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-duration:0.8s] [animation-delay:0.2s]"></div>
                      <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-duration:0.8s] [animation-delay:0.4s]"></div>
                    </div>
                    Analyzing schedule...
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        <div className="p-6 bg-white">
          <div className="max-w-3xl mx-auto relative group">
            <input 
              className="w-full pl-6 pr-14 py-4 bg-gray-100 border-none rounded-2xl focus:ring-2 focus:ring-blue-500/20 focus:bg-white transition-all outline-none text-sm placeholder:text-gray-400 shadow-inner"
              placeholder="Ask about your schedule..." 
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
            />
            <button 
              onClick={handleAsk}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-2 hover:bg-blue-50 rounded-xl transition-colors group-focus-within:bg-blue-600"
            >
              <Send size={20} className="text-blue-500 group-focus-within:text-white transition-colors" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
