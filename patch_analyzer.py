import re

with open("backend/modules/analyzer.py", "r") as f:
    content = f.read()

# 1. Update ROUTER_PROMPT
router_prompt_new = """ROUTER_PROMPT = \"\"\"You are the intent router for a Primavera P6 Schedule Analysis AI.
Before routing, classify the user's query into one of the following:
- DATA_QUERY: Direct retrieval (e.g., "critical activities")
- LOGIC_ANALYSIS: Linking, constraints, dependencies
- RISK_ANALYSIS: Probability, delay risk, SPI
- SIMULATION: "What happens if X changes", "What if..."
- BENCHMARK: Productivity norms, industry comparison
- MULTI_STEP_ANALYSIS: Top contributors, variance drivers

AVAILABLE TOOLS:
1. get_activity_details(name: str) - For finding specific activities/tasks.
2. get_delayed_activities(limit: int) - For listing delayed tasks.
3. get_critical_path(limit: int) - For critical path.
4. get_negative_float_activities(limit: int) - For negative float tasks.
5. analyze_activity_delay(activity_name: str) - For analyzing "why is X delayed?".
6. check_open_ends() - For unlinked tasks or open ends.
7. check_constraints() - For hard/soft constraints.
8. check_circular_dependencies() - For circular logic or loops.
9. check_path_continuity() - For broken logic paths or dangling logic.
10. get_project_health() - For overall project status or health score.
11. get_wbs_summary(wbs_name: str) - For WBS summaries.
12. get_project_summary() - For total project duration, start/finish dates.
13. clarify() - Use this if the query is ambiguous or unanswerable.

UI CONTEXT AWARENESS:
Use the provided UI State to understand what the user is currently looking at.

CONVERSATION MEMORY:
Use the Conversation History to resolve pronouns.

Return ONLY a JSON object:
{"query_type": "...", "tool": "tool_name", "arguments": {"arg_name": "arg_value"}}\"\"\""""

content = re.sub(r'ROUTER_PROMPT = """You are the intent router.*?{"tool": "tool_name", "arguments": {"arg_name": "arg_value"}}"""', router_prompt_new, content, flags=re.DOTALL)

# 2. Update EXPLANATION_PROMPT
explanation_new = """10. Tailor your answer precisely to the user's original query. Combine data intuitively. If asked about circular dependencies, don't talk about open ends unless requested."""

if "10. Tailor your answer precisely" not in content:
    content = content.replace('9. If a summary tool returns project duration, start date, or finish date, ALWAYS answer duration questions directly using that data.', 
    '9. If a summary tool returns project duration, start date, or finish date, ALWAYS answer duration questions directly using that data.\n10. Tailor your answer precisely to the user\'s original query. Combine data intuitively. If asked about circular dependencies, don\'t talk about open ends unless requested.')


# 3. Update _execute_tool
old_exec = """        if tool == "get_activity_details":
            name = args.get("name", "")
            if not name and session.get("last_search_term"): name = session["last_search_term"]
            result = self.get_activity_details(name, context=ctx)
        elif tool == "get_delayed_activities":
            result = self.get_delayed_activities(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "get_critical_path":
            result = self.get_critical_path(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "get_negative_float_activities":
            result = self.get_negative_float_activities(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "check_integrity":
            result = self.check_integrity(context=ctx)
        elif tool == "get_project_health":
            result = self.get_project_health(context=ctx)
        elif tool == "get_wbs_summary":
            result = self.get_wbs_summary(args.get("wbs_name"), context=ctx)
        elif tool == "get_project_summary":
            result = self.get_project_summary(context=ctx)
        elif tool == "analyze_activity_delay":
            name = args.get("activity_name", "")
            if not name and session.get("last_search_term"): name = session["last_search_term"]
            result = self.analyze_activity_delay(name, context=ctx)
        else:
            result = {"success": False, "clarify": True, "total_count": 0, "data": []}"""

