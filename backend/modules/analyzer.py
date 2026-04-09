import json
import pandas as pd
from openai import OpenAI
from typing import Dict, Any, Optional
from .data_store import XERDataStore

class XERAnalyzer:
    def __init__(self, ollama_url: str = "http://localhost:11434/v1"):
        self.data_store = XERDataStore()
        self.client = OpenAI(base_url=ollama_url, api_key="ollama")

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
        
        if any(w in query for w in ['delay', 'variance', 'behind', 'finish', 'date']):
            results['delay_analysis'] = self.calculate_project_delay()
            
        if any(w in query for w in ['critical', 'longest path', 'driving']):
            results['critical_path'] = self.get_critical_path()
            
        if any(w in query for w in ['negative float', 'float', 'slack']):
            results['float_analysis'] = self.get_negative_float_activities()
            
        if any(w in query for w in ['open ended', 'dangling', 'integrity', 'logic', 'missing']):
            results['integrity_checks'] = self.check_open_ended_activities()
            
        if 'driver' in query or 'driving' in query:
            results['delay_drivers'] = self.get_delay_drivers()

        return results

    def calculate_project_delay(self) -> Dict[str, Any]:
        """Calculates project-level delay based on max finish variance"""
        analysis = self.data_store.get_deterministic_analysis()
        summary = analysis.get('projectSummary', {})
        metrics = summary.get('healthMetrics', {})
        
        delay_days = int(summary.get('projectDelayDays', 0))
        status = "DELAYED" if delay_days > 0 else "ON TRACK"
        
        total = metrics.get('totalTasks', 1)
        completed = metrics.get('completedTasks', 0)
        pct = (completed / total) * 100 if total > 0 else 0
        
        return {
            "summary": f"The project is currently {status} by {delay_days} days.",
            "metrics": {
                "projectDelay": delay_days,
                "totalTasks": total,
                "completedPct": f"{pct:.1f}%"
            },
            "issues": ["Project finish date has slipped relative to baseline."] if delay_days > 0 else [],
            "recommendations": ["Review critical path activities for acceleration options."] if delay_days > 0 else ["Maintain current progress."]
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
        
        neg_float = [tid for tid, obj in activity_metrics.items() if obj.get('status_enum') == "DELAYED"]
        
        return {
            "summary": f"Found {len(neg_float)} activities with negative float.",
            "metrics": {"negativeFloatCount": len(neg_float)},
            "issues": ["Negative float indicates logic is already behind the current data date."] if neg_float else [],
            "recommendations": ["Recalculate schedule with actual dates or adjust logic."] if neg_float else []
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
        activity_metrics = analysis.get('activityAnalysis', {})
        
        driver_objs = [{"id": tid, "delay": obj['delay_days']} for tid, obj in activity_metrics.items() if obj.get('is_critical_p6')]
        drivers = sorted(driver_objs, key=lambda x: x['delay'], reverse=True)[:5]

        return {
            "summary": "Top delay drivers identified on the critical path.",
            "metrics": {"impactedDriversCount": len(drivers)},
            "issues": [f"Activity {d['id']} is driving {d['delay']} days of slippage." for d in drivers],
            "recommendations": ["Focus schedule recovery efforts on top driving activities."]
        }

    def _get_ai_explanation(self, query: str, data: Dict[str, Any]) -> str:
        try:
            prompt = f"""
            User Query: {query}
            Structured Analysis: {json.dumps(data, indent=2)}
            
            Instructions:
            1. You are a professional Schedule Analyst (P6 Expert).
            2. Explain the results concisely using the provided JSON only.
            3. DO NOT perform any math. Simply interpret the 'metrics', 'issues', and 'recommendations'.
            4. Use clear Markdown headings and bullet points.
            5. Provide a summary of the project health based on the findings.
            """
            
            response = self.client.chat.completions.create(
                model="llama3",
                messages=[
                    {"role": "system", "content": "Explain schedule analysis results as an expert analyst. No code. No math."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Analysis complete. Result Summary: {json.dumps(data, indent=2)}"
