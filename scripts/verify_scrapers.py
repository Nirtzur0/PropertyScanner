import sys
import os
import structlog
import logging

# Ensure src is in python path
sys.path.append(os.getcwd())

from src.listings.agents.factory import AgentFactory
from src.platform.utils.compliance import ComplianceManager

# Configure basic logging to console
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = structlog.get_logger()

def verify_all():
    print("\n🦅 PROPERTY SCANNER - SCRAPER VERIFICATION\n")
    print("Initializing Compliance Manager...")
    compliance = ComplianceManager(user_agent="PropertyScanner/VerificationScript")
    
    scenarios = [
        (
            "pisos", 
            "Pisos.com", 
            {"start_url": "https://www.pisos.com/venta/pisos-madrid/"}
        ),
        (
            "idealista", 
            "Idealista", 
            {"search_path": "/venta-viviendas/madrid/centro/"}
        ),
        (
            "rightmove_uk", 
            "Rightmove UK", 
            {
                "search_path": "https://www.rightmove.co.uk/property-for-sale/find.html?searchLocation=London&locationIdentifier=REGION%5E87490", 
                "max_listings": 2
            }
        ),
        (
            "zoopla_uk", 
            "Zoopla UK", 
            {
                "search_path": "/for-sale/property/london/", 
                "max_listings": 2
            }
        ),
        (
            "immobiliare_it", 
            "Immobiliare.it", 
            {
                "city": "milano", 
                "max_listings": 2
            }
        ),
    ]

    results = []

    for source_id, label, payload in scenarios:
        print(f"\n--- Testing {label} ({source_id}) ---")
        try:
            print(f"Creating agent for {source_id}...")
            agent = AgentFactory.create_crawler(
                source_id, 
                {"id": source_id, "rate_limit": {"period_seconds": 2}}, 
                compliance
            )
            
            print(f"Running agent with payload: {payload}...")
            # Run the agent
            response = agent.run(payload)
            
            status_icon = "✅" if response.status == "success" else "❌"
            item_count = len(response.data) if response.data else 0
            
            print(f"Agent finished.")
            print(f"Status: {response.status}")
            print(f"Items found: {item_count}")
            
            if response.errors:
                print(f"Errors: {response.errors}")
                
            results.append({
                "provider": label,
                "status": response.status,
                "count": item_count,
                "errors": response.errors
            })
            
        except Exception as e:
            print(f"🚨 EXCEPTION: {e}")
            results.append({
                "provider": label,
                "status": "exception",
                "count": 0,
                "errors": [str(e)]
            })

    print("\n\n" + "="*50)
    print("SUMMARY REPORT")
    print("="*50)
    for res in results:
        icon = "✅" if res["status"] == "success" else "❌"
        if res["status"] == "exception":
            icon = "💥"
        print(f"{icon} {res['provider']:<15} | Status: {res['status']:<10} | Items: {res['count']}")
        if res["errors"]:
             print(f"   Errors: {res['errors']}")
    print("="*50 + "\n")

if __name__ == "__main__":
    verify_all()
