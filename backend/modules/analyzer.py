import os, json, logging, re
import difflib
from openai import OpenAI
from typing import Dict, Any, Optional, List, Tuple
from .data_store import XERDataStore

logger = logging.getLogger(__name__)

# ── Intent constants ──────────────────────────────────────────────────────────
INTENT_ACTIVITY_SEARCH = "ACTIVITY_SEARCH"
INTENT_LIST_DELAYED    = "LIST_DELAYED"
INTENT_LIST_CRITICAL   = "LIST_CRITICAL"
INTENT_LIST_NEG_FLOAT  = "LIST_NEG_FLOAT"
INTENT_ANALYTICAL      = "ANALYTICAL"
INTENT_INTEGRITY       = "INTEGRITY"
INTENT_HEALTH          = "HEALTH"
INTENT_WBS             = "WBS_SUMMARY"
INTENT_CLARIFY         = "CLARIFY"

# ── Pass-1 deterministic patterns ─────────────────────────────────────────────
_P1: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bneg(?:ative)?\s*float\b|\bneg(?:ative)?\s*slack\b", re.I), INTENT_LIST_NEG_FLOAT),
    (re.compile(r"\bcritical\s+path\b|\blongest\s+path\b", re.I),              INTENT_LIST_CRITICAL),
    (re.compile(r"\bcritical\s+activit|\bcritical\s+task", re.I),              INTENT_LIST_CRITICAL),
    (re.compile(r"\bdelay(?:ed)?\b|\bbehind\b|\blate\s+task|\boverdue\b|\bslippage\b", re.I), INTENT_LIST_DELAYED),
    (re.compile(r"\bopen\s+(?:start|end|finish)s?\b|\bopen\s+ends?\b", re.I), INTENT_INTEGRITY),
    (re.compile(r"\b(?:schedule\s+)?(?:logic|integrity|sequence)\b", re.I),    INTENT_INTEGRITY),
    (re.compile(r"\bpredecessor\b|\bsuccessor\b|\bconstraint\b", re.I),        INTENT_INTEGRITY),
    (re.compile(r"\bwbs\b|\bdiscipline\b|\bbreakdown\b|\bzone\b", re.I),       INTENT_WBS),
    (re.compile(r"\boverall\s+health\b|\bproject\s+status\b|\boverview\b", re.I), INTENT_HEALTH),
    (re.compile(r"\b(?:can\s+i|if\s+i)\s+delay\b|\bfloat\s+impact\b", re.I), INTENT_ANALYTICAL),
]

# ── LLM system prompt ─────────────────────────────────────────────────────────
EXPLANATION_PROMPT = """You are XerAgent — a Senior Primavera P6 Forensic Analyst. EXPLANATION ONLY.
The Python backend has done ALL calculations. Never recalculate, estimate, or guess values.

STRICT RULES:
1. insights[] = human-readable English sentences ONLY. Never JSON/dict strings.
   BAD:  "{'task': 'X', 'delay': 5}"
   GOOD: "Activity X is 5 days delayed and sits on the critical path, directly threatening project completion."
2. Each insight: "[Finding]. [What it means]. [Why it matters or action needed]."
3. metrics{} values = strings or plain numbers ONLY. Never objects or arrays.
4. If is_truncated=true, first sentence of summary MUST be: "Showing [displayed_count] of [total_count] activities."
5. For search suggestions: state "Did you mean: [X], [Y]?" prominently.
6. For integrity: include activity names + PASS/WARNING/FAIL + impact explanation.
7. summary uses Markdown tables when listing multiple activities.
8. template_type: "list" | "activity" | "integrity" | "analysis" | "health" | "clarify"

Return ONLY valid JSON (no fences):
{"summary":"...","metrics":{"Label":value},"insights":["sentence."],"recommendations":["action."],"template_type":"..."}"""

PASS2_PROMPT = """Classify this P6 schedule query into ONE type:
LIST_DELAYED, LIST_CRITICAL, LIST_NEG_FLOAT, ACTIVITY_SEARCH, ANALYTICAL, INTEGRITY, HEALTH, WBS_SUMMARY, CLARIFY

Query: "{query}"
Last focus: {focus}
Context: {context}

Return JSON: {{"type":"...","term":"activity name if ACTIVITY_SEARCH else null"}}"""


