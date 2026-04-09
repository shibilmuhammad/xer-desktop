import pandas as pd
from typing import Dict, List, Optional, Any

class XERDataStore:
    """Stores all XER data with pre-computed statistics"""

    def __init__(self):
        self.versions = {} # { id: {type, name, data_date, data, df} }
        self.active_version_id = None
        self.hours_per_day = 10
        self._cached_stats = None

    def add_version(self, data: Dict, name: str, data_date: str, type: str = "update") -> str:
        version_id = f"{type}_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
        if type == "baseline":
            version_id = "baseline"
            
        self.versions[version_id] = {
            'id': version_id,
            'type': type,
            'name': name,
            'data_date': data_date,
            'data': data,
            'df': self._create_dataframes(data)
        }
        self.active_version_id = version_id
        self._cached_stats = None
        return version_id

    def remove_version(self, version_id: str):
        if version_id in self.versions:
            del self.versions[version_id]
            if self.active_version_id == version_id:
                self.active_version_id = "baseline" if "baseline" in self.versions else None
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

    def get_version(self, version_id: Optional[str] = None) -> Optional[Dict]:
        vid = version_id or self.active_version_id
        return self.versions.get(vid)

    def get_latest(self) -> Optional[Dict]:
        if not self.versions: return None
        # Sort updates by date and get latest
        updates = [v for v in self.versions.values() if v['type'] == 'update']
        if updates:
            updates.sort(key=lambda x: x['data_date'])
            return updates[-1]
        return self.versions.get('baseline')

    def get_baseline(self) -> Optional[Dict]:
        return self.versions.get('baseline')

    def get_update_by_month(self, month: str) -> Optional[Dict]:
        month_map = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
            'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        month_num = month_map.get(month.lower()[:3], month)
        updates = [v for v in self.versions.values() if v['type'] == 'update']
        for update in updates:
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

    def get_deterministic_analysis(self, version_id: Optional[str] = None) -> Dict:
        """
        Pure deterministic schedule analysis based on P6 principles.
        Calculates status, delays, and critical path metrics.
        """
        source = self.get_version(version_id)
        if not source or 'df' not in source or 'tasks' not in source['df']:
            return {}

        df = source['df']['tasks'].copy()
        
        # 1. Normalize & Pre-process
        # Ensure numeric float and durations
        df['float_hrs'] = pd.to_numeric(df.get('total_float_hr_cnt', 0), errors='coerce').fillna(0)
        df['float_days'] = df['float_hrs'] / self.hours_per_day
        
        # Parse dates
        # Note: XER stores dates as strings 'YYYY-MM-DD HH:MM'
        date_cols = ['target_start_date', 'target_end_date', 'act_start_date', 'act_end_date']
        for col in date_cols:
            if col in df.columns:
                df[f'_dt_{col}'] = pd.to_datetime(df[col], errors='coerce')

        # 2. Task Status Calculation (Pure logic)
        def calc_status(row):
            is_completed = pd.notnull(row.get('_dt_act_end_date'))
            is_in_progress = pd.notnull(row.get('_dt_act_start_date')) and not is_completed
            is_delayed = row.get('float_hrs', 0) < 0 and not is_completed
            
            if is_completed: return "COMPLETED"
            if is_delayed: return "DELAYED"
            if is_in_progress: return "IN_PROGRESS"
            return "NOT_STARTED"

        df['status_enum'] = df.apply(calc_status, axis=1)
        df['is_critical_p6'] = df['float_hrs'] <= 0

        # 3. Unified Current End Date Logic (Pure logic)
        def get_current_end_date(row):
            act = row.get('_dt_act_end_date')
            plan = row.get('_dt_target_end_date')
            return act if pd.notnull(act) else plan

        df['_dt_current_end_date'] = df.apply(get_current_end_date, axis=1)
        # Store if it's predicted (using planned finish)
        df['is_predicted_date'] = pd.isnull(df['_dt_act_end_date']) & pd.notnull(df['_dt_target_end_date'])

        # Filter out tasks without any end date availability for delay calculations
        calc_df = df[df['_dt_current_end_date'].notnull()].copy()

        # 4. Task Delay Calculation
        def calc_delay(row):
            # If delayed by negative float (active/planned)
            if row['float_hrs'] < 0 and row['status_enum'] != "COMPLETED":
                return abs(row['float_days'])
            
            baseline_finish = row.get('_dt_target_end_date')
            current_finish = row.get('_dt_current_end_date')
            
            if pd.isnull(baseline_finish) or pd.isnull(current_finish):
                return 0
            
            delay = (current_finish - baseline_finish).days
            return max(0, delay)

        df['delay_days'] = df.apply(calc_delay, axis=1)

        # 5. Project-Level Aggregates
        critical_tasks = df[df['is_critical_p6']]
        analysis_pool = critical_tasks if not critical_tasks.empty else df
        
        baseline_max_finish = df['_dt_target_end_date'].max()
        current_max_finish = df['_dt_current_end_date'].max()
        
        project_delay_days = 0
        if pd.notnull(baseline_max_finish) and pd.notnull(current_max_finish):
            project_delay_days = (current_max_finish - baseline_max_finish).days

        # 6. Project Health Metrics

        # 5. Project Health Metrics
        metrics = {
            "totalTasks": len(df),
            "completedTasks": len(df[df['status_enum'] == "COMPLETED"]),
            "inProgressTasks": len(df[df['status_enum'] == "IN_PROGRESS"]),
            "notStartedTasks": len(df[df['status_enum'] == "NOT_STARTED"]),
            "delayedTasks": len(df[df['status_enum'] == "DELAYED"]),
            "criticalCount": len(df[df['is_critical_p6']])
        }

        # 6. Critical Path Detection
        critical_path_ids = df[df['is_critical_p6']]['task_code'].tolist()

        return {
            "projectSummary": {
                "projectDelayDays": project_delay_days,
                "isDelayed": project_delay_days > 0,
                "healthMetrics": metrics,
                "criticalTasksCount": metrics["criticalCount"]
            },
            "activityAnalysis": df[['task_id', 'status_enum', 'delay_days', 'is_critical_p6', 'is_predicted_date', '_dt_current_end_date']].set_index('task_id').to_dict('index')
        }

    def calculate_project_delay(self) -> Dict:
        """Calculates delay between baseline and latest update"""
        baseline = self.get_baseline()
        latest = self.get_latest()
        if not baseline or not latest or baseline['id'] == latest['id']:
            return {"delay_days": 0, "reason": "No baseline or update available for comparison."}
        
        baseline_finish = pd.to_datetime(baseline['data_date'])
        if 'project_finish' in self.compute_basic_stats():
            baseline_finish = pd.to_datetime(self.compute_basic_stats()['project_finish'])
            
        latest = self.get_latest()
        latest_finish = pd.to_datetime(latest['data_date'])
        
        # Recalculate latest finish if possible
        latest_stats = self.compute_basic_stats()
        if 'project_finish' in latest_stats:
            latest_finish = pd.to_datetime(latest_stats['project_finish'])
            
        delay = (latest_finish - baseline_finish).days
        return {
            "baseline_finish": str(baseline_finish.date()),
            "latest_finish": str(latest_finish.date()),
            "delay_days": delay,
            "is_delayed": delay > 0
        }

    def get_critical_path_details(self, limit: int = 20) -> List[Dict]:
        """Returns structured info on the most critical tasks"""
        source = self.get_latest()
        if not source or 'tasks' not in source.get('df', {}): return []
        
        df = source['df']['tasks'].copy()
        if 'total_float_hr_cnt' not in df.columns: return []
        
        df['float'] = pd.to_numeric(df['total_float_hr_cnt'], errors='coerce').fillna(999)
        critical = df[df['float'] <= 0].sort_values('float').head(limit)
        
        results = []
        for _, row in critical.iterrows():
            results.append({
                "activity_id": row.get('task_code', ''),
                "name": row.get('task_name', ''),
                "float": row.get('float'),
                "start": str(row.get('target_start_date', ''))[:10],
                "finish": str(row.get('target_end_date', ''))[:10]
            })
        return results

    def get_logic_health_details(self) -> Dict:
        """Detailed analysis of schedule logic health"""
        source = self.get_latest()
        if not source or 'df' not in source: return {}
        
        tasks_df = source['df']['tasks']
        pred_df = source['df'].get('taskpred')
        
        if pred_df is None: return {"error": "No relationship data available"}
        
        all_ids = set(tasks_df['task_id'].tolist())
        has_successor = set(pred_df['pred_task_id'].tolist())
        has_predecessor = set(pred_df['task_id'].tolist())
        
        work_tasks = tasks_df[~tasks_df['task_type'].isin(['TT_LOE', 'TT_Mile', 'TT_FinMile'])]
        work_ids = set(work_tasks['task_id'].tolist())
        
        open_ended = (all_ids - has_successor) & work_ids
        dangling = (all_ids - has_predecessor) & work_ids
        
        return {
            "open_ended_count": len(open_ended),
            "dangling_count": len(dangling),
            "open_ended_samples": list(tasks_df[tasks_df['task_id'].isin(list(open_ended)[:5])]['task_code']),
            "dangling_samples": list(tasks_df[tasks_df['task_id'].isin(list(dangling)[:5])]['task_code'])
        }

    def get_float_distribution(self) -> Dict:
        """Breakdown of float values across the project"""
        source = self.get_latest()
        if not source or 'tasks' not in source.get('df', {}): return {}
        
        df = source['df']['tasks'].copy()
        df['float'] = pd.to_numeric(df.get('total_float_hr_cnt', 0), errors='coerce').fillna(0)
        
        # Categorize
        neg = len(df[df['float'] < 0])
        zero = len(df[df['float'] == 0])
        low = len(df[(df['float'] > 0) & (df['float'] <= 50)])
        high = len(df[df['float'] > 50])
        
        return {
            "negative": neg,
            "critical_zero": zero,
            "low_float_0_50": low,
            "high_float_50plus": high
        }

    def get_table_data(self, table_type: str = "TASK", search: str = "", limit: int = 100, offset: int = 0, source_id: Optional[str] = None) -> Dict:
        """Fetch and format paginated table data from a specific version ID"""
        source = self.get_version(source_id)
        if not source or 'df' not in source: return {"records": [], "total": 0}
        
        # Table mapping
        table_map = {
            "TASK": "tasks",
            "WBS": "projwbs",
            "RELATIONSHIPS": "taskpred",
            "PROJECT": "project"
        }
        
        df_key = table_map.get(table_type.upper(), table_type.lower())
        if df_key not in source['df']:
            return {"records": [], "total": 0, "error": f"Table '{table_type}' not found"}
            
        df = source['df'][df_key].copy()
        
        # Search & Filter
        if search:
            search_cols = ['task_name', 'task_code'] if df_key == 'tasks' else df.columns[:3]
            mask = df[search_cols].apply(lambda x: x.str.contains(search, case=False, na=False)).any(axis=1)
            df = df[mask]
            
        total = len(df)
        
        # Paginate
        paginated_df = df.iloc[offset : offset + limit]
        
        # Inject deterministic analysis if viewing TASK table
        analysis = {}
        if df_key == 'tasks':
            analysis = self.get_deterministic_analysis(source_id)
            activity_metrics = analysis.get('activityAnalysis', {})
            
            records = []
            for rec in paginated_df.to_dict('records'):
                tid = rec.get('task_id')
                metrics = activity_metrics.get(tid, {})
                rec['_analysis'] = {
                    'status': metrics.get('status_enum', 'NOT_STARTED'),
                    'delay_days': round(metrics.get('delay_days', 0), 1),
                    'is_critical': metrics.get('is_critical_p6', False),
                    'current_end_date': str(metrics.get('_dt_current_end_date', '-')).split(' ')[0],
                    'is_predicted': metrics.get('is_predicted_date', False)
                }
                records.append(rec)
            return {
                "records": records,
                "total": total,
                "table": table_type,
                "projectAnalysis": analysis.get('projectSummary', {})
            }

        return {
            "records": paginated_df.to_dict('records'),
            "total": total,
            "table": table_type
        }
