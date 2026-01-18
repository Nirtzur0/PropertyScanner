import sys
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)


def main():
    """
    Run the cognitive property scanner agent.
    
    Usage:
        python -m src.interfaces.agent "Find undervalued apartments in Madrid" "/venta-viviendas/madrid/centro/"
        python -m src.interfaces.agent "Find investment opportunities in Barcelona" "https://www.pisos.com/venta/pisos-barcelona/"
    """
    from src.agentic.orchestrator import CognitiveOrchestrator
    
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python -m src.interfaces.agent \"<query>\" \"<area_url_or_path>\" [--strategy=balanced]")
        return

    query = args[0]
    strategy = "balanced"
    areas = []
    for arg in args[1:]:
        if arg.startswith("--strategy="):
            strategy = arg.split("=", 1)[1] or "balanced"
        else:
            areas.append(arg)

    # Initialize cognitive orchestrator
    orchestrator = CognitiveOrchestrator()
    
    # Run analysis
    print(f"\n🧠 Starting cognitive analysis: {query}\n")
    result = orchestrator.run(query=query, areas=areas, strategy=strategy)
    
    # Print report
    if result.get("final_report"):
        print("\n" + "="*60)
        print("📊 INVESTMENT ANALYSIS REPORT")
        print("="*60)
        print(result["final_report"])
        print("="*60)
    else:
        print(f"\n⚠️ Analysis incomplete: {result.get('error', 'Unknown error')}")
    
    # Summary stats
    print(f"\n📈 Stats:")
    print(f"   Listings found: {result.get('listings_count', 0)}")
    print(f"   Evaluations: {len(result.get('evaluations', []))}")


if __name__ == "__main__":
    main()
