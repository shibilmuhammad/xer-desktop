import json
import pandas as pd
from openai import OpenAI
from typing import Dict, Any, Optional
from .data_store import XERDataStore

class XERQueryExecutor:
    def __init__(self, data_store: XERDataStore):
        self.data_store = data_store

    def execute(self, code: str) -> Dict[str, Any]:
        try:
            latest_data = self.data_store.get_latest()
            baseline_data = self.data_store.get_baseline()
            context = {
                'pd': pd,
                'baseline': baseline_data,
                'updates': self.data_store.updates,
                'latest': latest_data,
                'get_update_by_month': self.data_store.get_update_by_month,
                'hours_per_day': self.data_store.hours_per_day,
                'result': None
            }
            exec(code, context)
            result = context.get('result')
            if isinstance(result, pd.DataFrame):
                result = result.head(50).to_dict('records')
            return {'success': True, 'result': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}

class XERAnalyzer:
    def __init__(self, ollama_url: str = "http://localhost:11434/v1"):
        self.data_store = XERDataStore()
        self.executor = XERQueryExecutor(self.data_store)
        self.client = OpenAI(base_url=ollama_url, api_key="ollama")

    def get_basic_stats(self) -> Dict:
        return self.data_store.compute_basic_stats()

    def get_ai_response(self, user_query: str) -> str:
        basic_stats = self.get_basic_stats()
        try:
            # Code generation prompt
            code_gen_prompt = self._get_code_gen_prompt(user_query, basic_stats)
            try:
                code_response = self.client.chat.completions.create(
                    model="llama3",
                    messages=[
                        {"role": "system", "content": "Generate ONLY valid Python code that sets result = ... No explanations. Use 'baseline' and 'latest' dataframes. Focus on answering the user query precisely."},
                        {"role": "user", "content": code_gen_prompt}
                    ],
                    temperature=0.1,
                    timeout=30
                )
                generated_code = code_response.choices[0].message.content
                if "```python" in generated_code:
                    generated_code = generated_code.split("```python")[1].split("```")[0]
                generated_code = generated_code.strip()
                
                exec_result = self.executor.execute(generated_code)
                code_result = exec_result.get('result') if exec_result['success'] else None
            except Exception as e:
                print(f"AI Code Gen Warning: {str(e)}")
                code_result = None

            # Final response prompt
            response_prompt = self._get_response_prompt(user_query, basic_stats, code_result)
            
            final_response = self.client.chat.completions.create(
                model="llama3",
                messages=[
                    {"role": "system", "content": "You are a professional Primavera P6 Schedule Analyst."},
                    {"role": "user", "content": response_prompt}
                ],
                temperature=0.3,
                timeout=60
            )
            return final_response.choices[0].message.content
        except Exception as e:
            err_str = str(e)
            print(f"CRITICAL AI ERROR: {err_str}")
            return (
                f"I encountered an issue connecting to the AI assistant (Ollama).\n\n"
                f"**Error Details:** {err_str[:200]}\n\n"
                f"**Troubleshooting:**\n"
                f"1. Ensure Ollama is running (`ollama serve`).\n"
                f"2. Ensure you have the model installed: `ollama pull llama3`.\n"
                f"3. Check connection to `http://localhost:11434`.\n\n"
                f"--- \n"
                f"**Basic Stats Fallback:**\n"
                f"Activities: {basic_stats.get('total_activities')}\n"
                f"Critical: {basic_stats.get('critical_pct')}%\n"
                f"Data Date: {basic_stats.get('data_date')}"
            )

    def _get_code_gen_prompt(self, query, stats):
        return f"Query: {query}\nStats: {json.dumps(stats)}\nGenerate python code to analyze 'latest' and 'baseline' dataframes (df['tasks']). Set result to answer the query."

    def _get_response_prompt(self, query, stats, result):
        return f"""
        User Query: {query}
        
        Project Stats:
        {json.dumps(stats, indent=2)}
        
        Analysis Results:
        {json.dumps(result, indent=2) if result else 'No specific data found.'}
        
        Instructions:
        - Provide a professional, concise analysis.
        - Use Markdown formatting:
          - Use # or ## for main headings.
          - Use **bold** for key metrics.
          - USE TABLES for comparing data (e.g., activity counts, dates, delays).
          - Be direct and expert.
        """
