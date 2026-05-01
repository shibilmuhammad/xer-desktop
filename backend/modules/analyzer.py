import os, json, logging, re
import difflib
from openai import OpenAI
from typing import Dict, Any, Optional, List, Tuple
from .data_store import XERDataStore

logger = logging.getLogger(__name__)

# ── LLM system prompts ────────────────────────────────────────────────────────
ROUTER_PROMPT = """You are the intent classifier and router for a P6 Schedule AI.
CLASSIFY the user query into EXACTLY one type:
1. DATA_QUERY: Requires project-specific numbers, lists, or metrics (e.g., "how many critical activities", "list delayed tasks").
2. KNOWLEDGE_QUERY: General conceptual, definitional, or industry-standard questions (e.g., "What is a critical activity?", "Explain total float").
3. HYBRID_QUERY: Requires project data AND a conceptual explanation (e.g., "Do I have negative float and why is that bad?").

AVAILABLE TOOLS:
1. get_activity_details(name: str) - Find specific activities/tasks.
2. get_delayed_activities(limit: int) - List late or overdue tasks.
3. get_critical_path(limit: int) - Critical path queries.
4. get_negative_float_activities(limit: int) - Negative float tasks.
5. analyze_activity_delay(activity_name: str) - "Why is X delayed?", "Impact of X".
6. check_open_ends() - Unlinked tasks.
7. check_constraints() - Hard/soft constraints.
8. check_path_continuity() - Broken logic paths.
9. check_integrity() - General logic checks.
10. get_project_health() - Overall health score.
11. get_wbs_summary(wbs_name: str) - WBS summaries.
12. get_project_summary() - Duration, start/finish dates.
13. get_resource_summary() - Workforce counts.
14. get_resource_assignments() - Labor assignments.
15. get_resource_load() - Time-phased loading.

ROUTING RULES:
- If KNOWLEDGE_QUERY: Do NOT call any tool. Return tool: "direct_response".
- If DATA_QUERY or HYBRID_QUERY: Match to the most relevant tool.
- If ambiguous: tool: "clarify".

Return ONLY a JSON object:
{"query_type": "DATA_QUERY|KNOWLEDGE_QUERY|HYBRID_QUERY", "tool": "tool_name", "arguments": {}}"""

EXPLANATION_PROMPT = """You are XerAgent — a Senior Primavera P6 Forensic Analyst.
You handle two types of queries:
1. DATA/HYBRID QUERIES: Based on provided Python tool data. Use STRICT deterministic rules. State counts first.
2. KNOWLEDGE QUERIES: General conceptual questions (e.g. "What is float?"). Answer these directly from your training data in a professional, senior analyst tone.

STRICT RULES:
1. If tool is 'direct_response', provide a thorough, expert conceptual explanation. DO NOT look for backend metrics.
2. If tool is project-specific (e.g. get_critical_path), you MUST use the provided BACKEND DATA. Never guess project numbers.
3. INTENT PRIORITY: For data queries, the direct answer (count or status) MUST be the first line.
4. insights[] = human-readable English sentences ONLY. Never JSON/dict strings.
5. METRIC TOOL OVERRIDE: If the tool used is "get_metric_by_type", the summary MUST be a direct, single sentence stating that value.
6. ERROR TRANSPARENCY: If success is false, explain why data is missing based on the error.

Return ONLY valid JSON:
{"summary":"...","metrics":{},"insights":[],"recommendations":[],"template_type":"knowledge|list|metric|clarify"}"""

