import React from 'react';
import { ListTree } from 'lucide-react';

const AssessmentTable = ({ stats }) => {
  if (!stats?.delay_matrix?.assessment) return null;

  return (
    <div className="mb-10 bg-gray-900 rounded-[2.5rem] border border-white/10 shadow-2xl overflow-hidden">
      <div className="p-8 border-b border-white/5 flex items-center justify-between bg-gray-900/50 backdrop-blur-md sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <ListTree size={20} className="text-white" />
          </div>
          <div>
            <h3 className="text-xl font-black text-white tracking-tight">Assessment Parameters & Scoring</h3>
            <p className="text-[10px] text-gray-400 font-bold uppercase tracking-widest">Forensic quality methodology (DCMA-14 Standard)</p>
          </div>
        </div>
        <div className="px-5 py-2.5 bg-gray-800 rounded-2xl border border-white/5">
          <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest mr-3">Status:</span>
          <span className={`text-xs font-black uppercase tracking-tighter ${stats.delay_matrix.healthMetrics?.projectHealthScore > 80 ? 'text-green-400' : 'text-orange-400'}`}>
            {stats.delay_matrix.healthMetrics?.healthStatus} Quality
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-white/5">
              <th className="px-8 py-5 text-[10px] font-black text-gray-500 uppercase tracking-widest border-b border-white/5">#</th>
              <th className="px-8 py-5 text-[10px] font-black text-gray-500 uppercase tracking-widest border-b border-white/5">Parameters</th>
              <th className="px-8 py-5 text-[10px] font-black text-gray-500 uppercase tracking-widest border-b border-white/5">What is Measured</th>
              <th className="px-8 py-5 text-[10px] font-black text-gray-500 uppercase tracking-widest border-b border-white/5 text-center">Accepted Threshold</th>
              <th className="px-8 py-5 text-[10px] font-black text-gray-500 uppercase tracking-widest border-b border-white/5">Score</th>
              <th className="px-8 py-5 text-[10px] font-black text-gray-500 uppercase tracking-widest border-b border-white/5 text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {stats.delay_matrix.assessment.filter(p => p.id !== 14).map((point) => (
              <tr key={point.id} className="hover:bg-white/[0.02] transition-colors group border-b border-white/5 last:border-0">
                <td className="px-8 py-5 text-sm font-black text-blue-500/70">{point.id}</td>
                <td className="px-8 py-5">
                  <div className="flex flex-col">
                    <span className="text-sm font-bold text-gray-100 group-hover:text-white transition-colors">{point.name}</span>
                    {point.id === 1 && point.details && (
                      <div className="mt-2 flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[8px] font-black text-blue-400 uppercase tracking-widest">Starts:</span>
                          <span className="text-[10px] text-gray-500 truncate max-w-[200px] italic">{point.details.starts?.join(', ') || 'None'}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[8px] font-black text-green-400 uppercase tracking-widest">Finishes:</span>
                          <span className="text-[10px] text-gray-500 truncate max-w-[200px] italic">{point.details.finishes?.join(', ') || 'None'}</span>
                        </div>
                      </div>
                    )}
                  </div>
                </td>
                <td className="px-8 py-5">
                   <div className="flex flex-col gap-1 max-w-xs">
                     <span className="text-[11px] text-gray-400 font-medium leading-relaxed">{point.measure}</span>
                     {point.explanation && <span className="text-[9px] text-blue-400/70 font-bold italic">{point.explanation}</span>}
                   </div>
                </td>
                <td className="px-8 py-5 text-xs font-black text-gray-300 font-mono tracking-tighter text-center">{point.threshold}</td>
                <td className="px-8 py-5">
                  <span className="text-[12px] font-black text-white bg-white/5 px-3 py-1 rounded-lg border border-white/10">
                    {
                      point.id === 13 ? point.val.toFixed(3) : 
                      (point.id === 1 || point.id === 12 || point.id === 14 || point.id === 9 || point.id === 10) ? (point.status_text || (point.status ? 'Pass' : 'Fail')) :
                      typeof point.val === 'number' ? point.val.toFixed(1) + '%' : point.val
                    }
                  </span>
                </td>
                <td className="px-8 py-5">
                  <div className="flex justify-center">
                    <span className={`px-4 py-1 rounded-full text-[10px] font-black uppercase tracking-widest shadow-sm border ${
                      (point.status_text === 'PASS' || point.status === true) ? 'bg-green-500/20 text-green-400 border-green-500/30' : 
                      (point.status_text === 'WARNING') ? 'bg-orange-500/20 text-orange-400 border-orange-500/30' :
                      'bg-red-500/20 text-red-400 border-red-500/30'
                    }`}>
                       {point.status_text || (point.status ? 'Pass' : 'Fail')}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AssessmentTable;
