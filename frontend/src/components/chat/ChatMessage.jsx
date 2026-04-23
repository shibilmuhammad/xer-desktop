import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CheckCircle, XCircle, AlertTriangle, Zap, Activity, ChevronRight, ArrowRight } from 'lucide-react';
import ViewAllModal from './ViewAllModal';

// ── Helpers ───────────────────────────────────────────────────────────────────
const safeStr = (v) => {
  if (v === null || v === undefined) return '';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
};

const StatusBadge = ({ status }) => {
  const s = (status || '').toUpperCase();
  const cfg = {
    PASS:    { cls: 'bg-green-100 text-green-700 border-green-200',    icon: <CheckCircle size={11} /> },
    WARNING: { cls: 'bg-amber-100 text-amber-700 border-amber-200',    icon: <AlertTriangle size={11} /> },
    FAIL:    { cls: 'bg-red-100 text-red-700 border-red-200',          icon: <XCircle size={11} /> },
    DEFAULT: { cls: 'bg-gray-100 text-gray-600 border-gray-200',       icon: null },
  };
  const { cls, icon } = cfg[s] || cfg.DEFAULT;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest border ${cls}`}>
      {icon}{s || 'UNKNOWN'}
    </span>
  );
};

// ── Template Renderers ────────────────────────────────────────────────────────

function ListTemplate({ content }) {
  const [modalOpen, setModalOpen] = useState(false);
  const metrics = content.metrics || {};
  const insights = content.insights || [];
  const recs = content.recommendations || [];

  return (
    <div className="flex flex-col gap-4">
      {/* Truncation Banner */}
      {content.is_truncated && (
        <div className="flex items-center justify-between px-4 py-2.5 bg-blue-50 border border-blue-100 rounded-2xl">
          <div className="flex items-center gap-2">
            <Activity size={12} className="text-blue-500 animate-pulse" />
            <span className="text-xs font-black text-blue-700 uppercase tracking-widest">
              Showing {content.displayed_count} of {content.total_count} activities
            </span>
          </div>
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 bg-blue-600 text-white text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-blue-700 transition-colors shadow-sm">
            View All <ArrowRight size={10} />
          </button>
        </div>
      )}

      {/* Summary (Markdown with tables) */}
      <div className="text-sm text-gray-800 font-medium leading-relaxed markdown-table-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content.summary || ''}</ReactMarkdown>
      </div>

      {/* Metrics Grid */}
      {Object.keys(metrics).length > 0 && (
        <div className="grid grid-cols-2 gap-2.5">
          {Object.entries(metrics).map(([k, v]) => (
            <div key={k} className="bg-blue-50 border border-blue-100 p-3 rounded-xl">
              <div className="text-[9px] text-blue-500 font-black uppercase tracking-widest mb-1">
                {k.replace(/([A-Z])/g, ' $1').trim()}
              </div>
              <div className="text-lg font-black text-blue-900">{safeStr(v)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Suggestions */}
      {content.suggestions && content.suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-1">
          {content.suggestions.map((s, i) => (
            <span key={i} className="px-3 py-1 bg-gray-100 border border-gray-200 text-xs font-semibold text-gray-700 rounded-full cursor-pointer hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700 transition-colors">
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Insights */}
      {insights.length > 0 && (
        <div className="bg-gray-50 rounded-xl border border-gray-100 p-4">
          <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
            <Activity size={11} /> Key Insights
          </p>
          <ul className="space-y-2.5">
            {insights.map((ins, i) => (
              <li key={i} className="flex gap-2.5 text-sm text-gray-700">
                <CheckCircle size={14} className="text-green-500 mt-0.5 flex-shrink-0" />
                <span className="leading-snug">{safeStr(ins)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommendations */}
      {recs.length > 0 && (
        <div className="space-y-2">
          <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
            <Zap size={11} className="text-amber-500" /> Recommendations
          </p>
          {recs.map((r, i) => (
            <div key={i} className="flex gap-2.5 px-3 py-2.5 bg-amber-50 border border-amber-100 rounded-xl text-xs font-semibold text-amber-800 leading-relaxed">
              <Zap size={10} className="text-amber-500 mt-0.5 flex-shrink-0" />
              {safeStr(r)}
            </div>
          ))}
        </div>
      )}

      <ViewAllModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={content.summary?.split('\n')[0]?.replace(/[#*]/g, '').trim() || 'Activities'}
        data={content.data || []}
        totalCount={content.total_count || 0}
        displayedCount={content.displayed_count || 0}
      />
    </div>
  );
}

function IntegrityTemplate({ content }) {
  const stats = (content.data || [])[0] || {};
  const summary_stats = content.stats || {};
  const logicStatus = summary_stats.logic_status || stats.logic_status || 'UNKNOWN';
  const openStarts = summary_stats.open_start_names || [];
  const openFinishes = summary_stats.open_finish_names || [];
  const insights = content.insights || [];
  const recs = content.recommendations || [];

  return (
    <div className="flex flex-col gap-4">
      {/* Big Status Badge */}
      <div className="flex items-center gap-3 p-4 bg-gray-50 rounded-2xl border border-gray-100">
        <StatusBadge status={logicStatus} />
        <div className="text-sm font-medium text-gray-700 leading-snug">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content.summary || ''}</ReactMarkdown>
        </div>
      </div>

      {/* Open Ends */}
      {(openStarts.length > 0 || openFinishes.length > 0) && (
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-blue-50 border border-blue-100 rounded-xl">
            <p className="text-[9px] font-black text-blue-500 uppercase tracking-widest mb-2">
              Open Starts ({openStarts.length})
            </p>
            {openStarts.map((n, i) => (
              <p key={i} className="text-xs text-gray-700 font-medium truncate">{n}</p>
            ))}
            {openStarts.length === 0 && <p className="text-xs text-gray-400">None</p>}
          </div>
          <div className="p-3 bg-green-50 border border-green-100 rounded-xl">
            <p className="text-[9px] font-black text-green-600 uppercase tracking-widest mb-2">
              Open Finishes ({openFinishes.length})
            </p>
            {openFinishes.map((n, i) => (
              <p key={i} className="text-xs text-gray-700 font-medium truncate">{n}</p>
            ))}
            {openFinishes.length === 0 && <p className="text-xs text-gray-400">None</p>}
          </div>
        </div>
      )}

      {/* Other Checks */}
      {content.metrics && Object.keys(content.metrics).length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {Object.entries(content.metrics).map(([k, v]) => (
            <div key={k} className="bg-white border border-gray-100 p-2.5 rounded-xl text-center shadow-sm">
              <div className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-1">{k.replace(/([A-Z])/g, ' $1').trim()}</div>
              <div className="text-sm font-black text-gray-800">{safeStr(v)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Insights */}
      {insights.length > 0 && (
        <ul className="space-y-2">
          {insights.map((ins, i) => (
            <li key={i} className="flex gap-2 text-sm text-gray-700">
              <ChevronRight size={14} className="text-blue-400 mt-0.5 flex-shrink-0" />
              <span>{safeStr(ins)}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Recommendations */}
      {recs.length > 0 && (
        <div className="space-y-2">
          {recs.map((r, i) => (
            <div key={i} className="flex gap-2 px-3 py-2.5 bg-amber-50 border border-amber-100 rounded-xl text-xs font-semibold text-amber-800 leading-relaxed">
              <Zap size={10} className="text-amber-500 mt-0.5 flex-shrink-0" />{safeStr(r)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ClarifyTemplate({ content }) {
  const recs = content.recommendations || [];
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-gray-700 font-medium leading-relaxed">{content.summary}</p>
      {(content.insights || []).map((ins, i) => (
        <p key={i} className="text-sm text-gray-600 italic">{safeStr(ins)}</p>
      ))}
      {recs.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-1">
          {recs.map((r, i) => (
            <span key={i} className="px-3 py-1.5 bg-blue-50 border border-blue-100 text-xs font-bold text-blue-700 rounded-xl cursor-pointer hover:bg-blue-100 transition-colors">
              {safeStr(r)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function DefaultTemplate({ content }) {
  return <ListTemplate content={content} />;
}

// ── Main Export ───────────────────────────────────────────────────────────────
export default function ChatMessage({ content }) {
  if (typeof content === 'string') {
    return (
      <div className="text-sm text-gray-800 leading-relaxed markdown-table-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    );
  }
  if (!content || typeof content !== 'object') return null;

  const tmpl = content.template_type || 'list';

  if (tmpl === 'integrity') return <IntegrityTemplate content={content} />;
  if (tmpl === 'clarify')   return <ClarifyTemplate content={content} />;
  // list, activity, analysis, health all use the rich list template
  return <ListTemplate content={content} />;
}