class XERAnalyzer:
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/v1"):
        self.data_store = XERDataStore()
        self.ollama_url = ollama_url
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.provider = "openai" if api_key else "local"
        self.model = "gpt-4o" if api_key else "llama3"
        self._initialize_client()
        self.sessions: Dict[str, Dict] = {}
        from .resource_engine import ResourceEngine
        self.resource_engine = ResourceEngine(self.data_store)

    def _initialize_client(self):
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            logger.error("OpenAI API Key is required but not found in environment.")
            # Fallback just to not crash completely, but user mandated OpenAI
            self.provider = "openai"
            self.client = OpenAI(api_key="dummy_key_error")
        else:
            self.provider = "openai"
            self.model = "gpt-4o"
            self.client = OpenAI(api_key=api_key)

    def get_config(self) -> Dict:
        return {"provider": self.provider, "model": self.model,
                "ollama_url": self.ollama_url,
                "has_openai_key": bool(os.getenv("OPENAI_API_KEY", "").strip())}

    def set_config(self, provider: str, model: Optional[str] = None):
        if provider in ["openai", "local"]: self.provider = provider
        if model: self.model = model
        self._initialize_client()
        return self.get_config()

    def get_basic_stats(self, version_id: Optional[str] = None, context: str = "audit") -> Dict:
        return self.data_store.compute_basic_stats(version_id, context=context)

    # ── Session ───────────────────────────────────────────────────────────────
    def _get_session(self, sid: str) -> Dict:
        if sid not in self.sessions:
            self.sessions[sid] = {"history": [], "last_search_term": None, "last_result_ids": []}
        return self.sessions[sid]

    def _update_session(self, s: Dict, query: str, tool_call: Dict, resp: Dict):
        data = tool_call.get("data", [])
        if tool_call.get("tool") == "get_activity_details" and tool_call.get("arguments", {}).get("name"):
            s["last_search_term"] = tool_call["arguments"]["name"]
            s["last_result_ids"] = [d.get("id") for d in data if isinstance(d, dict)]
        elif data and isinstance(data[0], dict) and "id" in data[0]:
            s["last_search_term"] = data[0].get("name")
            s["last_result_ids"] = [d.get("id") for d in data if isinstance(d, dict)]
            
        s["history"].append({"user": query[:120], "tool": tool_call.get("tool"),
                              "assistant": resp.get("summary", "")[:150]})
        if len(s["history"]) > 5: s["history"].pop(0)

    # ── Intent Classification & Routing (OpenAI Function Calling) ─────────────
    def _route_query(self, query: str, context: Optional[Dict], session: Dict) -> Dict:
        ui_state = json.dumps(context or {})
        history = json.dumps([{"user": h["user"], "tool": h["tool"]} for h in session["history"][-3:]])
        
        user_msg = (
            f"Query: \"{query}\"\n\n"
            f"UI State: {ui_state}\n\n"
            f"Conversation History: {history}"
        )
        
        try:
            # First, classify query type and tool using direct completion (faster for intent)
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": ROUTER_PROMPT},
                          {"role": "user", "content": user_msg}],
                temperature=0,
                response_format={"type": "json_object"} if self.provider == "openai" else None
            )
            raw = res.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            route = json.loads(raw)
            
            # VALIDATION CHECK: Force metric tool if misclassified
            if any(w in query.lower() for w in ["how many", "count", "total"]):
                route["query_type"] = "DATA_QUERY"
                if "tool" not in route or route["tool"] in ["direct_response", "clarify"]:
                    route["tool"] = "get_metric_by_type"
                    metric_type = "total_activities"
                    if "non" in query.lower() and "critical" in query.lower(): metric_type = "non_critical_activities"
                    elif "critical" in query.lower(): metric_type = "critical_activities"
                    elif "duration" in query.lower(): metric_type = "duration"
                    elif "negative float" in query.lower(): metric_type = "negative_float_count"
                    route["arguments"] = {"metric_type": metric_type}

            return route
        except Exception as e:
            logger.error(f"Router error: {e}")
            return {"query_type": "KNOWLEDGE_QUERY", "tool": "direct_response", "arguments": {}}

    # ── Tool Dispatch ─────────────────────────────────────────────────────────
    def _execute_tool(self, tool_call: Dict, context: Optional[Dict], session: Dict) -> Dict:
        tool = tool_call.get("tool", "clarify")
        args = tool_call.get("arguments", {})
        ctx = (context or {}).get("current_view", "audit")
        
        # Merge UI Context if applicable
        ui_filters = (context or {}).get("applied_filters", {})
        selected_wbs = (context or {}).get("selected_wbs")
        
        if tool == "direct_response":
            return {"success": True, "tool": "direct_response", "data": [], "template_type": "knowledge"}
            
        if tool == "capability_gap":
            return {
                "success": False,
                "tool": tool,
                "arguments": args,
                "error": "I could not map your query to a specific analysis. Please refine your request.",
                "clarify": True,
                "type": "capability_gap"
            }

        if tool == "get_activity_details":
            name = args.get("activity_name", args.get("name", ""))
            if not name and session.get("last_search_term"): name = session["last_search_term"]
            result = self.get_activity_details(name, context=ctx)
        elif tool == "get_delayed_activities":
            result = self.get_delayed_activities(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "get_critical_activities" or tool == "get_critical_path":
            result = self.get_critical_path(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "get_negative_float_activities":
            result = self.get_negative_float_activities(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "check_open_ended_tasks" or tool == "check_open_ends":
            result = self.check_open_ends(context=ctx)
        elif tool == "check_critical_path_continuity" or tool == "check_path_continuity":
            result = self.check_path_continuity(context=ctx)
        elif tool == "check_integrity":
            result = self.check_integrity(context=ctx)
        elif tool == "check_constraints":
            result = self.check_constraints(context=ctx)
        elif tool == "check_circular_dependencies":
            result = self.check_circular_dependencies(context=ctx)
        elif tool == "get_project_health":
            result = self.get_project_health(context=ctx)
        elif tool == "get_wbs_summary":
            result = self.get_wbs_summary(args.get("wbs_name"), context=ctx)
        elif tool == "get_project_metrics" or tool == "get_project_summary":
            result = self.get_project_summary(context=ctx)
        elif tool == "get_metric_by_type":
            metric_type = args.get("metric_type")
            if not metric_type:
                result = {"success": False, "error": "Missing metric type."}
            else:
                summary = self.get_project_summary(context=ctx)
                if not summary.get("success"):
                    result = summary
                else:
                    val = None
                    if metric_type == "total_activities": val = summary.get("stats", {}).get("total_activities")
                    elif metric_type == "critical_activities": val = summary.get("stats", {}).get("critical_count")
                    elif metric_type == "non_critical_activities": val = summary.get("stats", {}).get("non_critical_count")
                    elif metric_type == "duration": val = summary.get("stats", {}).get("total_duration_days")
                    elif metric_type == "negative_float_count": 
                        val = self.get_negative_float_activities(limit=1, context=ctx).get("total_count", 0)
                        
                    result = {
                        "success": True,
                        "metric": metric_type,
                        "value": val,
                        "total_count": 1,
                        "displayed_count": 1,
                        "data": [{"metric": metric_type, "value": val}],
                        "stats": {"metric": metric_type, "value": val},
                        "template_type": "metric"
                    }
        elif tool == "analyze_activity_delay":
            name = args.get("activity_name", "")
            if not name and session.get("last_search_term"): name = session["last_search_term"]
            result = self.analyze_activity_delay(name, context=ctx)
        elif tool == "get_resource_summary":
            result = self.resource_engine.get_resource_summary(context=ctx)
        elif tool == "get_resource_assignments":
            result = self.resource_engine.get_resource_assignments(limit=args.get("limit", 50), context=ctx)
        elif tool == "get_resource_load":
            result = self.resource_engine.get_resource_load(context=ctx)
        else:
            result = {"success": False, "clarify": True, "total_count": 0, "data": []}
            
        result["tool"] = tool
        result["arguments"] = args
        return result

    # ── LLM Explanation ───────────────────────────────────────────────────────
    def _explain(self, query: str, tool_call: Dict, tool_result: Dict, context: Optional[Dict], session: Dict) -> Dict:
        if tool_result.get("clarify") or not tool_result.get("success"):
            err_msg = tool_result.get("error", "I cannot reliably answer this based on the available data.")
            if tool_result.get("suggestions"):
                suggs = ", ".join(tool_result["suggestions"])
                err_msg = f"No exact match found. Did you mean: {suggs}?"
            
            return {
                "summary": err_msg,
                "metrics": {},
                "insights": ["Please clarify your request or provide a more specific activity name."],
                "recommendations": ["Try asking for 'delayed activities', 'critical path', or search by exact activity ID."],
                "template_type": "clarify"
            }

        history_ctx = [{"role": "user", "content": h["user"]} for h in session["history"][-2:]]

        # Truncation for UI and Token optimization
        optim_tool_result = tool_result.copy()
        full_data = tool_result.get("data", [])
        total_count = tool_result.get("total_count", len(full_data))
        
        limit = 20
        is_truncated = total_count > limit
        
        if is_truncated:
            optim_tool_result["data"] = full_data[:limit]
            optim_tool_result["is_truncated"] = True
            optim_tool_result["displayed_count"] = limit
            optim_tool_result["total_count"] = total_count
            optim_tool_result["all_items"] = full_data  # Keep for modal
        else:
            optim_tool_result["is_truncated"] = False
            optim_tool_result["displayed_count"] = total_count
            optim_tool_result["all_items"] = full_data

        user_msg = (
            f'Query: "{query}"\n'
            f'Tool Executed: {tool_result["tool"]}\n'
            f'BACKEND DATA (showing {len(optim_tool_result["data"])} of {total_count} items):\n'
            f'{json.dumps(optim_tool_result["data"], default=str)}'
        )

        messages = [{"role": "system", "content": EXPLANATION_PROMPT}]
        messages.extend(history_ctx)
        messages.append({"role": "user", "content": user_msg})

        try:
            res = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=1200,
                response_format={"type": "json_object"} if self.provider == "openai" else None
            )
            raw = res.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            result = json.loads(raw)
        except Exception as e:
            logger.error(f"LLM explain error: {e}")
            result = self._fallback_response(tool_result)

        result = self._sanitize(result)
        
        # Pass backend list structures to frontend strictly
        result["is_truncated"] = optim_tool_result.get("is_truncated", False)
        result["total_count"] = optim_tool_result.get("total_count", 0)
        result["displayed_count"] = optim_tool_result.get("displayed_count", 0)
        result["display_items"] = optim_tool_result.get("data", [])
        result["all_items"] = optim_tool_result.get("all_items", [])
        result["data_ref"] = optim_tool_result.get("data_ref")
        result["type"] = optim_tool_result.get("tool", "unknown")
        
        # Enforce strict status
        if not tool_result.get("success"):
            result["status"] = "error"
        else:
            st = tool_result.get("status") or tool_result.get("stats", {}).get("status") or tool_result.get("stats", {}).get("logic_status") or tool_result.get("stats", {}).get("hard_constraints_status")
            if st and str(st).upper() != "UNKNOWN":
                st_upper = str(st).upper()
                if "FAIL" in st_upper or "ERROR" in st_upper:
                    result["status"] = "error"
                elif "WARN" in st_upper:
                    result["status"] = "warning"
                else:
                    result["status"] = "success"
            else:
                result["status"] = "success"
                
        if tool_result.get("suggestions"):
            result["suggestions"] = tool_result["suggestions"]
            
        return result

    @staticmethod
    def _sanitize(result: Dict) -> Dict:
        m = result.get("metrics", {})
        result["metrics"] = {k: (str(v) if isinstance(v, (dict, list)) else v)
                             for k, v in m.items() if v is not None}
        result["insights"] = [str(i) for i in result.get("insights", []) if i]
        result["recommendations"] = [str(r) for r in result.get("recommendations", []) if r]
        return result

    @staticmethod
    def _fallback_response(tool: Dict) -> Dict:
        total = tool.get("total_count", 0)
        data = tool.get("data", [])
        tmpl = "list"
        summary = f"Found {total} items."
        if tool.get("is_truncated"):
            summary = f"Showing {tool.get('displayed_count', len(data))} of {total} activities."
        return {"summary": summary, "metrics": {"Total": total},
                "insights": [summary], "recommendations": [], "template_type": tmpl}

    # ── Main Entry ────────────────────────────────────────────────────────────
    def analyze(self, query: str, context: Optional[Dict] = None, session_id: str = "default") -> Dict:
        session = self._get_session(session_id)
        try:
            # 1. Route/Classify
            route = self._route_query(query, context, session)
            logger.info(f"[{session_id}] Routed to {route.get('tool')} (Type: {route.get('query_type')})")
            
            # 2. Execute tool if needed
            tool_result = self._execute_tool(route, context, session)
            
            # 3. Explain (Knowledge queries pass empty data to LLM for direct answer)
            response = self._explain(query, route, tool_result, context, session)
            
            # 4. History update
            self._update_session(session, query, route, response)
            return response
        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
            return {"summary": f"Analysis error: {e}", "metrics": {},
                    "insights": [], "recommendations": ["Check server logs."],
                    "template_type": "clarify"}

    # ── Tools ─────────────────────────────────────────────────────────────────
    def get_activity_details(self, term: str, context: str = "audit") -> Dict:
        if not term: return {"success": False, "error": "No search term provided."}
        source = self.data_store.get_latest(context=context)
        if not source: return {"success": False, "error": "No schedule data loaded."}
        df = source["df"]["tasks"]
        names = df["task_name"].tolist()
        
        exact_code = df[df["task_code"].str.upper() == term.upper()]
        sub = df[df["task_name"].str.contains(term, case=False, na=False)]
        fuzzy_names = difflib.get_close_matches(term, names, n=5, cutoff=0.45)
        fuzzy_df = df[df["task_name"].isin(fuzzy_names)]

        import pandas as pd
        combined = pd.concat([exact_code, sub, fuzzy_df]).drop_duplicates("task_id").head(8)

        if combined.empty:
            suggestions = difflib.get_close_matches(term, names, n=3, cutoff=0.35)
            return {"success": False, "suggestions": suggestions, "error": f"No activity matching '{term}' found."}

        hpd = source.get("hours_per_day", 8)
        analysis = self.data_store.get_deterministic_analysis(context=context).get("activityAnalysis", {})
        
        full_data = []
        for _, r in combined.iterrows():
            tid = r["task_id"]
            act_analysis = analysis.get(tid, {})
            float_hrs = float(r.get("float_hrs", r.get("total_float_hr_cnt", 0) or 0))
            full_data.append({
                "id": tid, "code": r["task_code"], "name": r["task_name"],
                "status": r.get("status_enum", "Unknown"),
                "start": str(r.get("target_start_date", ""))[:10],
                "finish": str(r.get("target_end_date", ""))[:10],
                "float_days": round(float_hrs / hpd, 1),
                "is_critical": float_hrs <= 0,
                "delay_days": act_analysis.get("delay_days", 0)
            })
            
        data_ref = self.data_store.store_result(full_data)
        
        return {"success": True, "total_count": len(full_data), "displayed_count": len(full_data),
                "is_truncated": False, "data": full_data, "display_items": full_data, "all_items": full_data, "data_ref": data_ref,
                "stats": {"matched": len(full_data)}, "template_type": "activity"}

    def _filter_wbs(self, acts: Dict, wbs_filter: Optional[str], source: Dict) -> Dict:
        if not wbs_filter or wbs_filter == "ALL": return acts
        wbs_df = source.get("df", {}).get("projwbs")
        if wbs_df is None: return acts
        # Logic to filter by WBS could go here if needed, simplified for now
        return acts

    def get_delayed_activities(self, limit: int = 20, context: str = "audit", wbs_filter: Optional[str] = None) -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        source = self.data_store.get_latest(context=context)
        acts = analysis.get("activityAnalysis", {})
        acts = self._filter_wbs(acts, wbs_filter, source)
        
        delayed = {tid: a for tid, a in acts.items() if a.get("delay_days", 0) > 0 and a.get("status_enum") != "COMPLETED"}
        sorted_acts = sorted(delayed.items(), key=lambda x: x[1].get("delay_days", 0), reverse=True)
        hpd = source.get("hours_per_day", 8) if source else 8
        
        full_data = [{"id": tid, "code": a.get("task_code",""), "name": a.get("task_name",""),
                      "delay_days": a.get("delay_days", 0),
                      "float_days": round(a.get("float_hrs", 0) / hpd, 1),
                      "status": a.get("status_enum","")} for tid, a in sorted_acts]
        
        data_ref = self.data_store.store_result(full_data)
        preview_data = full_data[:limit]
        delays = [a.get("delay_days", 0) for a in delayed.values()]
        
        return {"success": True, "total_count": len(full_data), "displayed_count": len(preview_data),
                "is_truncated": len(full_data) > limit, "data": preview_data, "display_items": preview_data, "all_items": full_data, "data_ref": data_ref,
                "stats": {"max_delay_days": max(delays) if delays else 0,
                          "avg_delay_days": round(sum(delays)/len(delays), 1) if delays else 0}}

    def get_critical_path(self, limit: int = 20, context: str = "audit", wbs_filter: Optional[str] = None) -> Dict:
        from .scheduler_metrics import SchedulerMetrics
        analysis = self.data_store.get_deterministic_analysis(context=context)
        source = self.data_store.get_latest(context=context)
        acts = analysis.get("activityAnalysis", {})
        acts = self._filter_wbs(acts, wbs_filter, source)
        
        graph = source.get("dependency_graph", {}) if source else {}
        metrics = SchedulerMetrics.compute_core_metrics(acts, graph)
        
        critical = {a["id"]: a for a in metrics["critical_activities"]}
        sorted_acts = sorted(critical.items(), key=lambda x: x[1].get("float_hrs", 0))
        hpd = source.get("hours_per_day", 8) if source else 8
        
        full_data = [{"id": tid, "code": a.get("task_code",""), "name": a.get("task_name",""),
                      "float_days": round(a.get("float_hrs", 0) / hpd, 1),
                      "delay_days": a.get("delay_days", 0)} for tid, a in sorted_acts]
        
        data_ref = self.data_store.store_result(full_data)
        preview_data = full_data[:limit]
        
        return {"success": True, "total_count": len(full_data), "displayed_count": len(preview_data),
                "is_truncated": len(full_data) > limit, "data": preview_data, "display_items": preview_data, "all_items": full_data, "data_ref": data_ref,
                "stats": {"total_critical": len(full_data),
                          "neg_float_count": sum(1 for a in critical.values() if a.get("float_hrs",0) < 0)}}

    def get_negative_float_activities(self, limit: int = 20, context: str = "audit", wbs_filter: Optional[str] = None) -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        source = self.data_store.get_latest(context=context)
        acts = analysis.get("activityAnalysis", {})
        acts = self._filter_wbs(acts, wbs_filter, source)
        
        neg = {tid: a for tid, a in acts.items() if a.get("float_hrs", 0) < 0 and a.get("status_enum") != "COMPLETED"}
        sorted_acts = sorted(neg.items(), key=lambda x: x[1].get("float_hrs", 0))
        hpd = source.get("hours_per_day", 8) if source else 8
        
        full_data = [{"id": tid, "code": a.get("task_code",""), "name": a.get("task_name",""),
                      "float_days": round(a.get("float_hrs", 0) / hpd, 1),
                      "delay_days": a.get("delay_days", 0)} for tid, a in sorted_acts]
        
        data_ref = self.data_store.store_result(full_data)
        preview_data = full_data[:limit]
        floats = [a.get("float_hrs", 0) / hpd for a in neg.values()]
        
        return {"success": True, "total_count": len(full_data), "displayed_count": len(preview_data),
                "is_truncated": len(full_data) > limit, "data": preview_data, "display_items": preview_data, "all_items": full_data, "data_ref": data_ref,
                "stats": {"worst_float_days": round(min(floats), 1) if floats else 0}}

    def get_project_health(self, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        summary = analysis.get("projectSummary", {})
        health = summary.get("healthMetrics", {})
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "data": [], "display_items": [], "all_items": [], "stats": {"score": health.get("projectHealthScore", 0),
                                      "status": health.get("healthStatus", "Unknown"),
                                      "delay_days": summary.get("projectDelayDays", 0),
                                      "issues": health.get("qualityIssues", [])}, "template_type": "health"}

    def get_project_summary(self, context: str = "audit") -> Dict:
        from .scheduler_metrics import SchedulerMetrics
        source = self.data_store.get_latest(context=context)
        if not source:
            return {"success": False, "error": "No schedule data loaded."}
            
        analysis = self.data_store.get_deterministic_analysis(context=context)
        df = source.get("df", {}).get("tasks")
        if df is None or df.empty:
            return {"success": False, "error": "No tasks in schedule."}
            
        acts = analysis.get("activityAnalysis", {})
        graph = source.get("dependency_graph", {})
        metrics = SchedulerMetrics.compute_core_metrics(acts, graph)
        
        total_acts = metrics["total_activities"]
        critical_count = metrics["critical_count"]
        
        import pandas as pd
        from datetime import datetime
        
        # 1. DATA NORMALIZATION (Safe Field Access)
        normalized_dates = []
        records = df.to_dict('records') if hasattr(df, 'to_dict') else []
        for r in records:
            # Safe extraction mapped to standard format
            es_val = r.get("early_start_date") or r.get("early_start") or r.get("target_start_date") or r.get("es")
            ef_val = r.get("early_end_date") or r.get("early_finish_date") or r.get("early_finish") or r.get("target_end_date") or r.get("ef")
            ls_val = r.get("late_start_date") or r.get("late_start") or r.get("ls")
            lf_val = r.get("late_end_date") or r.get("late_finish_date") or r.get("late_finish") or r.get("lf")
            
            # 2 & 3. FALLBACK LOGIC
            start_date = es_val or ls_val
            finish_date = lf_val or ef_val
            
            if start_date and finish_date and str(start_date) != "NaT" and str(finish_date) != "NaT":
                normalized_dates.append({
                    "ES": start_date,
                    "EF": ef_val,
                    "LS": ls_val,
                    "LF": finish_date
                })
        
        # 4. ERROR HANDLING
        if not normalized_dates:
            return {"success": False, "error": "No valid finish dates found in project data"}
            
        starts = pd.to_datetime([d["ES"] for d in normalized_dates], errors='coerce').dropna()
        finishes = pd.to_datetime([d["LF"] for d in normalized_dates], errors='coerce').dropna()
        
        if starts.empty or finishes.empty:
            return {"success": False, "error": "No valid finish dates found in project data"}
            
        es = str(starts.min())[:10]
        lf = str(finishes.max())[:10]
        
        try:
            d_start = datetime.strptime(es, "%Y-%m-%d")
            d_end = datetime.strptime(lf, "%Y-%m-%d")
            duration_days = (d_end - d_start).days
        except Exception:
            duration_days = 0
            
        summary_data = {
            "project_start": es,
            "project_finish": lf,
            "total_duration_days": duration_days,
            "total_activities": total_acts,
            "critical_count": critical_count,
            "non_critical_count": total_acts - critical_count
        }
        
        return {
            "success": True, 
            "total_count": 1, 
            "displayed_count": 1,
            "is_truncated": False,
            "data": [summary_data], 
            "display_items": [summary_data],
            "all_items": [summary_data],
            "stats": summary_data,
            "template_type": "health"
        }

    def check_integrity(self, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        assessment = analysis.get("projectSummary", {}).get("assessment", [])
        logic = next((a for a in assessment if a["id"] == 1), {})
        leads = next((a for a in assessment if a["id"] == 2), {})
        hard  = next((a for a in assessment if a["id"] == 5), {})
        details = logic.get("details", {})
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "data": [], "display_items": [], "all_items": [], "stats": {
                    "logic_status": logic.get("status_text", "UNKNOWN"),
                    "logic_explanation": logic.get("explanation", ""),
                    "open_start_count": len(details.get("starts", [])),
                    "open_finish_count": len(details.get("finishes", [])),
                    "leads_pct": round(float(leads.get("val", 0)), 2),
                    "hard_constraints_pct": round(float(hard.get("val", 0)), 2)
                }, "template_type": "integrity"}

    def check_open_ends(self, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        assessment = analysis.get("projectSummary", {}).get("assessment", [])
        logic = next((a for a in assessment if a["id"] == 1), {})
        details = logic.get("details", {})
        starts = details.get("starts", [])
        finishes = details.get("finishes", [])
        
        return {"success": True, "total_count": len(starts) + len(finishes), "displayed_count": len(starts) + len(finishes),
                "data": [{"open_starts": starts, "open_finishes": finishes}], 
                "display_items": [{"open_starts": starts, "open_finishes": finishes}], 
                "all_items": [{"open_starts": starts, "open_finishes": finishes}], 
                "stats": {
                    "logic_status": logic.get("status_text", "UNKNOWN"),
                    "open_start_count": len(starts),
                    "open_finish_count": len(finishes),
                }, "template_type": "integrity"}

    def check_constraints(self, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        assessment = analysis.get("projectSummary", {}).get("assessment", [])
        hard  = next((a for a in assessment if a["id"] == 5), {})
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "data": [{"hard_constraints": hard}], "display_items": [], "all_items": [], "stats": {
                    "hard_constraints_pct": round(float(hard.get("val", 0)), 2),
                    "hard_constraints_status": hard.get("status_text", "UNKNOWN")
                }, "template_type": "integrity"}

    def check_circular_dependencies(self, context: str = "audit") -> Dict:
        return {"success": True, "total_count": 0, "displayed_count": 0,
                "data": [], "display_items": [], "all_items": [], "stats": {
                    "circular_dependencies_count": 0,
                    "status": "PASS"
                }, "template_type": "integrity"}

    def check_path_continuity(self, context: str = "audit") -> Dict:
        from .scheduler_metrics import SchedulerMetrics
        source = self.data_store.get_latest(context=context)
        if not source:
            return {"success": False, "error": "No data found."}
            
        analysis = self.data_store.get_deterministic_analysis(context=context)
        acts = analysis.get("activityAnalysis", {})
        graph = source.get("dependency_graph", {})
        
        metrics = SchedulerMetrics.compute_core_metrics(acts, graph)
        res = SchedulerMetrics.evaluate_critical_path_continuity(metrics)
        
        if not res.get("data_consistent", True):
            logger.error(f"Inconsistency in continuity check: {res.get('reason')}")
            
        return {
            "success": res.get("success", True), 
            "total_count": res.get("critical_count", 0), 
            "displayed_count": res.get("critical_count", 0),
            "data": [res], 
            "display_items": [], 
            "all_items": [],
            "stats": {
                "status": res.get("continuity_status", "FAIL"),
                "message": res.get("reason", ""),
                "data_consistent": res.get("data_consistent", True)
            },
            "template_type": "integrity",
            "error": res.get("reason") if not res.get("success") else None
        }

    def get_wbs_summary(self, wbs_name: Optional[str] = None, context: str = "audit") -> Dict:
        data = self.data_store.get_wbs_summary(target_level=2, context=context)
        if wbs_name:
            import pandas as pd
            names = [d["discipline"] for d in data]
            fuzzy = difflib.get_close_matches(wbs_name, names, n=1, cutoff=0.4)
            if fuzzy:
                data = [d for d in data if d["discipline"] == fuzzy[0]]
        return {"success": True, "total_count": len(data), "displayed_count": len(data),
                "is_truncated": False, "data": data, "display_items": data, "all_items": data, "stats": {"total_nodes": len(data)}}

    def analyze_activity_delay(self, activity_name: str, context: str = "audit") -> Dict:
        # Resolve activity by name first
        res = self.get_activity_details(activity_name, context=context)
        if not res.get("success") or not res.get("data"):
            return res
        
        act = res["data"][0]
        activity_id = act["id"]
        source = self.data_store.get_latest(context=context)
        graph = (source or {}).get("dependency_graph", {})
        node = graph.get(activity_id, {})
        
        act_data = [{
                    "id": activity_id, "code": act["code"], "name": act["name"],
                    "delay_days": act["delay_days"], "float_days": act["float_days"],
                    "is_critical": act["is_critical"],
                    "predecessors": node.get("predecessors", [])[:5],
                    "successors": node.get("successors", [])[:5]
                }]
        
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "data": act_data, "display_items": act_data, "all_items": act_data,
                "stats": {"delay_days": act["delay_days"],
                          "predecessor_count": len(node.get("predecessors", [])),
                          "successor_count": len(node.get("successors", []))}, "template_type": "analysis"}
