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
                
                # Simple delay check for stats (comparing current end to target end)
                # Note: For full accuracy, the deterministic analysis should be used.
                if 'target_end_date' in tasks_df.columns and 'act_end_date' in tasks_df.columns:
                    # Very basic check for stats
                    pass 

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

        # Add the new matrix and health metrics
        analysis = self.get_deterministic_analysis(source['id'])
        summary = analysis.get('projectSummary', {})
        delay_matrix = summary.get('delayFloatMatrix', {})
        health_metrics = summary.get('healthMetrics', {})
        stats['delay_matrix'] = {**delay_matrix, **health_metrics}
        stats['topDrivers'] = summary.get('topDrivers', [])
        stats['topRisks'] = summary.get('topRisks', [])

        self._cached_stats = stats
        return stats

    def _get_baseline_map(self) -> Dict[str, pd.Timestamp]:
        """Helper to get task_code -> target_end_date from baseline"""
        baseline = self.get_baseline()
        if not baseline or 'df' not in baseline or 'tasks' not in baseline['df']:
            return {}
        df = baseline['df']['tasks'].copy()
        df['_dt_target_end_date'] = pd.to_datetime(df['target_end_date'], errors='coerce')
        return df.set_index('task_code')['_dt_target_end_date'].to_dict()

    def get_deterministic_analysis(self, version_id: Optional[str] = None) -> Dict:
        """
        Pure deterministic schedule analysis based on P6 principles.
        Calculates status, delays (Baseline vs Update), and quality metrics.
        """
        source = self.get_version(version_id)
        if not source or 'df' not in source or 'tasks' not in source['df']:
            return {}

        df = source['df']['tasks'].copy()
        baseline_map = self._get_baseline_map()
        
        # 1. Normalize & Pre-process
        df['float_hrs'] = pd.to_numeric(df.get('total_float_hr_cnt', 0), errors='coerce').fillna(0)
        df['float_days'] = df['float_hrs'] / self.hours_per_day
        
        date_cols = ['target_start_date', 'target_end_date', 'act_start_date', 'act_end_date']
        for col in date_cols:
            if col in df.columns:
                df[f'_dt_{col}'] = pd.to_datetime(df[col], errors='coerce')

        # 2. Status Calculation
        def calc_status(row):
            is_completed = pd.notnull(row.get('_dt_act_end_date'))
            is_in_progress = pd.notnull(row.get('_dt_act_start_date')) and not is_completed
            if is_completed: return "COMPLETED"
            if is_in_progress: return "IN_PROGRESS"
            return "NOT_STARTED"

        df['status_enum'] = df.apply(calc_status, axis=1)
        df['is_critical_p6'] = df['float_hrs'] <= 0

        # 2.5. Unified Current End Date Logic
        def get_current_end_date(row):
            act = row.get('_dt_act_end_date')
            plan = row.get('_dt_target_end_date')
            return act if pd.notnull(act) else plan

        df['_dt_current_end_date'] = df.apply(get_current_end_date, axis=1)
        df['is_predicted_date'] = pd.isnull(df['_dt_act_end_date']) & pd.notnull(df['_dt_target_end_date'])

        # 3. Precision P6 Delay Calculation (BASELINE vs UPDATE PLANNED)
        def calc_p6_delay(row):
            code = row.get('task_code')
            baseline_finish = baseline_map.get(code)
            current_planned_finish = row.get('_dt_target_end_date')
            
            if pd.isnull(baseline_finish) or pd.isnull(current_planned_finish):
                return 0
            
            delay = (current_planned_finish - baseline_finish).days
            return delay

        df['delay_days'] = df.apply(calc_p6_delay, axis=1)

        # 4. Delay-Float Matrix Logic
        def classify_matrix(row):
            delay = row['delay_days']
            flt = row['float_hrs']
            if delay > 0:
                if flt > 0: return "DELAYED_SAFE"
                if flt == 0: return "DELAYED_CRITICAL"
                if flt < 0: return "DELAYED_NEGATIVE"
            return "NORMAL"

        df['delay_float_category'] = df.apply(classify_matrix, axis=1)

        # 5. Project-Level Calculation
        baseline_max_finish = max(baseline_map.values()) if baseline_map else df['_dt_target_end_date'].max()
        current_max_finish = df['_dt_target_end_date'].max()
        
        project_delay_days = 0
        if pd.notnull(baseline_max_finish) and pd.notnull(current_max_finish):
            project_delay_days = (current_max_finish - baseline_max_finish).days

        # 6. Schedule Quality Engine
        total_tasks = len(df)
        critical_count = len(df[df['is_critical_p6']])
        neg_float_count = len(df[df['float_hrs'] < 0])
        
        crit_pct = (critical_count / total_tasks * 100) if total_tasks > 0 else 0
        neg_pct = (neg_float_count / total_tasks * 100) if total_tasks > 0 else 0
        
        score = 100
        issues = []
        
        if crit_pct > 30: 
            score -= 15
            issues.append(f"High Critical Path Activity ({crit_pct:.1f}%)")
        if neg_pct > 10: 
            score -= 20
            issues.append(f"Significant Negative Float ({neg_pct:.1f}%)")
            
        is_constrained = False
        if project_delay_days <= 0 and neg_pct > 15:
            is_constrained = True
            score -= 10
            issues.append("Project delay hidden by constraints (Fixed finish date detected)")

        health_status = "Good"
        if score < 65: health_status = "Critical"
        elif score < 85: health_status = "Warning"

        # 7. Root Cause Extraction
        top_delay_drivers = df[df['delay_days'] > 0].sort_values('delay_days', ascending=False).head(5)
        top_neg_float = df[df['float_hrs'] < 0].sort_values('float_hrs').head(5)

        metrics = {
            "totalTasks": total_tasks,
            "completedTasks": len(df[df['status_enum'] == "COMPLETED"]),
            "inProgressTasks": len(df[df['status_enum'] == "IN_PROGRESS"]),
            "notStartedTasks": len(df[df['status_enum'] == "NOT_STARTED"]),
            "delayedTasks": len(df[df['delay_days'] > 0]),
            "criticalCount": critical_count,
            "projectHealthScore": score,
            "healthStatus": health_status,
            "isConstrained": is_constrained,
            "qualityIssues": issues
        }

        matrix_summary = {
            "total_delayed": metrics["delayedTasks"],
            "delayed_safe": len(df[df['delay_float_category'] == "DELAYED_SAFE"]),
            "delayed_critical": len(df[df['delay_float_category'] == "DELAYED_CRITICAL"]),
            "delayed_negative": len(df[df['delay_float_category'] == "DELAYED_NEGATIVE"])
        }

        return {
            "projectSummary": {
                "projectDelayDays": project_delay_days,
                "isDelayed": project_delay_days > 0,
                "healthMetrics": metrics,
                "delayFloatMatrix": matrix_summary,
                "topDrivers": top_delay_drivers[['task_code', 'task_name', 'delay_days']].to_dict('records'),
                "topRisks": top_neg_float[['task_code', 'task_name', 'float_hrs']].to_dict('records')
            },
            "activityAnalysis": df[['task_id', 'task_code', 'task_name', 'status_enum', 'delay_days', 'float_hrs', 'delay_float_category', 'is_critical_p6', 'is_predicted_date', '_dt_current_end_date']].set_index('task_id').to_dict('index')
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
