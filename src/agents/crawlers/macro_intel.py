
import json
import sqlite3
import requests
from datetime import datetime
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup
import ollama
import structlog
from src.agents.base import BaseAgent, AgentResponse

logger = structlog.get_logger(__name__)

class MacroIntelligenceAgent(BaseAgent):
    """
    LLM-driven agent that scrapes the web for real-world economic consensus.
    Extracts scenarios (Bull/Bear/Base) for Euribor, Inflation, and GDP.
    """
    def __init__(self, db_path="data/listings.db"):
        super().__init__(name="MacroIntel")
        self.db_path = db_path

    def run(self, input_payload: dict) -> AgentResponse:
        """
        Input: {"year": 2025}
        """
        target_year = input_payload.get("year", datetime.now().year + 1)
        query = f"ECB economic forecasts {target_year} euribor spain inflation housing market consensus"
        
        logger.info("macro_search_start", query=query)
        
        # 1. Search
        results = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
        except Exception as e:
            return AgentResponse(status="failure", errors=[str(e)])

        extracted_scenarios = []
        
        # 2. Scrape & Analyze
        for res in results:
            url = res['href']
            try:
                # Simple scrape
                resp = requests.get(url, timeout=10)
                soup = BeautifulSoup(resp.content, 'html.parser')
                # Extract main text (simple heuristic)
                text = soup.get_text(separator=' ', strip=True)[:4000] # Limit context
                
                # 3. LLM Extraction
                # Use a specific schema for extraction if possible, or straight prompting
                prompt = f"""
                Analyze the following economic report text regarding {target_year}.
                Extract the consensus or projected numerical values for:
                1. Euribor 12-month rate (%)
                2. Inflation rate (HICP) for Spain/Eurozone (%)
                3. GDP Growth (%)
                
                If multiple scenarios (optimistic/pessimistic) mentions, extract them.
                
                Text: "{text}..."
                
                Output ONLY valid JSON in this format:
                [
                    {{"scenario": "base", "euribor": 3.0, "inflation": 2.5, "gdp": 1.5, "confidence": "high"}},
                    {{"scenario": "pessimistic", "euribor": 4.0, ...}}
                ]
                If data is missing, use null.
                """
                
                # Try using gpt-oss or generic model available
                # Fallback to 'llava' if it's the only one, though it's vision it handles text instructions reasonably well
                model = "gpt-oss:latest" 
                # Check what comes back
                
                llm_resp = ollama.chat(model=model, messages=[{'role': 'user', 'content': prompt}])
                content = llm_resp['message']['content']
                
                # Parse JSON
                # Robust find of JSON array
                try:
                    start = content.find('[')
                    end = content.rfind(']') + 1
                    json_str = content[start:end]
                    data = json.loads(json_str)
                    
                    for item in data:
                        extracted_scenarios.append({
                            "source": url,
                            "data": item
                        })
                except:
                    logger.warning("llm_json_parse_fail", content=content[:100])
                    
            except Exception as e:
                logger.warning("scrape_failed", url=url, error=str(e))
                
        # 4. Save
        self._save_scenarios(extracted_scenarios)
        
        return AgentResponse(status="success", data=extracted_scenarios)

    def _save_scenarios(self, scenarios):
        conn = sqlite3.connect(self.db_path)
        for s in scenarios:
            d = s['data']
            conn.execute("""
                INSERT INTO macro_scenarios (date, source_url, scenario_name, euribor_12m_forecast, inflation_forecast, gdp_growth_forecast, confidence_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d"),
                s['source'],
                d.get('scenario', 'base'),
                d.get('euribor'),
                d.get('inflation'),
                d.get('gdp'),
                str(d)
            ))
        conn.commit()
        conn.close()
