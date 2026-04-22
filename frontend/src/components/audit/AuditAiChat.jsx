import React from 'react';
import { Send, Globe, Cpu, Activity, CheckCircle, Zap, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import logo from '../../assets/logo.png';
import OptimizedChatInput from '../OptimizedChatInput';

const AuditAiChat = ({ 
  messages, 
  isTyping, 
  handleAsk, 
  chatEndRef,
  isUpdatingAI,
  handleUpdateAI,
  aiConfig,
  stats
}) => {
  return (
    <div className="bg-white rounded-[2.5rem] border border-gray-200 shadow-sm p-10 relative flex flex-col min-h-[500px]">
      <div className="flex items-center gap-3 mb-10 border-b border-gray-100 pb-5">
         <div className="w-10 h-10 rounded-2xl bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-200">
            <Send size={18} className="text-white" />
         </div>
         <div>
           <h3 className="text-xl font-black text-gray-900 tracking-tight">AI Audit Assistant</h3>
           <p className="text-xs text-gray-400 font-medium tracking-tight">Contextual P6 forensic analysis</p>
         </div>

         {/* Compact Model Switcher in Header */}
         <div className="ml-auto flex items-center gap-1.5 p-1 bg-gray-50 border border-gray-200 rounded-2xl">
           <button 
             disabled={isUpdatingAI}
             onClick={() => handleUpdateAI('openai')}
             className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-[10px] font-black transition-all ${
               aiConfig.provider === 'openai' 
               ? 'bg-red-600 text-white shadow-sm' 
               : 'text-gray-400 hover:text-gray-600'
             } ${!aiConfig.has_openai_key && 'opacity-30 cursor-not-allowed'}`}
             title={!aiConfig.has_openai_key ? "OpenAI API Key missing" : "GPT-4o Cloud"}
           >
             <Globe size={12} /> Cloud
             {aiConfig.provider === 'openai' && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>}
           </button>
           <button 
             disabled={isUpdatingAI}
             onClick={() => handleUpdateAI('local')}
             className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-[10px] font-black transition-all ${
               aiConfig.provider === 'local' 
               ? 'bg-blue-600 text-white shadow-sm' 
               : 'text-gray-400 hover:text-gray-600'
             }`}
           >
             <Cpu size={12} /> Local
             {aiConfig.provider === 'local' && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>}
           </button>
         </div>

         <span className="text-[10px] font-black uppercase tracking-widest bg-gray-100 text-gray-500 px-3 py-1.5 rounded-xl border border-gray-200/50">
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

                        {(m.content.recommendations || m.content.drivers) && (m.content.recommendations || m.content.drivers).length > 0 && (
                          <div className="recommendations mt-1">
                            <h5 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                              <Zap size={12} className="text-amber-500"/> Strategic Recommendations
                            </h5>
                            <div className="space-y-2">
                              {(m.content.recommendations || m.content.drivers).map((rec, idx) => (
                                <div key={idx} className="flex gap-2.5 px-3 py-2 bg-amber-50/50 text-amber-800 border border-amber-100/50 rounded-xl text-xs font-semibold shadow-sm leading-relaxed">
                                  <div className="mt-1 shrink-0"><Zap size={10} className="text-amber-500" /></div>
                                  {rec}
                                </div>
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
         <OptimizedChatInput 
           placeholder="Ask about schedule delays, critical path, or risks..."
           isTyping={isTyping}
           onSubmit={handleAsk}
           className="w-full pl-6 pr-14 py-4.5 bg-white/95 backdrop-blur-md border border-gray-200 shadow-xl rounded-2xl focus:ring-4 focus:ring-blue-500/10 focus:border-blue-400 transition-all outline-none text-sm placeholder:text-gray-400 font-medium"
           buttonClassName="absolute right-2.5 top-1/2 -translate-y-1/2 p-2.5 bg-blue-600 hover:bg-blue-700 rounded-xl transition-all shadow-lg shadow-blue-200 text-white"
         />
       </div>
    </div>
  );
};

export default AuditAiChat;
