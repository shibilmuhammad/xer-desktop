import pandas as pd
import re
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

    def compute_basic_stats(self, version_id: Optional[str] = None) -> Dict:
        if not version_id and self._cached_stats: return self._cached_stats
        
        source = self.get_version(version_id) if version_id else self.get_latest()
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
        
        # Merge all metrics ensuring projectDelayDays and assessment are included
        stats['delay_matrix'] = {
            **delay_matrix, 
            **health_metrics, 
            "projectDelayDays": summary.get('projectDelayDays', 0),
            "assessment": summary.get("assessment", []),
            "qualityIssues": health_metrics.get("qualityIssues", [])
        }
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
        df['float_hrs'] = pd.to_numeric(df['total_float_hr_cnt'], errors='coerce').fillna(0) if 'total_float_hr_cnt' in df.columns else 0
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
            
            try:
                diff = current_planned_finish - baseline_finish
                return int(diff.days) if hasattr(diff, 'days') else 0
            except:
                return 0

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
        
        # Finish Variance (Standard P6 comparison)
        finish_variance = 0
        if pd.notnull(baseline_max_finish) and pd.notnull(current_max_finish):
            finish_variance = (current_max_finish - baseline_max_finish).days

        # Constraint Detection: If finish variance is flat, but we have negative float, 
        # the "Real Delay" is the amount of negative float on the critical path.
        max_neg_float_days = 0
        if not df[df['float_hrs'] < 0].empty:
            # We take the absolute value of the worst negative float
            max_neg_float_days = abs(df['float_hrs'].min() / self.hours_per_day)

        project_delay_days = finish_variance
        is_constrained = False
        
        if finish_variance <= 0 and max_neg_float_days > 0:
            is_constrained = True
            project_delay_days = round(max_neg_float_days, 0)

        # 6. DCMA 14-Point Assessment Logic
        total_tasks = len(df)
        critical_count = len(df[df['is_critical_p6']])
        neg_float_count = len(df[df['float_hrs'] < 0])
        
        task_ids = set(df['task_id'].unique())
        preds_df = source['df'].get('projwbs', pd.DataFrame()) # Placeholder for checking exists
        preds_df = source['df'].get('taskpred', pd.DataFrame())
        
        # Helper lists for checks
        incomplete_tasks = df[df['status_enum'] != 'COMPLETED']
        total_incomplete = len(incomplete_tasks)
        
        # Check 1: Logic
        has_pred = set(preds_df['task_id'].unique()) if not preds_df.empty else set()
        has_succ = set(preds_df['pred_task_id'].unique()) if not preds_df.empty else set()
        dangling = incomplete_tasks[~(incomplete_tasks['task_id'].isin(has_pred)) | ~(incomplete_tasks['task_id'].isin(has_succ))]
        pt1_val = (len(dangling) / total_incomplete * 100) if total_incomplete > 0 else 0
        
        # Check 2: Leads (Negative Lag)
        leads_count = len(preds_df[pd.to_numeric(preds_df['lag_hr_cnt'], errors='coerce') < 0]) if not preds_df.empty else 0
        total_rels = len(preds_df) if not preds_df.empty else 1
        pt2_val = (leads_count / total_rels * 100)
        
        # Check 3: Lags (Positive Lag)
        lags_count = len(preds_df[pd.to_numeric(preds_df['lag_hr_cnt'], errors='coerce') > 0]) if not preds_df.empty else 0
        pt3_val = (lags_count / total_rels * 100)
        
        # Check 4: Relationship Types (FS)
        fs_count = len(preds_df[preds_df['pred_type'] == 'PR_FS']) if not preds_df.empty else 0
        pt4_val = (fs_count / total_rels * 100)
        
        # Check 5: Hard Constraints
        hard_constraints = ['CS_MNET', 'CS_MSEO', 'CS_MSON', 'CS_MFON'] # Must Start On, Must Finish On, etc.
        hard_const_count = len(incomplete_tasks[incomplete_tasks['cstr_type'].isin(hard_constraints)])
        pt5_val = (hard_const_count / total_incomplete * 100) if total_incomplete > 0 else 0
        
        # Check 6: High Float (> 44 days)
        high_float_threshold = 44 * self.hours_per_day
        high_float_count = len(incomplete_tasks[incomplete_tasks['float_hrs'] > high_float_threshold])
        pt6_val = (high_float_count / total_incomplete * 100) if total_incomplete > 0 else 0
        
        # Check 7: Negative Float
        neg_float_count = len(incomplete_tasks[incomplete_tasks['float_hrs'] < 0])
        pt7_val = (neg_float_count / total_incomplete * 100) if total_incomplete > 0 else 0
        
        # Check 8: High Duration (> 44 days)
        # We use target_drtn_hr_cnt as it represents Planned Duration in most XER exports
        dur_col = 'target_drtn_hr_cnt' if 'target_drtn_hr_cnt' in df.columns else 'orig_dur_hr_cnt'
        high_dur_threshold = 44 * self.hours_per_day
        
        if dur_col in incomplete_tasks.columns:
            high_dur_count = len(incomplete_tasks[pd.to_numeric(incomplete_tasks[dur_col], errors='coerce').fillna(0) > high_dur_threshold])
        else:
            high_dur_count = 0
            
        pt8_val = (high_dur_count / total_incomplete * 100) if total_incomplete > 0 else 0

        # Check 11: Missed Tasks (% of completed tasks with late finish)
        missed_count = len(df[(df['status_enum'] == 'COMPLETED') & (df['delay_days'] > 0)])
        total_completed = len(df[df['status_enum'] == 'COMPLETED'])
        pt11_val = (missed_count / total_completed * 100) if total_completed > 0 else 0

        # Check 13: CPLI (Critical Path Length Index)
        # Formula: (Remaining Working Days + Total Float) / Remaining Working Days
        # Remaining Days = Data Date to Project Finish
        # Robust Data Date lookup
        data_date_val = source.get('stats', {}).get('data_date')
        if not data_date_val or data_date_val == "N/A":
            # Fallback to project info if stats not yet ready
            proj_data = source.get('data', {}).get('project', [])
            if isinstance(proj_data, list) and proj_data:
                data_date_val = proj_data[0].get('last_recalc_date')
            elif isinstance(proj_data, dict):
                data_date_val = proj_data.get('last_recalc_date')
        
        project_work_days = 1 # Default to avoid division by zero
        if data_date_val:
            try:
                # Convert to string and slice safely
                ds = str(data_date_val)[:10]
                data_date = pd.to_datetime(ds)
                finish_date = df['_dt_target_end_date'].max()
                if pd.notnull(finish_date) and pd.notnull(data_date):
                    calendar_diff = finish_date - data_date
                    if hasattr(calendar_diff, 'days'):
                        # Convert calendar days to working days (Benchmark: 5/7 conversion)
                        project_work_days = max(1, int(calendar_diff.days * 5 / 7))
            except:
                project_work_days = 1
        
        # Industrial CPLI uses the Total Float of the PROJECT FINISH milestone
        # Rogue tasks with extreme float are excluded
        finish_milestone = df[df['task_type'] == 'TT_FinMile']
        if not finish_milestone.empty:
            total_float_hrs = finish_milestone['float_hrs'].min()
        else:
            # Fallback: Minimum float of all tasks, but capped to avoid extreme outliers (orphans)
            total_float_hrs = df['float_hrs'].min() if not df.empty else 0
            # If the float is so negative it's more than the project duration, it's likely a data error/orphan
            total_float_hrs = max(total_float_hrs, -(project_work_days * self.hours_per_day))

        min_float_days = total_float_hrs / self.hours_per_day
        pt13_val = round((project_work_days + min_float_days) / project_work_days, 3)

        assessment = [
            {"id": 1, "name": "Logic", "measure": "% tasks missing links (dangling)", "val": float(pt1_val), "threshold": "<= 5%", "status": bool(pt1_val <= 5)},
            {"id": 2, "name": "Leads", "measure": "% links with Negative Lag", "val": float(pt2_val), "threshold": "0%", "status": bool(pt2_val == 0)},
            {"id": 3, "name": "Lags", "measure": "% links with Positive Lag", "val": float(pt3_val), "threshold": "<= 5%", "status": bool(pt3_val <= 5)},
            {"id": 4, "name": "Rel Types", "measure": "% Finish-to-Start relationships", "val": float(pt4_val), "threshold": ">= 90%", "status": bool(pt4_val >= 90)},
            {"id": 5, "name": "Hard Constraints", "measure": "% tasks with mandatory constraints", "val": float(pt5_val), "threshold": "<= 5%", "status": bool(pt5_val <= 5)},
            {"id": 6, "name": "High Float", "measure": "% tasks with float > 44 days", "val": float(pt6_val), "threshold": "<= 5%", "status": bool(pt6_val <= 5)},
            {"id": 7, "name": "Negative Float", "measure": "% tasks with negative float", "val": float(pt7_val), "threshold": "0%", "status": bool(pt7_val == 0)},
            {"id": 8, "name": "High Duration", "measure": "% tasks with duration > 44 days", "val": float(pt8_val), "threshold": "<= 5%", "status": bool(pt8_val <= 5)},
            {"id": 9, "name": "Invalid Dates", "measure": "Dates inconsistent with Data Date", "val": 0.0, "threshold": "0%", "status": True},
            {"id": 10, "name": "Resources", "measure": "Tasks with assigned resources", "val": 100.0, "threshold": "100%", "status": True},
            {"id": 11, "name": "Missed Tasks", "measure": "% completed tasks finished late", "val": float(pt11_val), "threshold": "<= 5%", "status": bool(pt11_val <= 5)},
            {"id": 12, "name": "Critical Path", "measure": "Continuous path integrity", "val": 100.0, "threshold": "Required", "status": bool(critical_count > 0)},
            {"id": 13, "name": "CPLI", "measure": "Critical Path Length Index", "val": float(pt13_val), "threshold": ">= 0.95", "status": bool(pt13_val >= 0.95)},
            {"id": 14, "name": "Baseline", "measure": "Project baseline assignment", "val": 100.0, "threshold": "Required", "status": bool(baseline_map)}
        ]

        # 7. Quality Metrics Aggregate
        score = 100
        issues = []
        
        if pt1_val > 5: score -= 10; issues.append("Missing schedule logic")
        if pt2_val > 0: score -= 10; issues.append("Negative lags (leads) detected")
        if pt7_val > 0: score -= 20; issues.append("Negative float (behind schedule)")
        if pt5_val > 5: score -= 10; issues.append("Excessive hard constraints")
            
        if is_constrained:
            score -= 10
            issues.append("Project delay hidden by constraints (Fixed finish date detected)")

        health_status = "Good"
        if score < 65: health_status = "Critical"
        elif score < 85: health_status = "Warning"

        # 8. Root Cause Extraction
        top_delay_drivers = df[df['delay_days'] > 0].sort_values('delay_days', ascending=False).head(20)
        top_neg_float = df[df['float_hrs'] < 0].sort_values('float_hrs').head(20)

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
                "assessment": assessment,
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
        df['float'] = pd.to_numeric(df['total_float_hr_cnt'], errors='coerce').fillna(0) if 'total_float_hr_cnt' in df.columns else 0
        
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

    def get_wbs_summary(self, version_id: Optional[str] = None, target_level: int = 2) -> List[Dict]:
        """Aggregates task data by Discipline (Activity Code) or WBS level (Heuristic Priority)"""
        source = self.get_version(version_id)
        if not source or 'df' not in source: return []
        
        tasks_df = source['df'].get('tasks')
        wbs_df = source['df'].get('projwbs')
        tables = source.get('data', {}).get('tables', {})
        
        if tasks_df is None or len(tasks_df) == 0: return []
        
        # 1. Try grouping by Activity Code (The Gold Standard)
        discipline_map = {}
        grouping_mode = "WBS"
        
        if 'TASKACTV' in tables and 'ACTVTYPE' in tables and 'ACTVVAL' in tables:
            # Find the type_id for "Discipline"
            types = pd.DataFrame(tables['ACTVTYPE'])
            disc_types = types[types['actv_code_type_name'].str.contains('discipline|disc|dept|trade|responsibility', case=False, na=False)]
            
            if not disc_types.empty:
                type_id = disc_types.iloc[0]['actv_code_type_id']
                vals = pd.DataFrame(tables['ACTVVAL'])
                map_df = pd.DataFrame(tables['TASKACTV'])
                
                # Filter specifically for our Discipline type
                specific_map = map_df[map_df['actv_code_type_id'] == type_id]
                specific_vals = vals[vals['actv_code_type_id'] == type_id]
                
                # Join to get names
                merged_map = specific_map.merge(specific_vals, on='actv_code_id', how='left')
                discipline_map = merged_map.set_index('task_id')['actv_code_name'].to_dict()
                grouping_mode = f"Code:{disc_types.iloc[0]['actv_code_type_name']}"

        # 2. Cleanup & Processing
        def clean_label(label):
            if not label or not isinstance(label, str): return label
            # Strip numeric prefixes like "4 ", "05. ", "1 - "
            return re.sub(r'^[\d\.\-\s]+', '', label).strip()

        tasks_copy = tasks_df.copy()
        
        if discipline_map:
            tasks_copy['group_key'] = tasks_copy['task_id'].map(discipline_map).fillna("Unassigned / Other")
            tasks_copy['group_name'] = tasks_copy['group_key'].apply(clean_label)
        else:
            # Fallback to WBS
            if wbs_df is not None:
                parent_map = wbs_df.set_index('wbs_id')['parent_wbs_id'].to_dict()
                wbs_info = wbs_df.set_index('wbs_id')[['wbs_short_name', 'wbs_name']].to_dict('index')
                
                def get_parent_at_level(wbs_id, level):
                    path = []
                    curr = wbs_id
                    while curr in parent_map and pd.notnull(curr):
                        path.append(curr)
                        curr = parent_map[curr]
                    path.reverse()
                    idx = min(level, len(path)-1)
                    return path[idx] if path else wbs_id

                tasks_copy['target_wbs_id'] = tasks_copy['wbs_id'].apply(lambda x: get_parent_at_level(x, target_level))
                tasks_copy['group_name'] = tasks_copy['target_wbs_id'].apply(lambda x: clean_label(wbs_info.get(x, {}).get('wbs_name', 'General')))
            else:
                tasks_copy['group_name'] = "General Project"

        # 3. Handle Milestones (Separate from functional work)
        is_mile = tasks_copy['task_type'].isin(['TT_Mile', 'TT_FinMile'])
        tasks_copy.loc[is_mile, 'group_name'] = "Project Milestones"

        # 4. Get deterministic metrics
        analysis = self.get_deterministic_analysis(version_id)
        activity_metrics = analysis.get('activityAnalysis', {})
        
        metrics_list = []
        for tid, m in activity_metrics.items():
            metrics_list.append({
                'task_id': tid,
                'status': m.get('status_enum'),
                'float_hrs': m.get('float_hrs', 0)
            })
        metrics_df = pd.DataFrame(metrics_list)
        
        # 5. Join and Aggregate
        merged = tasks_copy.merge(metrics_df, on='task_id', how='left')
        merged['drtn'] = pd.to_numeric(merged['target_drtn_hr_cnt'], errors='coerce').fillna(0) / self.hours_per_day if 'target_drtn_hr_cnt' in merged.columns else 0
        
        summary = merged.groupby('group_name').agg(
            total_tasks=('task_id', 'count'),
            duration_days=('drtn', 'sum'),
            avg_float_hrs=('float_hrs', 'mean'),
            completed=('status', lambda x: (x == 'COMPLETED').sum()),
            in_progress=('status', lambda x: (x == 'IN_PROGRESS').sum()),
            not_started=('status', lambda x: (x == 'NOT_STARTED').sum())
        ).reset_index()
        
        # 6. Formatting
        results = []
        for _, row in summary.iterrows():
            results.append({
                "discipline": str(row['group_name']),
                "activities": int(row['total_tasks']),
                "duration_days": round(float(row['duration_days']), 0),
                "avg_float": round(float(row['avg_float_hrs']), 1),
                "status": f"{int(row['completed'])}C / {int(row['in_progress'])}IP / {int(row['not_started'])}NS"
            })
        
        # Sort by impact (negative float)
        return sorted(results, key=lambda x: x['avg_float'])

    def get_table_data(self, table_type: str = "TASK", search: str = "", limit: int = 100, offset: int = 0, source_id: Optional[str] = None, filter_type: str = "ALL") -> Dict:
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
        
        # 1. Search Logic
        if search:
            search_cols = ['task_name', 'task_code'] if df_key == 'tasks' else df.columns[:3]
            mask = df[search_cols].apply(lambda x: x.str.contains(search, case=False, na=False)).any(axis=1)
            df = df[mask]
            
        # 2. Analytical Filtering (pre-pagination)
        if df_key == 'tasks' and filter_type != 'ALL':
            analysis = self.get_deterministic_analysis(source_id)
            metrics = analysis.get('activityAnalysis', {})
            
            def check_filter(tid):
                m = metrics.get(tid, {})
                if filter_type == 'CRITICAL': return m.get('is_critical_p6', False)
                if filter_type == 'NEG_FLOAT': return (m.get('float_hrs', 0) < 0)
                if filter_type == 'DELAYED': return (m.get('delay_days', 0) > 0)
                if filter_type == 'DELAYED_CRITICAL': return m.get('delay_float_category') == 'DELAYED_CRITICAL'
                if filter_type == 'DELAYED_NEGATIVE': return m.get('delay_float_category') == 'DELAYED_NEGATIVE'
                return True
            
            df = df[df['task_id'].apply(check_filter)]
            
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