class XERAnalyzer:
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/v1"):
        self.data_store = XERDataStore()
        self.ollama_url = ollama_url
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.provider = "openai" if api_key else "local"
        self.model = "gpt-4o" if api_key else "llama3"
        self._initialize_client()
        self.sessions: Dict[str, Dict] = {}

    def _initialize_client(self):
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if self.provider == "openai" and api_key:
            self.client = OpenAI(api_key=api_key)
            if self.model == "llama3": self.model = "gpt-4o"
        else:
            self.provider = "local"
            self.client = OpenAI(base_url=self.ollama_url, api_key="ollama")
            if self.model == "gpt-4o": self.model = "llama3"

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
            self.sessions[sid] = {"history": [], "focus_id": None,
                                  "last_search_term": None, "last_result_ids": [],
                                  "last_intent": None}
        return self.sessions[sid]

    def _update_session(self, s: Dict, query: str, intent: Dict, tool: Dict, resp: Dict):
        s["last_intent"] = intent["type"]
        data = tool.get("data", [])
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            s["focus_id"] = data[0].get("id")
        if intent["type"] == INTENT_ACTIVITY_SEARCH and intent.get("term"):
            s["last_search_term"] = intent["term"]
            s["last_result_ids"] = [d.get("id") for d in data if isinstance(d, dict)]
        s["history"].append({"q": query[:120], "intent": intent["type"],
                              "snippet": resp.get("summary", "")[:150]})
        if len(s["history"]) > 5: s["history"].pop(0)

    # ── Intent Classification ─────────────────────────────────────────────────
    def _resolve_references(self, query: str, session: Dict) -> str:
        """Replace pronouns with last known context."""
        pronouns = re.compile(r"\b(it|this|that|the first one|the task|these tasks)\b", re.I)
        if pronouns.search(query) and session.get("last_search_term"):
            return pronouns.sub(session["last_search_term"], query)
        return query

    def _classify_intent(self, query: str, context: Optional[Dict], session: Dict) -> Dict:
        # Pass 1: deterministic regex
        for pattern, intent_type in _P1:
            if pattern.search(query):
                return {"type": intent_type, "term": None}

        # Check if it looks like an activity search (contains a noun phrase not caught above)
        words = query.strip().split()
        if len(words) >= 2 and not re.search(r"\b(show|list|all|how many|count|total)\b", query, re.I):
            return {"type": INTENT_ACTIVITY_SEARCH, "term": query.strip()}

        # Pass 2: LLM for ambiguous
        try:
            prompt = PASS2_PROMPT.format(
                query=query,
                focus=session.get("last_search_term", "none"),
                context=json.dumps((context or {}).get("applied_filters", ""))
            )
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "Intent classifier. Return ONLY JSON."},
                           {"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=60
            )
            return json.loads(res.choices[0].message.content)
        except:
            return {"type": INTENT_CLARIFY, "term": None}

    # ── Tool Dispatch ─────────────────────────────────────────────────────────
    def _execute_tool(self, intent: Dict, context: Optional[Dict], session: Dict) -> Dict:
        t = intent["type"]
        ctx = (context or {}).get("current_view", "audit")
        if t == INTENT_ACTIVITY_SEARCH:
            return self.search_activities(intent.get("term", ""), context=ctx)
        if t == INTENT_LIST_DELAYED:
            return self.get_delayed_activities(limit=20, context=context)
        if t == INTENT_LIST_CRITICAL:
            return self.get_critical_path(limit=20, context=context)
        if t == INTENT_LIST_NEG_FLOAT:
            return self.get_negative_float_activities(limit=20, context=ctx)
        if t == INTENT_INTEGRITY:
            return self.check_integrity(context=ctx)
        if t == INTENT_HEALTH:
            return self.get_project_health(context=ctx)
        if t == INTENT_WBS:
            return self.get_wbs_summary(intent.get("wbs_id"), context=ctx)
        if t == INTENT_ANALYTICAL:
            focus = session.get("focus_id") or (intent.get("term") and
                    self.search_activities(intent["term"]).get("data", [{}])[0:1])
            if isinstance(focus, list) and focus:
                focus = focus[0].get("id") if isinstance(focus[0], dict) else None
            if focus:
                return self.analyze_activity_delay(str(focus), context=ctx)
            return self.get_delayed_activities(limit=10, context=context)
        # CLARIFY
        return {"success": False, "clarify": True, "total_count": 0, "data": []}

    # ── LLM Explanation ───────────────────────────────────────────────────────
    def _explain(self, query: str, intent: Dict, tool: Dict, context: Optional[Dict], session: Dict) -> Dict:
        if intent["type"] == INTENT_CLARIFY or tool.get("clarify"):
            hist = [h["q"] for h in session["history"][-2:]]
            return {
                "summary": "I couldn't determine what you're asking. Please be more specific.",
                "metrics": {},
                "insights": ["Try asking: 'Show delayed activities', 'Critical path tasks', 'Is schedule logic valid', or search by activity name."],
                "recommendations": hist or ["Rephrase your question with a specific schedule topic."],
                "template_type": "clarify"
            }

        history_ctx = [{"role": "user", "content": h["q"]} for h in session["history"][-2:]]

        user_msg = (
            f'Query: "{query}"\n'
            f'Intent: {intent["type"]}\n'
            f'UI Context: {json.dumps(context or {})}\n\n'
            f'BACKEND DATA (use exclusively):\n{json.dumps(tool, default=str)}'
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
            # Strip markdown fences if local model adds them
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            result = json.loads(raw)
        except Exception as e:
            logger.error(f"LLM explain error: {e}")
            result = self._fallback_response(tool, intent)

        result = self._sanitize(result)
        # Attach truncation metadata for frontend
        if tool.get("is_truncated"):
            result["is_truncated"] = True
            result["total_count"] = tool.get("total_count", 0)
            result["displayed_count"] = tool.get("displayed_count", 0)
            result["data"] = tool.get("data", [])
        if tool.get("suggestions"):
            result["suggestions"] = tool["suggestions"]
        return result

    @staticmethod
    def _sanitize(result: Dict) -> Dict:
        """Ensure metrics/insights/recommendations contain only primitives."""
        m = result.get("metrics", {})
        result["metrics"] = {k: (str(v) if isinstance(v, (dict, list)) else v)
                             for k, v in m.items() if v is not None}
        result["insights"] = [str(i) for i in result.get("insights", []) if i]
        result["recommendations"] = [str(r) for r in result.get("recommendations", []) if r]
        return result

    @staticmethod
    def _fallback_response(tool: Dict, intent: Dict) -> Dict:
        total = tool.get("total_count", 0)
        data = tool.get("data", [])
        tmpl = "list" if intent["type"].startswith("LIST_") else "health"
        names = [d.get("name", d.get("task_name", "")) for d in data[:5] if isinstance(d, dict)]
        summary = f"Found {total} items."
        if tool.get("is_truncated"):
            summary = f"Showing {tool.get('displayed_count', len(data))} of {total} activities."
        if names:
            summary += f" Top items: {', '.join(names)}."
        return {"summary": summary, "metrics": {"Total": total},
                "insights": [summary], "recommendations": [], "template_type": tmpl}

    # ── Main Entry ────────────────────────────────────────────────────────────
    def analyze(self, query: str, context: Optional[Dict] = None, session_id: str = "default") -> Dict:
        session = self._get_session(session_id)
        try:
            resolved = self._resolve_references(query, session)
            intent = self._classify_intent(resolved, context, session)
            logger.info(f"[{session_id}] Intent={intent['type']} query='{query[:60]}'")
            tool_result = self._execute_tool(intent, context, session)
            response = self._explain(resolved, intent, tool_result, context, session)
            self._update_session(session, query, intent, tool_result, response)
            return response
        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
            return {"summary": f"Analysis error: {e}", "metrics": {},
                    "insights": [], "recommendations": ["Check server logs."],
                    "template_type": "clarify"}

    # ── Tools ─────────────────────────────────────────────────────────────────
    def search_activities(self, term: str, context: str = "audit") -> Dict:
        if not term: return {"success": False, "total_count": 0, "data": [],
                              "error": "No search term provided."}
        source = self.data_store.get_latest(context=context)
        if not source: return {"success": False, "total_count": 0, "data": [],
                                "error": "No schedule data loaded."}
        df = source["df"]["tasks"]
        names = df["task_name"].tolist()
        codes = df["task_code"].tolist()

        # Strategy 1: exact code match
        exact_code = df[df["task_code"].str.upper() == term.upper()]
        # Strategy 2: substring in name
        sub = df[df["task_name"].str.contains(term, case=False, na=False)]
        # Strategy 3: fuzzy name match
        fuzzy_names = difflib.get_close_matches(term, names, n=5, cutoff=0.45)
        fuzzy_df = df[df["task_name"].isin(fuzzy_names)]

        import pandas as pd
        combined = pd.concat([exact_code, sub, fuzzy_df]).drop_duplicates("task_id").head(8)

        # Build suggestions for near-misses
        suggestions = []
        if combined.empty:
            suggestions = difflib.get_close_matches(term, names, n=3, cutoff=0.35)
            return {"success": False, "total_count": 0, "data": [],
                    "suggestions": suggestions,
                    "suggestion_text": f"No match for '{term}'. Did you mean: {', '.join(suggestions)}?" if suggestions else f"No activity matching '{term}' found.",
                    "error": None}

        hpd = source.get("hours_per_day", 8)
        data = []
        for _, r in combined.iterrows():
            float_hrs = float(r.get("float_hrs", r.get("total_float_hr_cnt", 0) or 0))
            data.append({
                "id": r["task_id"], "code": r["task_code"], "name": r["task_name"],
                "status": r.get("status_enum", "Unknown"),
                "start": str(r.get("target_start_date", ""))[:10],
                "finish": str(r.get("target_end_date", ""))[:10],
                "float_days": round(float_hrs / hpd, 1),
                "is_critical": float_hrs <= 0
            })
        return {"success": True, "total_count": len(data), "displayed_count": len(data),
                "is_truncated": False, "data": data,
                "stats": {"matched": len(data)}, "error": None,
                "suggestions": [d["name"] for d in data]}

    def get_delayed_activities(self, limit: int = 20, context: Optional[Dict] = None) -> Dict:
        ctx = (context or {}).get("current_view", "audit") if isinstance(context, dict) else "audit"
        analysis = self.data_store.get_deterministic_analysis(context=ctx)
        acts = analysis.get("activityAnalysis", {})
        delayed = {tid: a for tid, a in acts.items() if a.get("delay_days", 0) > 0
                   and a.get("status_enum") != "COMPLETED"}
        sorted_acts = sorted(delayed.items(), key=lambda x: x[1].get("delay_days", 0), reverse=True)
        top = sorted_acts[:limit]
        latest = self.data_store.get_latest(context=ctx)
        hpd = latest.get("hours_per_day", 8) if latest else 8
        data = [{"id": tid, "code": a.get("task_code",""), "name": a.get("task_name",""),
                 "delay_days": a.get("delay_days", 0),
                 "float_days": round(a.get("float_hrs", 0) / hpd, 1),
                 "category": a.get("delay_float_category",""),
                 "status": a.get("status_enum",""),
                 "finish": str(a.get("target_end_date",""))[:10]}
                for tid, a in top]
        delays = [a.get("delay_days", 0) for a in delayed.values()]
        return {"success": True, "total_count": len(delayed), "displayed_count": len(data),
                "is_truncated": len(delayed) > limit, "data": data,
                "stats": {"max_delay_days": max(delays) if delays else 0,
                          "avg_delay_days": round(sum(delays)/len(delays), 1) if delays else 0,
                          "critical_delayed": sum(1 for a in delayed.values() if a.get("float_hrs",0) <= 0)},
                "error": None}

    def get_critical_path(self, limit: int = 20, context: Optional[Dict] = None) -> Dict:
        ctx = (context or {}).get("current_view", "audit") if isinstance(context, dict) else "audit"
        analysis = self.data_store.get_deterministic_analysis(context=ctx)
        acts = analysis.get("activityAnalysis", {})
        critical = {tid: a for tid, a in acts.items() if a.get("is_critical_p6")
                    and a.get("status_enum") != "COMPLETED"}
        sorted_acts = sorted(critical.items(), key=lambda x: x[1].get("float_hrs", 0))
        top = sorted_acts[:limit]
        latest = self.data_store.get_latest(context=ctx)
        hpd = latest.get("hours_per_day", 8) if latest else 8
        data = [{"id": tid, "code": a.get("task_code",""), "name": a.get("task_name",""),
                 "float_days": round(a.get("float_hrs", 0) / hpd, 1),
                 "delay_days": a.get("delay_days", 0),
                 "finish": str(a.get("target_end_date",""))[:10]}
                for tid, a in top]
        return {"success": True, "total_count": len(critical), "displayed_count": len(data),
                "is_truncated": len(critical) > limit, "data": data,
                "stats": {"total_critical": len(critical),
                          "neg_float_count": sum(1 for a in critical.values() if a.get("float_hrs",0) < 0)},
                "error": None}

    def get_negative_float_activities(self, limit: int = 20, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        acts = analysis.get("activityAnalysis", {})
        latest = self.data_store.get_latest(context=context)
        hpd = latest.get("hours_per_day", 8) if latest else 8
        neg = {tid: a for tid, a in acts.items()
               if a.get("float_hrs", 0) < 0 and a.get("status_enum") != "COMPLETED"}
        sorted_acts = sorted(neg.items(), key=lambda x: x[1].get("float_hrs", 0))
        top = sorted_acts[:limit]
        data = [{"id": tid, "code": a.get("task_code",""), "name": a.get("task_name",""),
                 "float_days": round(a.get("float_hrs", 0) / hpd, 1),
                 "delay_days": a.get("delay_days", 0),
                 "finish": str(a.get("target_end_date",""))[:10]}
                for tid, a in top]
        floats = [a.get("float_hrs", 0) / hpd for a in neg.values()]
        return {"success": True, "total_count": len(neg), "displayed_count": len(data),
                "is_truncated": len(neg) > limit, "data": data,
                "stats": {"worst_float_days": round(min(floats), 1) if floats else 0,
                          "avg_float_days": round(sum(floats)/len(floats), 1) if floats else 0},
                "error": None}

    def get_project_health(self, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        summary = analysis.get("projectSummary", {})
        health = summary.get("healthMetrics", {})
        assessment = summary.get("assessment", [])
        pass_count = sum(1 for a in assessment if a.get("status") is True or a.get("status_text") == "PASS")
        fail_count = sum(1 for a in assessment if a.get("status") is False or a.get("status_text") == "FAIL")
        warn_count = len(assessment) - pass_count - fail_count
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "is_truncated": False, "data": [],
                "stats": {"score": health.get("projectHealthScore", 0),
                          "status": health.get("healthStatus", "Unknown"),
                          "delay_days": summary.get("projectDelayDays", 0),
                          "pass_checks": pass_count, "fail_checks": fail_count,
                          "warning_checks": warn_count,
                          "issues": health.get("qualityIssues", [])},
                "error": None, "template_type": "health"}

    def check_integrity(self, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        assessment = analysis.get("projectSummary", {}).get("assessment", [])
        logic = next((a for a in assessment if a["id"] == 1), {})
        leads = next((a for a in assessment if a["id"] == 2), {})
        lags  = next((a for a in assessment if a["id"] == 3), {})
        hard  = next((a for a in assessment if a["id"] == 5), {})
        details = logic.get("details", {})
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "is_truncated": False, "data": [],
                "stats": {
                    "logic_status": logic.get("status_text", "UNKNOWN"),
                    "logic_explanation": logic.get("explanation", ""),
                    "open_start_count": len(details.get("starts", [])),
                    "open_finish_count": len(details.get("finishes", [])),
                    "open_start_names": details.get("starts", []),
                    "open_finish_names": details.get("finishes", []),
                    "leads_pct": round(float(leads.get("val", 0)), 2),
                    "lags_pct": round(float(lags.get("val", 0)), 2),
                    "hard_constraints_pct": round(float(hard.get("val", 0)), 2),
                    "leads_status": leads.get("status_text") or ("PASS" if leads.get("status") else "FAIL"),
                    "lags_status": lags.get("status_text") or ("PASS" if lags.get("status") else "FAIL"),
                },
                "error": None, "template_type": "integrity"}

    def get_wbs_summary(self, wbs_id: Optional[str] = None, context: str = "audit") -> Dict:
        data = self.data_store.get_wbs_summary(target_level=2, context=context)
        return {"success": True, "total_count": len(data), "displayed_count": len(data),
                "is_truncated": False, "data": data,
                "stats": {"total_nodes": len(data)}, "error": None}

    def analyze_activity_delay(self, activity_id: str, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        acts = analysis.get("activityAnalysis", {})
        act = acts.get(activity_id)
        if not act:
            return {"success": False, "total_count": 0, "data": [],
                    "error": f"Activity ID {activity_id} not found in schedule data."}
        source = self.data_store.get_latest(context=context)
        hpd = source.get("hours_per_day", 8) if source else 8
        graph = (source or {}).get("dependency_graph", {})
        node = graph.get(activity_id, {})
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "is_truncated": False,
                "data": [{
                    "id": activity_id,
                    "code": act.get("task_code",""), "name": act.get("task_name",""),
                    "status": act.get("status_enum",""),
                    "delay_days": act.get("delay_days", 0),
                    "float_days": round(act.get("float_hrs", 0) / hpd, 1),
                    "is_critical": act.get("is_critical_p6", False),
                    "category": act.get("delay_float_category",""),
                    "target_start": str(act.get("target_start_date",""))[:10],
                    "target_finish": str(act.get("target_end_date",""))[:10],
                    "predecessors": node.get("predecessors", [])[:5],
                    "successors": node.get("successors", [])[:5],
                }],
                "stats": {"delay_days": act.get("delay_days", 0),
                          "float_days": round(act.get("float_hrs", 0) / hpd, 1),
                          "predecessor_count": len(node.get("predecessors", [])),
                          "successor_count": len(node.get("successors", []))},
                "error": None, "template_type": "activity"}
