"""
XER Schedule Analyzer - Robust LLM-Powered Analysis
Comprehensive context and reliable code generation
"""

import re
import json
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict


class XERDataStore:
    """Stores all XER data with pre-computed statistics"""

    def __init__(self):
        self.baseline = None
        self.updates = []
        self.hours_per_day = 10
        self._cached_stats = None

    def load_baseline(self, data: Dict, name: str, data_date: str):
        """Load baseline data"""
        self.baseline = {
            'name': name,
            'data_date': data_date,
            'data': data,
            'df': self._create_dataframes(data)
        }
        self._cached_stats = None  # Clear cache

    def add_update(self, data: Dict, name: str, data_date: str):
        """Add an update file"""
        self.updates.append({
            'name': name,
            'data_date': data_date,
            'data': data,
            'df': self._create_dataframes(data)
        })
        self.updates.sort(key=lambda x: x['data_date'])
        self._cached_stats = None

    def remove_update(self, index: int):
        """Remove an update by index"""
        if 0 <= index < len(self.updates):
            self.updates.pop(index)
            self._cached_stats = None

    def _create_dataframes(self, data: Dict) -> Dict[str, pd.DataFrame]:
        """Convert XER tables to pandas DataFrames"""
        dfs = {}

        if data.get('tasks'):
            dfs['tasks'] = pd.DataFrame(data['tasks'])

        if data.get('wbs'):
            dfs['wbs'] = pd.DataFrame(data['wbs'])

        for table_name, records in data.get('tables', {}).items():
            if records:
                dfs[table_name.lower()] = pd.DataFrame(records)

        return dfs

    def get_latest(self) -> Dict:
        """Get latest data (most recent update or baseline)"""
        if self.updates:
            return self.updates[-1]
        return self.baseline

    def get_baseline(self) -> Dict:
        """Get baseline data"""
        return self.baseline

    def get_update_by_date(self, date_str: str) -> Optional[Dict]:
        """Find update by date (partial match)"""
        for update in self.updates:
            if date_str in update['data_date'] or date_str in update['name']:
                return update
        return None

    def get_update_by_month(self, month: str, year: str = None) -> Optional[Dict]:
        """Find update by month name or number"""
        month_map = {
            'jan': '01', 'january': '01', '01': '01', '1': '01',
            'feb': '02', 'february': '02', '02': '02', '2': '02',
            'mar': '03', 'march': '03', '03': '03', '3': '03',
            'apr': '04', 'april': '04', '04': '04', '4': '04',
            'may': '05', '05': '05', '5': '05',
            'jun': '06', 'june': '06', '06': '06', '6': '06',
            'jul': '07', 'july': '07', '07': '07', '7': '07',
            'aug': '08', 'august': '08', '08': '08', '8': '08',
            'sep': '09', 'september': '09', '09': '09', '9': '09',
            'oct': '10', 'october': '10', '10': '10',
            'nov': '11', 'november': '11', '11': '11',
            'dec': '12', 'december': '12', '12': '12'
        }

        month_num = month_map.get(month.lower(), month)

        for update in self.updates:
            data_date = update['data_date']
            if len(data_date) >= 7:
                file_month = data_date[5:7]
                file_year = data_date[:4]
                if file_month == month_num:
                    if year is None or file_year == year:
                        return update
        return None

    def compute_basic_stats(self) -> Dict:
        """Compute comprehensive statistics that are always available"""
        if self._cached_stats:
            return self._cached_stats

        source = self.get_latest()
        if not source or 'tasks' not in source.get('df', {}):
            return {'error': 'No data loaded'}

        tasks_df = source['df']['tasks'].copy()
        stats = {}

        # Basic counts
        stats['total_activities'] = len(tasks_df)
        stats['data_source'] = source['name']
        stats['data_date'] = source['data_date']

        # Task types
        if 'task_type' in tasks_df.columns:
            type_counts = tasks_df['task_type'].value_counts().to_dict()
            stats['task_types'] = type_counts
            stats['milestones'] = type_counts.get('TT_Mile', 0) + type_counts.get('TT_FinMile', 0)
            stats['loe_activities'] = type_counts.get('TT_LOE', 0)
            stats['regular_tasks'] = type_counts.get('TT_Task', 0)

        # Status breakdown
        if 'status_code' in tasks_df.columns:
            status_counts = tasks_df['status_code'].value_counts().to_dict()
            stats['status_breakdown'] = status_counts
            stats['completed'] = status_counts.get('TK_Complete', 0)
            stats['in_progress'] = status_counts.get('TK_Active', 0)
            stats['not_started'] = status_counts.get('TK_NotStart', 0)

        # Duration analysis
        if 'target_drtn_hr_cnt' in tasks_df.columns:
            tasks_df['duration_hrs'] = pd.to_numeric(tasks_df['target_drtn_hr_cnt'], errors='coerce').fillna(0)
            tasks_df['duration_days'] = tasks_df['duration_hrs'] / self.hours_per_day

            # Exclude LOE for duration stats
            work_tasks = tasks_df[~tasks_df.get('task_type', '').isin(['TT_LOE', 'TT_Mile', 'TT_FinMile'])]
            if len(work_tasks) > 0:
                stats['long_duration_count'] = len(work_tasks[work_tasks['duration_days'] > 30])
                stats['avg_duration_days'] = round(work_tasks['duration_days'].mean(), 1)
                stats['max_duration_days'] = round(work_tasks['duration_days'].max(), 1)

        # Float/Critical path
        if 'total_float_hr_cnt' in tasks_df.columns:
            tasks_df['float_hrs'] = pd.to_numeric(tasks_df['total_float_hr_cnt'], errors='coerce').fillna(0)
            tasks_df['float_days'] = tasks_df['float_hrs'] / self.hours_per_day

            work_tasks = tasks_df[~tasks_df.get('task_type', '').isin(['TT_LOE'])]
            if len(work_tasks) > 0:
                critical = work_tasks[work_tasks['float_hrs'] <= 0]
                near_critical = work_tasks[(work_tasks['float_hrs'] > 0) & (work_tasks['float_hrs'] <= 100)]
                negative_float = work_tasks[work_tasks['float_hrs'] < 0]

                stats['critical_count'] = len(critical)
                stats['critical_pct'] = round(len(critical) / len(work_tasks) * 100, 1)
                stats['near_critical_count'] = len(near_critical)
                stats['negative_float_count'] = len(negative_float)

        # Relationships
        if 'taskpred' in source['df']:
            pred_df = source['df']['taskpred']
            stats['total_relationships'] = len(pred_df)

            if 'pred_type' in pred_df.columns:
                rel_types = pred_df['pred_type'].value_counts().to_dict()
                stats['relationship_types'] = rel_types

            if 'lag_hr_cnt' in pred_df.columns:
                pred_df['lag'] = pd.to_numeric(pred_df['lag_hr_cnt'], errors='coerce').fillna(0)
                stats['relationships_with_lag'] = len(pred_df[pred_df['lag'] > 0])
                stats['negative_lags'] = len(pred_df[pred_df['lag'] < 0])

            # Open-ended and dangling
            all_task_ids = set(tasks_df['task_id'].tolist())
            has_successor = set(pred_df['pred_task_id'].tolist())
            has_predecessor = set(pred_df['task_id'].tolist())

            no_successor = all_task_ids - has_successor
            no_predecessor = all_task_ids - has_predecessor

            # Exclude LOE and milestones
            work_task_ids = set(tasks_df[~tasks_df['task_type'].isin(['TT_LOE', 'TT_Mile', 'TT_FinMile'])]['task_id'].tolist())
            stats['open_ended_count'] = len(no_successor & work_task_ids)
            stats['dangling_count'] = len(no_predecessor & work_task_ids)

        # Constraints
        if 'cstr_type' in tasks_df.columns:
            constrained = tasks_df[tasks_df['cstr_type'].notna() & (tasks_df['cstr_type'] != '')]
            stats['constrained_activities'] = len(constrained)
            if len(constrained) > 0:
                stats['constraint_types'] = constrained['cstr_type'].value_counts().to_dict()

        # Resources
        if 'taskrsrc' in source['df']:
            rsrc_df = source['df']['taskrsrc']
            stats['resource_assignments'] = len(rsrc_df)
            tasks_with_resources = rsrc_df['task_id'].nunique()
            stats['tasks_with_resources'] = tasks_with_resources
            stats['resource_loaded_pct'] = round(tasks_with_resources / len(tasks_df) * 100, 1)

        # Date range
        if 'target_start_date' in tasks_df.columns:
            starts = tasks_df['target_start_date'].dropna()
            if len(starts) > 0:
                stats['project_start'] = str(starts.min())[:10]

        if 'target_end_date' in tasks_df.columns:
            ends = tasks_df['target_end_date'].dropna()
            if len(ends) > 0:
                stats['project_finish'] = str(ends.max())[:10]

        # Calendars
        if 'calendar' in source['df']:
            cal_df = source['df']['calendar']
            stats['calendar_count'] = len(cal_df)
            if 'clndr_name' in cal_df.columns:
                stats['calendars'] = cal_df['clndr_name'].tolist()

        # Files info
        stats['baseline_name'] = self.baseline['name'] if self.baseline else None
        stats['baseline_date'] = self.baseline['data_date'] if self.baseline else None
        stats['update_count'] = len(self.updates)
        stats['updates'] = [{'name': u['name'], 'date': u['data_date']} for u in self.updates]

        self._cached_stats = stats
        return stats


    def get_tasks_df(self) -> Optional[pd.DataFrame]:
        """Get tasks dataframe with converted numeric fields"""
        source = self.get_latest()
        if not source or 'tasks' not in source.get('df', {}):
            return None
        
        df = source['df']['tasks'].copy()
        
        # Standard conversions
        if 'target_drtn_hr_cnt' in df.columns:
            df['duration_hrs'] = pd.to_numeric(df['target_drtn_hr_cnt'], errors='coerce').fillna(0)
            df['duration_days'] = df['duration_hrs'] / self.hours_per_day
        
        if 'total_float_hr_cnt' in df.columns:
            df['float_hrs'] = pd.to_numeric(df['total_float_hr_cnt'], errors='coerce').fillna(0)
            df['float_days'] = df['float_hrs'] / self.hours_per_day
            
        if 'phys_complete_pct' in df.columns:
            df['complete_pct'] = pd.to_numeric(df['phys_complete_pct'], errors='coerce').fillna(0)
            
        return df

    def get_delay_analysis(self) -> Dict:
        """Compare baseline vs latest for project delay"""
        if not self.baseline:
            return {"error": "No baseline loaded for comparison"}
        
        latest = self.get_latest()
        latest_df = latest['df'].get('tasks')
        baseline_df = self.baseline['df'].get('tasks')
        
        if latest_df is None or baseline_df is None:
            return {"error": "Task data missing for delay analysis"}

        # Extract project end dates
        baseline_finish = str(pd.to_datetime(baseline_df['target_end_date']).max())[:10]
        latest_finish = str(pd.to_datetime(latest_df['target_end_date']).max())[:10]
        
        b_date = pd.to_datetime(baseline_finish)
        l_date = pd.to_datetime(latest_finish)
        delay_days = (l_date - b_date).days
        
        return {
            "baseline_finish": baseline_finish,
            "latest_finish": latest_finish,
            "delay_days": delay_days,
            "status": "Delayed" if delay_days > 0 else "On Track" if delay_days == 0 else "Ahead"
        }

    def get_critical_path_details(self, limit: int = 20) -> List[Dict]:
        """Get details of critical activities"""
        df = self.get_tasks_df()
        if df is None: return []
        
        critical = df[df['float_hrs'] <= 0]
        # Sort by end date to show current critical activities
        critical = critical.sort_values('target_end_date')
        
        return critical.head(limit)[['task_code', 'task_name', 'target_start_date', 'target_end_date', 'float_days']].to_dict('records')

    def get_health_report(self) -> Dict:
        """Detailed schedule health analysis"""
        stats = self.compute_basic_stats()
        df = self.get_tasks_df()
        
        if df is None: return stats
        
        # Get specific problematic tasks
        open_ended = stats.get('open_ended_count', 0)
        negative_float = stats.get('negative_float_count', 0)
        long_dur = stats.get('long_duration_count', 0)
        
        health_data = {
            "summary": stats,
            "alerts": []
        }
        
        if negative_float > 0:
            health_data["alerts"].append(f"Found {negative_float} activities with negative float.")
        if open_ended > 0:
            health_data["alerts"].append(f"Found {open_ended} open-ended activities.")
            
        return health_data

    def get_comparison_report(self) -> Dict:
        """Compare baseline vs latest update in detail"""
        if not self.baseline or not self.updates:
            return {"note": "Comparison requires both baseline and at least one update."}
            
        b_df = self.baseline['df']['tasks']
        l_df = self.get_latest()['df']['tasks']
        
        # Activity count change
        diff_count = len(l_df) - len(b_df)
        
        return {
            "baseline_activities": len(b_df),
            "latest_activities": len(l_df),
            "net_change": diff_count,
            "new_activities_count": len(set(l_df['task_code']) - set(b_df['task_code'])),
            "removed_activities_count": len(set(b_df['task_code']) - set(l_df['task_code']))
        }

    def route_query(self, query: str) -> Dict:
        """Route user query to the appropriate analysis function"""
        q = query.lower()
        
        context = {"query": query, "basic_stats": self.compute_basic_stats()}
        
        if any(word in q for word in ["delay", "behind", "ahead", "finish", "end date"]):
            context["analysis_type"] = "Delay Analysis"
            context["data"] = self.get_delay_analysis()
            
        elif any(word in q for word in ["critical", "longest path"]):
            context["analysis_type"] = "Critical Path Analysis"
            context["data"] = self.get_critical_path_details()
            
        elif any(word in q for word in ["health", "quality", "open ended", "dangling", "float", "issue"]):
            context["analysis_type"] = "Schedule Health"
            context["data"] = self.get_health_report()
            
        elif any(word in q for word in ["compare", "change", "baseline", "different"]):
            context["analysis_type"] = "Comparison Analysis"
            context["data"] = self.get_comparison_report()
            
        else:
            context["analysis_type"] = "General Query"
            context["data"] = "Refer to basic stats"
            
        return context


