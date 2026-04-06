import pandas as pd
from typing import Dict, List, Optional, Any

class XERDataStore:
    """Stores all XER data with pre-computed statistics"""

    def __init__(self):
        self.baseline = None
        self.updates = []
        self.hours_per_day = 10
        self._cached_stats = None

    def load_baseline(self, data: Dict, name: str, data_date: str):
        self.baseline = {
            'name': name,
            'data_date': data_date,
            'data': data,
            'df': self._create_dataframes(data)
        }
        self._cached_stats = None

    def add_update(self, data: Dict, name: str, data_date: str):
        self.updates.append({
            'name': name,
            'data_date': data_date,
            'data': data,
            'df': self._create_dataframes(data)
        })
        self.updates.sort(key=lambda x: x['data_date'])
        self._cached_stats = None

    def remove_update(self, index: int):
        if 0 <= index < len(self.updates):
            self.updates.pop(index)
            self._cached_stats = None

    def _create_dataframes(self, data: Dict) -> Dict[str, pd.DataFrame]:
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
        if self.updates: return self.updates[-1]
        return self.baseline

    def get_baseline(self) -> Dict:
        return self.baseline

    def get_update_by_month(self, month: str) -> Optional[Dict]:
        month_map = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
            'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        month_num = month_map.get(month.lower()[:3], month)
        for update in self.updates:
            if update['data_date'][5:7] == month_num:
                return update
        return None

    def compute_basic_stats(self) -> Dict:
        if self._cached_stats: return self._cached_stats
        source = self.get_latest()
        if not source or 'tasks' not in source.get('df', {}): return {}

        tasks_df = source['df']['tasks'].copy()
        stats = {}
        stats['total_activities'] = len(tasks_df)
        stats['data_source'] = source['name']
        stats['data_date'] = source['data_date']

        if 'target_drtn_hr_cnt' in tasks_df.columns:
            tasks_df['duration_hrs'] = pd.to_numeric(tasks_df['target_drtn_hr_cnt'], errors='coerce').fillna(0)
            work_tasks = tasks_df[~tasks_df.get('task_type', '').isin(['TT_LOE', 'TT_Mile', 'TT_FinMile'])]
            stats['long_duration_count'] = len(work_tasks[work_tasks['duration_hrs'] / self.hours_per_day > 30]) if len(work_tasks) > 0 else 0

        if 'total_float_hr_cnt' in tasks_df.columns:
            tasks_df['float_hrs'] = pd.to_numeric(tasks_df['total_float_hr_cnt'], errors='coerce').fillna(0)
            work_tasks = tasks_df[~tasks_df.get('task_type', '').isin(['TT_LOE'])]
            if len(work_tasks) > 0:
                critical = work_tasks[work_tasks['float_hrs'] <= 0]
                stats['critical_count'] = len(critical)
                stats['critical_pct'] = round(len(critical) / len(work_tasks) * 100, 1)
                stats['negative_float_count'] = len(work_tasks[work_tasks['float_hrs'] < 0])

        if 'taskpred' in source['df']:
            pred_df = source['df']['taskpred']
            all_task_ids = set(tasks_df['task_id'].tolist())
            has_successor = set(pred_df['pred_task_id'].tolist())
            work_task_ids = set(tasks_df[~tasks_df['task_type'].isin(['TT_LOE', 'TT_Mile', 'TT_FinMile'])]['task_id'].tolist())
            stats['open_ended_count'] = len((all_task_ids - has_successor) & work_task_ids)

        if 'target_start_date' in tasks_df.columns:
            stats['project_start'] = str(tasks_df['target_start_date'].dropna().min())[:10]
        if 'target_end_date' in tasks_df.columns:
            stats['project_finish'] = str(tasks_df['target_end_date'].dropna().max())[:10]

        self._cached_stats = stats
        return stats
