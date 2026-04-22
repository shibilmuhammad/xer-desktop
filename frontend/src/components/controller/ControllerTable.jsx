import React from 'react';
import { Search, Circle, CheckCircle, Loader2, AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react';

const ControllerTable = ({
  tableData,
  viewerTable,
  viewerFilter,
  setViewerFilter,
  tableSearch,
  setTableSearch,
  tablePage,
  setTablePage,
  formatP6Date,
  getHeaderLabel
}) => {
  return (
    <>
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
                {tableData.records.length > 0 ? tableData.records.map((row, i) => {
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
                                <span title={`Delay: ${analysis.delay_days || 0} days`} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-tight shadow-sm cursor-help ${statusConfig.color}`}>
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
                                {key === 'act_end_date' && analysis.current_end_date ? formatP6Date(analysis.current_end_date) : formatP6Date(row[key])}
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
    </>
  );
};

export default ControllerTable;
