import React, { useState, useMemo } from 'react';
import { X, Search, AlertTriangle, CheckCircle, Clock } from 'lucide-react';

const STATUS_COLORS = {
  COMPLETED:    'bg-green-100 text-green-700',
  IN_PROGRESS:  'bg-blue-100 text-blue-700',
  NOT_STARTED:  'bg-gray-100 text-gray-600',
  DELAYED_CRITICAL: 'bg-red-100 text-red-700',
  DELAYED_SAFE: 'bg-orange-100 text-orange-700',
  DELAYED_NEGATIVE: 'bg-red-200 text-red-800',
  DEFAULT:      'bg-gray-100 text-gray-500',
};

const PAGE_SIZE = 30;

export default function ViewAllModal({ isOpen, onClose, title, data = [], totalCount, displayedCount }) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    if (!search.trim()) return data;
    const q = search.toLowerCase();
    return data.filter(d =>
      (d.name || d.task_name || '').toLowerCase().includes(q) ||
      (d.code || d.task_code || '').toLowerCase().includes(q)
    );
  }, [data, search]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-8 py-5 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-black text-gray-900">{title}</h2>
            <p className="text-xs text-gray-400 mt-0.5 font-medium">
              {search ? `${filtered.length} filtered` : `${totalCount} total`}
              {totalCount > displayedCount && !search &&
                <span className="ml-2 text-amber-500 font-bold">
                  · Showing {displayedCount} of {totalCount} — search to refine
                </span>}
            </p>
          </div>
          <button onClick={onClose}
            className="p-2 rounded-xl hover:bg-gray-100 text-gray-400 hover:text-gray-700 transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Search */}
        <div className="px-8 py-4 border-b border-gray-50">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
              placeholder="Filter by name or code..."
              className="w-full pl-9 pr-4 py-2.5 text-sm bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 transition-all font-medium"
            />
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-y-auto">
          {paginated.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-400">
              <AlertTriangle size={28} className="mb-3 opacity-40" />
              <p className="text-sm font-medium">No matching activities</p>
            </div>
          ) : (
            <table className="w-full text-left">
              <thead className="sticky top-0 bg-gray-50 border-b border-gray-100">
                <tr>
                  {['Code', 'Activity Name', 'Status', 'Delay', 'Float', 'Finish'].map(h => (
                    <th key={h} className="px-6 py-3 text-[10px] font-black text-gray-400 uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {paginated.map((row, i) => {
                  const cat = row.category || row.status || 'DEFAULT';
                  const colorClass = STATUS_COLORS[cat] || STATUS_COLORS.DEFAULT;
                  const delay = row.delay_days || 0;
                  const float_ = row.float_days ?? '-';
                  return (
                    <tr key={row.id || i} className="hover:bg-blue-50/30 transition-colors">
                      <td className="px-6 py-3 text-xs font-mono text-gray-500">{row.code || '-'}</td>
                      <td className="px-6 py-3 text-sm font-semibold text-gray-800 max-w-[240px] truncate" title={row.name}>{row.name || '-'}</td>
                      <td className="px-6 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wide ${colorClass}`}>
                          {row.status || '-'}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-sm font-bold text-red-600">{delay > 0 ? `${delay}d` : '-'}</td>
                      <td className={`px-6 py-3 text-sm font-bold ${float_ < 0 ? 'text-red-500' : 'text-gray-600'}`}>{float_ !== '-' ? `${float_}d` : '-'}</td>
                      <td className="px-6 py-3 text-xs text-gray-500 font-mono">{row.finish || '-'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-8 py-4 border-t border-gray-100 bg-gray-50/50">
            <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
              className="px-4 py-1.5 text-xs font-bold rounded-lg bg-white border border-gray-200 hover:bg-gray-50 disabled:opacity-30 transition-all">
              Previous
            </button>
            <span className="text-xs text-gray-500 font-medium">Page {page} of {totalPages}</span>
            <button disabled={page === totalPages} onClick={() => setPage(p => p + 1)}
              className="px-4 py-1.5 text-xs font-bold rounded-lg bg-white border border-gray-200 hover:bg-gray-50 disabled:opacity-30 transition-all">
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
