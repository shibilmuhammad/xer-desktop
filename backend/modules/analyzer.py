import os
import json
import logging
import pandas as pd
from openai import OpenAI
from typing import Dict, Any, Optional
from .data_store import XERDataStore

class XERAnalyzer:
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/v1"):
        self.data_store = XERDataStore()
        self.ollama_url = ollama_url
        
        # Check for OpenAI Key to determine default provider
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.provider = "openai" if api_key else "local"
        self.model = "gpt-4o" if api_key else "llama3"
        
        self._initialize_client()
        self._cache = {}

    def _initialize_client(self):
        """Internal helper to setup the OpenAI client based on the current provider."""
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        
        if self.provider == "openai" and api_key:
            self.client = OpenAI(api_key=api_key)
            # Use gpt-4o as default for high-precision tool calling
            if self.model == "llama3": self.model = "gpt-4o" 
        else:
            # Fallback to local if no API key or explicitly set to local
            self.provider = "local"
            self.client = OpenAI(base_url=self.ollama_url, api_key="ollama")
            if self.model == "gpt-4o": self.model = "llama3"

    def get_config(self) -> Dict[str, str]:
        """Returns the current AI configuration."""
        return {
            "provider": self.provider,
            "model": self.model,
            "ollama_url": self.ollama_url,
            "has_openai_key": bool(os.getenv("OPENAI_API_KEY", "").strip())
        }

    def set_config(self, provider: str, model: Optional[str] = None):
        """Updates the AI configuration and re-initializes the client."""
        if provider in ["openai", "local"]:
            self.provider = provider
        if model:
            self.model = model
        self._initialize_client()
        return self.get_config()

    def get_basic_stats(self, version_id: Optional[str] = None) -> Dict[str, Any]:
        """Wrapper for backward compatibility and version-specific stats"""
        return self.data_store.compute_basic_stats(version_id)

    def analyze(self, query: str) -> Dict[str, Any]:
        """Main entry point: Route -> Execute -> structured dict"""
        self._cache.clear() 
        
        try:
            if self.provider == "openai":
                return self._analyze_with_tools(query)
            else:
                return self._analyze_local(query)
        except Exception as e:
            logging.error(f"Analysis error: {e}")
            return self._fallback_deterministic(query, str(e))

    def _analyze_with_tools(self, query: str) -> Dict[str, Any]:
        tools = [
            {"type": "function", "function": {"name": "get_project_health", "description": "Returns the high-level P6 analytical status, health score, and days of delay."}},
            {"type": "function", "function": {"name": "calculate_project_delay", "description": "Calculates project-level delay based on max finish variance between baseline and updates."}},
            {"type": "function", "function": {"name": "get_schedule_quality", "description": "Provides a detailed DCMA-style quality report and score."}},
            {"type": "function", "function": {"name": "get_critical_path", "description": "Identifies critical path activities (Float <= 0) and counts them."}},
            {"type": "function", "function": {"name": "get_negative_float_activities", "description": "Filters activities with negative float."}},
            {"type": "function", "function": {"name": "check_open_ended_activities", "description": "Detects activities missing predecessors or successors."}},
            {"type": "function", "function": {"name": "get_delay_drivers", "description": "Identifies activities causing the most project-level slippage."}},
            {"type": "function", "function": {"name": "get_discipline_summary", "description": "Provides a forensic summary of status, duration, and float aggregated by project discipline. This uses Activity Codes (The Gold Standard) prioritized over WBS levels, and automatically separates Milestones for a clean executive view."}},
            {
                "type": "function",
                "function": {
                    "name": "search_activities",
                    "description": "Searches the schedule database for specific activities by exact or partial name, code, or description. Use this tool specifically when the user asks for details (like start/finish dates, status) of a specific activity by name.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_term": {
                                "type": "string",
                                "description": "The exact or partial name/code of the activity to search for."
                            }
                        },
                        "required": ["search_term"]
                    }
                }
            }
        ]
        
        system_prompt = """
        You are a Senior Forensic Schedule Delay Analyst and P6 Expert.
        You communicate with professional authority, precision, and deep analytical insight. 
        Your goal is to provide realistic, data-grounded, and actionable schedule intelligence.
        
        For questions about the specific project:
        1. Always use provided tools to fetch grounded facts.
        2. DO NOT just list numbers. Explain the causal relationship (e.g., 'The Mechanical discipline is driving the critical path; its delay has eroded the project's buffer').
        3. Use professional terminology: "Concurrent delay", "Driving relationship", "Logic trace", "Float consumption", "Status variance".
        4. **Detailed Listing**: When asked to list high-risk or delayed activities, use the 'data' field in tool results.
        5. **True Discipline Summaries**: Use the 'get_discipline_summary' tool. It provides a cleaned, forensic view of the project departments (e.g., Civil, Design, Procurement). 
           - **NOTE**: 'Project Milestones' is a separate category containing the core schedule checkpoints. 
           - **Presentation**: Present the results in a professional Markdown table sorted by Average Float (most negative first).
        
        For general questions, use your PMBOK/P6 expertise to provide best-practice guidance.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1
        )
        
        message = response.choices[0].message
        messages.append(message)
        
        if message.tool_calls:
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                if hasattr(self, fn_name):
                    fn = getattr(self, fn_name)
                    
                    args_dict = {}
                    if tool_call.function.arguments:
                        try:
                            args_dict = json.loads(tool_call.function.arguments)
                        except Exception as e:
                            logging.error(f"Failed to parse tool arguments: {e}")
                            
                    try:
                        result = fn(**args_dict)
                    except Exception as e:
                        result = {"error": str(e)}
                        
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": fn_name,
                        "content": json.dumps(result)
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": fn_name,
                        "content": "{}"
                    })
        else:
            # If no tools called, we could force a general analysis tool, or just let it respond.
            pass
            
        messages.append({
            "role": "system", 
            "content": "Return the final analysis STRICTLY as a JSON object. The 'summary' must be a professional executive summary with analytical depth (use Markdown for bolding/emphasis). If the user asked for a list, include the detailed list of activities in the summary using Markdown tables. The 'metrics' should be numerical KPIs. The 'insights' should be strategic findings. Schema: {\"summary\": \"...\", \"metrics\": {...}, \"insights\": [...], \"recommendations\": [...]}"
        })
        
        final_response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        content = final_response.choices[0].message.content
        return json.loads(content)

    def _analyze_local(self, query: str) -> Dict[str, Any]:
        analysis_results = self._route_query(query)
        explanation = self._get_ai_explanation(query, analysis_results)
        
        metrics = {}
        insights = []
        recommendations = []
        
        for k, v in analysis_results.items():
            if isinstance(v, dict):
                metrics.update(v.get('metrics', {}))
                insights.append(v.get('summary', ''))
                issues = v.get('issues', [])
                if issues: insights.extend(issues)
                recs = v.get('recommendations', [])
                if recs: recommendations.extend(recs)
                    
        return {
            "summary": explanation,
            "metrics": metrics,
            "insights": insights,
            "recommendations": recommendations
        }
        
    def _fallback_deterministic(self, query: str, error: str) -> Dict[str, Any]:
        res = self._route_query(query)
        metrics = {}
        insights = []
        recommendations = []
        for v in res.values():
             if isinstance(v, dict):
                 metrics.update(v.get('metrics', {}))
                 insights.append(v.get('summary', ''))
                 if v.get('issues'): insights.extend(v['issues'])
                 if v.get('recommendations'): recommendations.extend(v['recommendations'])
        return {
            "summary": f"LLM Integration Failed ({error}). Showing deterministic raw data fallback.",
            "metrics": metrics,
            "insights": insights,
            "recommendations": recommendations
        }

    # ------- DETERMINISTIC FUNCTIONS -------

    def _route_query(self, query: str) -> Dict[str, Any]:
        """Legacy keyword router for local fallback"""
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

        if any(w in query for w in ['discipline', 'wbs', 'by level', 'department', 'area']):
            results['discipline_summary'] = self.get_discipline_summary()

        import re
        activity_match = re.search(r'(?:activity|task)\s+([a-zA-Z0-9\-\_]+|"[^"]+"|\'[^\']+\')', query, re.IGNORECASE)
        if activity_match:
            term = activity_match.group(1).replace('"', '').replace("'", "").strip()
            if term:
                results['search_results'] = self.search_activities(term)

        if not results:
            results['project_health'] = self.get_project_health()
            results['general_info'] = "The user asked a general question. Provide a high-level summary of the schedule's current health and delay standing based on the project_health data."

        return results

    def get_project_health(self) -> Dict[str, Any]:
        if 'project_health' in self._cache: return self._cache['project_health']
        analysis = self.data_store.get_deterministic_analysis()
        summary = analysis.get('projectSummary', {})
        metrics = summary.get('healthMetrics', {})
        
        res = {
            "score": metrics.get('projectHealthScore', 0),
            "status": metrics.get('healthStatus', 'Unknown'),
            "is_constrained": metrics.get('is_constrained', False),
            "delay_days": summary.get('projectDelayDays', 0),
            "issues": metrics.get('qualityIssues', [])
        }
        self._cache['project_health'] = res
        return res

    def calculate_project_delay(self) -> Dict[str, Any]:
        if 'project_delay' in self._cache: return self._cache['project_delay']
        health = self.get_project_health()
        delay_days = health['delay_days']
        
        summary_msg = f"The project finish date has shifted by {delay_days} days."
        if delay_days == 0 and health['is_constrained']:
            summary_msg = "The project finish date is currently fixed (0-day variance), but significant negative float suggests the schedule is constrained and internally delayed."
        elif delay_days == 0:
            summary_msg = "The project is currently on track with 0 days of variance."

        res = {
            "summary": summary_msg,
            "metrics": {
                "projectDelay": delay_days,
                "isConstrained": health['is_constrained']
            },
            "issues": health['issues'],
            "recommendations": ["Investigate hidden constraints preventing finish date movement."] if health['is_constrained'] else []
        }
        self._cache['project_delay'] = res
        return res

    def get_schedule_quality(self) -> Dict[str, Any]:
        if 'schedule_quality' in self._cache: return self._cache['schedule_quality']
        health = self.get_project_health()
        res = {
            "summary": f"Schedule Quality Score: {health['score']}/100 ({health['status']})",
            "metrics": {"score": health['score']},
            "issues": health['issues'],
            "recommendations": ["Fix open-ended logic to improve critical path reliability."] if health['score'] < 80 else []
        }
        self._cache['schedule_quality'] = res
        return res

    def get_critical_path(self) -> Dict[str, Any]:
        if 'critical_path' in self._cache: return self._cache['critical_path']
        analysis = self.data_store.get_deterministic_analysis()
        activity_metrics = analysis.get('activityAnalysis', {})
        
        critical_ids = [tid for tid, obj in activity_metrics.items() if obj.get('is_critical_p6')]
        critical_list = []
        for tid in critical_ids[:20]:  # Top 20 to avoid token bloat
            act = activity_metrics[tid]
            critical_list.append({
                "id": tid,
                "code": act.get('task_code', tid),
                "name": act.get('task_name', 'Unknown'),
                "delay_days": act.get('delay_days', 0),
                "risk_level": "Critical"
            })

        total = len(activity_metrics)
        pct = (len(critical_ids) / total) * 100 if total > 0 else 0

        res = {
            "summary": f"Detected {len(critical_ids)} activities on the critical path.",
            "metrics": {
                "criticalCount": len(critical_ids),
                "criticalPct": f"{pct:.1f}%"
            },
            "data": critical_list,
            "issues": ["Large critical path detected."] if len(critical_ids) > 50 else [],
            "recommendations": ["Monitor prioritized activities for potential bottlenecks."]
        }
        self._cache['critical_path'] = res
        return res

    def get_negative_float_activities(self) -> Dict[str, Any]:
        if 'negative_float' in self._cache: return self._cache['negative_float']
        analysis = self.data_store.get_deterministic_analysis()
        activity_metrics = analysis.get('activityAnalysis', {})
        
        neg_float_ids = [tid for tid, obj in activity_metrics.items() if (obj.get('float_hrs') or 0) < 0]
        # Sort by most negative float
        sorted_ids = sorted(neg_float_ids, key=lambda tid: activity_metrics[tid].get('float_hrs', 0))
        
        risky_list = []
        for tid in sorted_ids[:20]:
            act = activity_metrics[tid]
            flt = act.get('float_hrs', 0)
            level = "Extreme Risk" if flt < -200 else "High Risk" if flt < -100 else "Medium Risk"
            risky_list.append({
                "id": tid,
                "code": act.get('task_code', tid),
                "name": act.get('task_name', 'Unknown'),
                "float_hrs": flt,
                "risk_level": level
            })
            
        res = {
            "summary": f"Found {len(neg_float_ids)} activities with negative float.",
            "metrics": {"negativeFloatCount": len(neg_float_ids)},
            "data": risky_list,
            "issues": ["Negative float indicates the project cannot meet its current constraints."] if neg_float_ids else [],
            "recommendations": ["Verify 'Must Finish By' dates and out-of-sequence progress."] if neg_float_ids else []
        }
        self._cache['negative_float'] = res
        return res

    def check_open_ended_activities(self) -> Dict[str, Any]:
        if 'open_ended' in self._cache: return self._cache['open_ended']
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

        res = {
            "summary": f"Integrity Check: {len(open_starts)} Open Starts, {len(open_finishes)} Open Finishes detected.",
            "metrics": {
                "openStarts": len(open_starts),
                "openFinishes": len(open_finishes)
            },
            "issues": ["Open-ended activities invalidate critical path reliability."] if (open_starts or open_finishes) else [],
            "recommendations": ["Link open-ended activities to appropriate milestones."]
        }
        self._cache['open_ended'] = res
        return res

    def get_delay_drivers(self) -> Dict[str, Any]:
        if 'delay_drivers' in self._cache: return self._cache['delay_drivers']
        analysis = self.data_store.get_deterministic_analysis()
        summary = analysis.get('projectSummary', {})
        drivers = summary.get('topDrivers', [])

        res = {
            "summary": "Top delay drivers identified on the critical path.",
            "metrics": {"impactedDriversCount": len(drivers)},
            "data": drivers,
            "issues": [f"Activity {d['task_code']} is driving {d['delay_days']} days of slippage." for d in drivers],
            "recommendations": [f"Conduct recovery session for {d['task_code']} to recover {d['delay_days']} days." for d in drivers[:3]] + ["Re-baseline project to reflect current performance benchmarks."]
        }
        self._cache['delay_drivers'] = res
        return res

    def get_discipline_summary(self) -> Dict[str, Any]:
        if 'discipline_summary' in self._cache: return self._cache['discipline_summary']
        # target_level=2 provides the most common executive view (Project > Discipline)
        data = self.data_store.get_wbs_summary(target_level=2)
        res = {
            "summary": "Project status aggregated by major discipline (WBS Level 2).",
            "metrics": {"totalDisciplinesShown": len(data)},
            "data": data,
            "issues": [f"{d['discipline']} has active tasks with {d['avg_float']} avg float." for d in data[:5] if d['avg_float'] < 0],
            "recommendations": ["Review disciplines with significant negative float and trace logic dependencies."]
        }
        self._cache['discipline_summary'] = res
        return res

    def search_activities(self, search_term: str) -> Dict[str, Any]:
        """Searches for specific activities by exact or partial name or code."""
        if 'search_activities_' + search_term in self._cache:
            return self._cache['search_activities_' + search_term]
            
        data = self.data_store.get_table_data(table_type="TASK", search=search_term, limit=20)
        records = data.get("records", [])
        
        if not records:
            res = {"summary": f"No activities found matching '{search_term}'.", "data": [], "metrics": {}}
            self._cache['search_activities_' + search_term] = res
            return res
            
        simplified_records = []
        for r in records:
            simplified_records.append({
                "task_code": r.get('task_code', ''),
                "task_name": r.get('task_name', ''),
                "target_start_date": r.get('target_start_date', ''),
                "target_end_date": r.get('target_end_date', ''),
                "act_start_date": r.get('act_start_date', ''),
                "act_end_date": r.get('act_end_date', ''),
                "status": r.get('_analysis', {}).get('status', 'Unknown')
            })
            
        res = {
            "summary": f"Found {len(records)} activities matching '{search_term}'.",
            "metrics": {"matched_activities": len(records)},
            "data": simplified_records,
            "issues": [],
            "recommendations": []
        }
        self._cache['search_activities_' + search_term] = res
        return res

    def _get_ai_explanation(self, query: str, data: Dict[str, Any]) -> str:
        try:
            prompt = f"""
            User Query: {query}
            Structured Analysis: {json.dumps(data, indent=2)}
            
            Instructions:
            1. You are a professional Schedule Analyst (P6 Expert).
            2. Explain the results concisely using the provided JSON. Use the 'data' field to construct detailed Markdown tables if requested or relevant.
            3. DO NOT perform any math. Simply interpret the 'metrics', 'data', 'issues', and 'recommendations'.
            4. Use clear Markdown headings and bullet points.
            5. ONLY answer what is relevant to the user's specific query. Do not summarize general project health unless it was specifically asked or is the only data provided.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Explain schedule analysis results as an expert analyst. No code. No math."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Analysis complete. Raw JSON: {json.dumps(data, indent=2)}"