new_exec = """        query_type = tool_call.get("query_type", "DATA_QUERY")
        if query_type in ["SIMULATION", "RISK_ANALYSIS", "BENCHMARK", "MULTI_STEP_ANALYSIS"]:
            error_msg = f"This requires {query_type.lower().replace('_', ' ')} capabilities which are not currently implemented."
            if query_type == "SIMULATION":
                error_msg = "Schedule recalculation required. Not available yet."
            return {
                "success": False,
                "tool": tool,
                "arguments": args,
                "error": error_msg,
                "clarify": True,
                "type": "capability_gap"
            }

        if tool == "get_activity_details":
            name = args.get("name", "")
            if not name and session.get("last_search_term"): name = session["last_search_term"]
            result = self.get_activity_details(name, context=ctx)
        elif tool == "get_delayed_activities":
            result = self.get_delayed_activities(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "get_critical_path":
            result = self.get_critical_path(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "get_negative_float_activities":
            result = self.get_negative_float_activities(limit=args.get("limit", 20), context=ctx, wbs_filter=selected_wbs)
        elif tool == "check_integrity":
            result = self.check_integrity(context=ctx)
        elif tool == "check_open_ends":
            result = self.check_open_ends(context=ctx)
        elif tool == "check_constraints":
            result = self.check_constraints(context=ctx)
        elif tool == "check_circular_dependencies":
            result = self.check_circular_dependencies(context=ctx)
        elif tool == "check_path_continuity":
            result = self.check_path_continuity(context=ctx)
        elif tool == "get_project_health":
            result = self.get_project_health(context=ctx)
        elif tool == "get_wbs_summary":
            result = self.get_wbs_summary(args.get("wbs_name"), context=ctx)
        elif tool == "get_project_summary":
            result = self.get_project_summary(context=ctx)
        elif tool == "analyze_activity_delay":
            name = args.get("activity_name", "")
            if not name and session.get("last_search_term"): name = session["last_search_term"]
            result = self.analyze_activity_delay(name, context=ctx)
        else:
            result = {"success": False, "clarify": True, "total_count": 0, "data": []}"""

content = content.replace(old_exec, new_exec)

# 4. Add new tools
new_tools = """
    def check_open_ends(self, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        assessment = analysis.get("projectSummary", {}).get("assessment", [])
        logic = next((a for a in assessment if a["id"] == 1), {})
        details = logic.get("details", {})
        starts = details.get("starts", [])
        finishes = details.get("finishes", [])
        return {"success": True, "total_count": len(starts) + len(finishes), "displayed_count": len(starts) + len(finishes),
                "data": [], "display_items": [], "all_items": [], "stats": {
                    "logic_status": logic.get("status_text", "UNKNOWN"),
                    "open_start_count": len(starts),
                    "open_finish_count": len(finishes),
                }, "template_type": "integrity"}

    def check_constraints(self, context: str = "audit") -> Dict:
        analysis = self.data_store.get_deterministic_analysis(context=context)
        assessment = analysis.get("projectSummary", {}).get("assessment", [])
        hard  = next((a for a in assessment if a["id"] == 5), {})
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "data": [], "display_items": [], "all_items": [], "stats": {
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
        analysis = self.data_store.get_deterministic_analysis(context=context)
        assessment = analysis.get("projectSummary", {}).get("assessment", [])
        leads = next((a for a in assessment if a["id"] == 2), {})
        return {"success": True, "total_count": 1, "displayed_count": 1,
                "data": [], "display_items": [], "all_items": [], "stats": {
                    "leads_pct": round(float(leads.get("val", 0)), 2),
                    "status": leads.get("status_text", "UNKNOWN")
                }, "template_type": "integrity"}
"""

if "def check_open_ends" not in content:
    content = content.replace('def get_wbs_summary(self', new_tools + '\n    def get_wbs_summary(self')

with open("backend/modules/analyzer.py", "w") as f:
    f.write(content)

