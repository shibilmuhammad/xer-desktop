import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import timedelta

class CPMScheduler:
    def __init__(self, hours_per_day: int = 10):
        self.hours_per_day = hours_per_day

    def calculate(self, tasks_df: pd.DataFrame, relationships_df: pd.DataFrame, project_start_date: pd.Timestamp) -> pd.DataFrame:
        """
        Performs Forward and Backward pass to calculate ES, EF, LS, LF, and Total Float.
        """
        if tasks_df.empty:
            return tasks_df

        # 1. Prepare Data
        tasks = tasks_df.copy()
        rels = relationships_df.copy() if not relationships_df.empty else pd.DataFrame(columns=['task_id', 'pred_task_id', 'pred_type', 'lag_hr_cnt'])

        # Convert durations and lags to numeric hours
        tasks['duration_hrs'] = pd.to_numeric(tasks['target_drtn_hr_cnt'], errors='coerce').fillna(0)
        rels['lag_hrs'] = pd.to_numeric(rels['lag_hr_cnt'], errors='coerce').fillna(0)

        # Initialize computed fields (in hours from project start)
        tasks['es_hrs'] = 0.0
        tasks['ef_hrs'] = 0.0
        tasks['ls_hrs'] = 0.0
        tasks['lf_hrs'] = 0.0
        tasks['tf_hrs'] = 0.0

        # Build adjacency lists
        # Successors: task_id -> list of (successor_id, rel_type, lag)
        # Predecessors: task_id -> list of (predecessor_id, rel_type, lag)
        successors = {tid: [] for tid in tasks['task_id']}
        predecessors = {tid: [] for tid in tasks['task_id']}

        for _, row in rels.iterrows():
            sid = row['task_id']      # Successor
            pid = row['pred_task_id'] # Predecessor
            rtype = row['pred_type']
            lag = row['lag_hrs']

            if sid in tasks['task_id'].values and pid in tasks['task_id'].values:
                successors[pid].append((sid, rtype, lag))
                predecessors[sid].append((pid, rtype, lag))

        # 2. Forward Pass (ES, EF)
        # We'll use a topological sort approach. 
        # Calculate in-degree (number of predecessors)
        in_degree = {tid: len(predecessors[tid]) for tid in tasks['task_id']}
        queue = [tid for tid in tasks['task_id'] if in_degree[tid] == 0]
        
        # Track processed tasks to detect cycles
        processed_count = 0
        
        # Dictionary for quick access to ES/EF/Duration
        task_data = tasks.set_index('task_id')[['duration_hrs', 'es_hrs', 'ef_hrs']].to_dict('index')

        while queue:
            pid = queue.pop(0)
            processed_count += 1
            
            # EF = ES + Duration
            task_data[pid]['ef_hrs'] = task_data[pid]['es_hrs'] + task_data[pid]['duration_hrs']
            
            for sid, rtype, lag in successors[pid]:
                impact = 0.0
                if rtype == 'PR_FS':
                    impact = task_data[pid]['ef_hrs'] + lag
                elif rtype == 'PR_SS':
                    impact = task_data[pid]['es_hrs'] + lag
                elif rtype == 'PR_FF':
                    # EF_s >= EF_p + Lag => ES_s + Dur_s >= EF_p + Lag => ES_s >= EF_p + Lag - Dur_s
                    impact = task_data[pid]['ef_hrs'] + lag - task_data[sid]['duration_hrs']
                elif rtype == 'PR_SF':
                    # EF_s >= ES_p + Lag => ES_s + Dur_s >= ES_p + Lag => ES_s >= ES_p + Lag - Dur_s
                    impact = task_data[pid]['es_hrs'] + lag - task_data[sid]['duration_hrs']
                
                task_data[sid]['es_hrs'] = max(task_data[sid]['es_hrs'], impact)
                
                in_degree[sid] -= 1
                if in_degree[sid] == 0:
                    queue.append(sid)

        # Handle cycles or disconnected nodes (P6 usually treats them as having project start as ES)
        # For this implementation, we assume a valid DAG for simplicity, but we've processed all reachable nodes.

        # 3. Backward Pass (LS, LF)
        # Find project finish (max EF)
        max_ef = max(t['ef_hrs'] for t in task_data.values()) if task_data else 0.0
        
        # Initialize LF/LS
        for tid in task_data:
            task_data[tid]['lf_hrs'] = max_ef
            task_data[tid]['ls_hrs'] = max_ef - task_data[tid]['duration_hrs']

        # Reverse in-degree for backward pass (number of successors)
        out_degree = {tid: len(successors[tid]) for tid in tasks['task_id']}
        queue = [tid for tid in tasks['task_id'] if out_degree[tid] == 0]

        while queue:
            sid = queue.pop(0)
            
            # LS = LF - Duration
            task_data[sid]['ls_hrs'] = task_data[sid]['lf_hrs'] - task_data[sid]['duration_hrs']
            
            for pid, rtype, lag in predecessors[sid]:
                impact = max_ef
                if rtype == 'PR_FS':
                    # LF_p <= LS_s - Lag
                    impact = task_data[sid]['ls_hrs'] - lag
                elif rtype == 'PR_SS':
                    # LS_p <= LS_s - Lag => LF_p - Dur_p <= LS_s - Lag => LF_p <= LS_s - Lag + Dur_p
                    impact = task_data[sid]['ls_hrs'] - lag + task_data[pid]['duration_hrs']
                elif rtype == 'PR_FF':
                    # LF_p <= LF_s - Lag
                    impact = task_data[sid]['lf_hrs'] - lag
                elif rtype == 'PR_SF':
                    # LS_p <= LF_s - Lag => LF_p - Dur_p <= LF_s - Lag => LF_p <= LF_s - Lag + Dur_p
                    impact = task_data[sid]['lf_hrs'] - lag + task_data[pid]['duration_hrs']
                
                task_data[pid]['lf_hrs'] = min(task_data[pid]['lf_hrs'], impact)
                
                out_degree[pid] -= 1
                if out_degree[pid] == 0:
                    queue.append(pid)

        # 4. Final Calculations and Formatting
        computed_results = []
        for tid in tasks['task_id']:
            d = task_data[tid]
            es = project_start_date + timedelta(hours=d['es_hrs'])
            ef = project_start_date + timedelta(hours=d['ef_hrs'])
            ls = project_start_date + timedelta(hours=d['ls_hrs'])
            lf = project_start_date + timedelta(hours=d['lf_hrs'])
            tf = d['ls_hrs'] - d['es_hrs']
            
            computed_results.append({
                'task_id': tid,
                'early_start': es.strftime('%Y-%m-%d %H:%M'),
                'early_finish': ef.strftime('%Y-%m-%d %H:%M'),
                'late_start': ls.strftime('%Y-%m-%d %H:%M'),
                'late_finish': lf.strftime('%Y-%m-%d %H:%M'),
                'total_float': round(tf / self.hours_per_day, 2) # in days
            })

        results_df = pd.DataFrame(computed_results)
        return tasks.merge(results_df, on='task_id', how='left')