class XERAnalyzer:
    """Main analyzer with comprehensive LLM support"""

    def __init__(self):
        self.data_store = XERDataStore()

    def load_baseline(self, data: Dict, name: str = None, data_date: str = None):
        if name is None:
            name = data.get('project', {}).get('project_name', 'Baseline')
        if data_date is None:
            data_date = data.get('project', {}).get('data_date', '')[:10]
        self.data_store.load_baseline(data, name, data_date)

    def add_update(self, data: Dict, name: str = None, data_date: str = None):
        if name is None:
            name = data.get('project', {}).get('project_name', 'Update')
        if data_date is None:
            data_date = data.get('project', {}).get('data_date', '')[:10]
        self.data_store.add_update(data, name, data_date)

    def remove_update(self, index: int):
        self.data_store.remove_update(index)

    def get_basic_stats(self) -> Dict:
        """Get pre-computed statistics"""
        return self.data_store.compute_basic_stats()

    def get_analysis_context(self, query: str) -> Dict:
        """Route query and return context for LLM explanation"""
        return self.data_store.route_query(query)

    def get_system_prompt(self) -> str:
        """Get the system prompt for local LLM"""
        return """You are an expert Primavera P6 Schedule Analyst. 
Your job is to EXPLAIN the structured data provided to you.

STRICT RULES:
1. Do NOT generate Python code.
2. Do NOT assume data that is not in the JSON provided.
3. If the JSON is empty or has an error, tell the user you lack the data.
4. Use professional construction project management terminology.
5. Be concise and use bullet points for readability.
6. Do NOT hallucinate specific dates or numbers; only use what is given in the 'Analysis Context'."""

    def get_explanation_prompt(self, query: str, context: Dict) -> str:
        """Generate final prompt for local LLM explanation"""
        return f"""
Analyze the following P6 Schedule data to answer the user query.

USER QUERY: {query}

ANALYSIS CONTEXT (JSON):
{json.dumps(context, indent=2, default=str)}

INSTRUCTIONS:
- Summarize the key findings from the JSON data.
- If it's a delay analysis, mention the specific dates and variance.
- If it's a health report, highlight the specific counts of issues.
- Provide professional recommendations based ON THIS DATA ONLY.
"""
