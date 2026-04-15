import json
import os
import pandas as pd
from openai import OpenAI
from typing import Dict, Any, Optional
from .data_store import XERDataStore

class XERAnalyzer:
    def __init__(self):
        self.data_store = XERDataStore()
        api_key = os.environ.get("OPENAI_API_KEY", "")
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"


    def get_basic_stats(self) -> Dict[str, Any]:
        """Wrapper for backward compatibility with main.py"""
        return self.data_store.compute_basic_stats()

    def analyze(self, query: str) -> str:
        """Main entry point: Route -> Execute -> Explain"""
        analysis_results = self._route_query(query)
        return self._get_ai_explanation(query, analysis_results)

    def _route_query(self, query: str) -> Dict[str, Any]:
        """Maps user query to deterministic backend functions"""
        query = query.lower()
        results = {}

        if any(w in query for w in ['delay', 'variance', 'behind', 'finish', 'date', 'late']):
            results['delay_analysis'] = self.calculate_project_delay()
            
        if any(w in query for w in ['critical', 'longest path', 'driving']):
            results['critical_path'] = self.get_critical_path()
            
        if any(w in query for w in ['negative float', 'float', 'slack']):
            results['float_analysis'] = self.get_negative_float_activities()
            
        if any(w in query for w in ['open ended', 'dangling', 'integrity', 'logic', 'missing']):
            results['integrity_checks'] = self.check_open_ended_activities()
        
        if any(w in query for w in ['quality', 'score', 'health', 'dcma', 'overview']):
            results['schedule_quality'] = self.get_schedule_quality()
            results['project_health'] = self.get_project_health()
            
        if any(w in query for w in ['driver', 'driving', 'cause', 'why']):
            results['delay_drivers'] = self.get_delay_drivers()
            
        if any(w in query for w in ['compare', 'difference', 'status', 'summary', 'update', 'both']):
            results['project_health'] = self.get_project_health()
            results['delay_analysis'] = self.calculate_project_delay()
            results['delay_drivers'] = self.get_delay_drivers()

        # If we couldn't match anything, assume general summary Instead of failing without data
        if not results:
            results['project_health'] = self.get_project_health()
            results['general_info'] = "The user asked a general question. Provide a high-level summary of the schedule's current health and delay standing based on the project_health data. Do not say 'no module triggered'."

        return results

    def get_project_health(self) -> Dict[str, Any]:
        """Returns the high-level P6 analytical status"""
        analysis = self.data_store.get_deterministic_analysis()
        summary = analysis.get('projectSummary', {})
        metrics = summary.get('healthMetrics', {})
        
        return {
            "score": metrics.get('projectHealthScore', 0),
            "status": metrics.get('healthStatus', 'Unknown'),
            "is_constrained": metrics.get('is_constrained', False),
            "delay_days": summary.get('projectDelayDays', 0),
            "issues": metrics.get('qualityIssues', [])
        }

    def calculate_project_delay(self) -> Dict[str, Any]:
        """Calculates project-level delay based on max finish variance"""
        health = self.get_project_health()
        delay_days = health['delay_days']
        
        summary_msg = f"The project finish date has shifted by {delay_days} days."
        if delay_days == 0 and health['is_constrained']:
            summary_msg = "The project finish date is currently fixed (0-day variance), but significant negative float suggests the schedule is constrained and internally delayed."
        elif delay_days == 0:
            summary_msg = "The project is currently on track with 0 days of variance."

        return {
            "summary": summary_msg,
            "metrics": {
                "projectDelay": delay_days,
                "isConstrained": health['is_constrained']
            },
            "issues": health['issues'],
            "recommendations": ["Investigate hidden constraints preventing finish date movement."] if health['is_constrained'] else []
        }

    def get_schedule_quality(self) -> Dict[str, Any]:
        """Provides a detailed DCMA-style quality report"""
        health = self.get_project_health()
        return {
            "summary": f"Schedule Quality Score: {health['score']}/100 ({health['status']})",
            "metrics": {"score": health['score']},
            "issues": health['issues'],
            "recommendations": ["Fix open-ended logic to improve critical path reliability."] if health['score'] < 80 else []
        }

    def get_critical_path(self) -> Dict[str, Any]:
        """Identifies critical path activities (Float <= 0)"""
        analysis = self.data_store.get_deterministic_analysis()
        activity_metrics = analysis.get('activityAnalysis', {})
        
        critical_ids = [tid for tid, obj in activity_metrics.items() if obj.get('is_critical_p6')]
        
        source = self.data_store.get_latest()
        names = {}
        if source and 'df' in source and 'tasks' in source['df']:
            tasks_df = source['df']['tasks']
            names = tasks_df[tasks_df['task_id'].isin(critical_ids)][['task_id', 'task_name']].set_index('task_id')['task_name'].to_dict()

        critical_list = [{"id": tid, "name": names.get(tid, tid), "delay": activity_metrics[tid].get('delay_days')} for tid in critical_ids]

        total = len(activity_metrics)
        pct = (len(critical_list) / total) * 100 if total > 0 else 0

        return {
            "summary": f"Detected {len(critical_list)} activities on the critical path.",
            "metrics": {
                "criticalCount": len(critical_list),
                "criticalPct": f"{pct:.1f}%"
            },
            "issues": ["Large critical path detected."] if len(critical_list) > 50 else [],
            "recommendations": ["Monitor prioritized activities for potential bottlenecks."]
        }

    def get_negative_float_activities(self) -> Dict[str, Any]:
        """Filters activities with negative float (Logic-driven delays)"""
        analysis = self.data_store.get_deterministic_analysis()
        activity_metrics = analysis.get('activityAnalysis', {})
        
        neg_float = [tid for tid, obj in activity_metrics.items() if (obj.get('float_hrs') or 0) < 0]
        
        return {
            "summary": f"Found {len(neg_float)} activities with negative float.",
            "metrics": {"negativeFloatCount": len(neg_float)},
            "issues": ["Negative float indicates the project cannot meet its current constraints."] if neg_float else [],
            "recommendations": ["Verify 'Must Finish By' dates and out-of-sequence progress."] if neg_float else []
        }

    def check_open_ended_activities(self) -> Dict[str, Any]:
        """Detects activities missing predecessors or successors"""
        source = self.data_store.get_latest()
        if not source or 'df' not in source: return {"summary": "No data available.", "metrics": {}, "issues": [], "recommendations": []}
        
        tasks_df = source['df'].get('tasks')
        preds_df = source['df'].get('taskpred')
        
        if tasks_df is None or preds_df is None: 
            return {
                "summary": "Tables missing.",
                "metrics": {},
                "issues": ["Required XER tables (TASK/TASKPRED) not found."],
                "recommendations": ["Ensure XER file contains project relationships."]
            }

        all_tids = set(tasks_df['task_id'])
        has_pred = set(preds_df['task_id'])
        has_succ = set(preds_df['pred_task_id'])

        open_starts = list(all_tids - has_pred)
        open_finishes = list(all_tids - has_succ)

        return {
            "summary": f"Integrity Check: {len(open_starts)} Open Starts, {len(open_finishes)} Open Finishes detected.",
            "metrics": {
                "openStarts": len(open_starts),
                "openFinishes": len(open_finishes)
            },
            "issues": ["Open-ended activities invalidate critical path reliability."] if (open_starts or open_finishes) else [],
            "recommendations": ["Link open-ended activities to appropriate milestones."]
        }

    def get_delay_drivers(self) -> Dict[str, Any]:
        """Identifies activities causing the most project-level slippage"""
        analysis = self.data_store.get_deterministic_analysis()
        summary = analysis.get('projectSummary', {})
        drivers = summary.get('topDrivers', [])

        return {
            "summary": "Top delay drivers identified on the critical path.",
            "metrics": {"impactedDriversCount": len(drivers)},
            "issues": [f"Activity {d['task_code']} is driving {d['delay_days']} days of slippage." for d in drivers],
            "recommendations": ["Focus schedule recovery efforts on top driving activities."]
        }

    def _get_ai_explanation(self, query: str, data: Dict[str, Any]) -> str:
        try:
            prompt = f"""
User Query: {query}
Structured Analysis: {json.dumps(data, indent=2)}

Instructions:
1. You are a professional Schedule Analyst (Primavera P6 Expert).
2. Explain the results concisely using the provided JSON only.
3. DO NOT perform any math. Simply interpret the 'metrics', 'issues', and 'recommendations'.
4. Use clear Markdown headings and bullet points.
5. ONLY answer what is relevant to the user's specific query.
6. Be specific, professional and actionable. Avoid vague statements.
"""
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert Primavera P6 schedule analyst. Explain schedule analysis results clearly and professionally. No code. No math. Use markdown formatting."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"**Analysis Complete**\n\nResult: {json.dumps(data, indent=2)}\n\n_Error getting AI explanation: {str(e)}_"

