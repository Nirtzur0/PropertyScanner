import sqlite3
import requests
import json

from src.core.config import DEFAULT_DB_PATH

DB_PATH = str(DEFAULT_DB_PATH)
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3"

def analyze_single(desc):
    prompt = f"""Analyze this real estate description and list 3 important structured fields that are MISSING from standard data (elevator, pool, garage).
    Focus on value drivers (e.g. heating, exterior, furnished).
    
    Description: "{desc[:500]}..."
    
    Output list:"""
    
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except:
        return ""

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT description FROM listings WHERE description IS NOT NULL LIMIT 3")
    rows = cursor.fetchall()
    conn.close()
    
    print("\n--- ANALYSIS RESULTS ---\n")
    for i, row in enumerate(rows):
        print(f"\nListing #{i+1}:")
        print(analyze_single(row[0]))

if __name__ == "__main__":
    main()
