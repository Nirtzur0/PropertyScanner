import sys
import argparse
import structlog
import os
from src.services.storage import StorageService
from src.services.valuation import ValuationService
from src.qa.golden_set import GoldenSetGenerator
from src.qa.tracer import QATracer
from src.qa.assertions import QAAssertions
from src.qa.reporting import ReportGenerator

logger = structlog.get_logger()

def main():
    parser = argparse.ArgumentParser(description="Run End-to-End QA on Real Data")
    parser.add_argument("--size", type=int, default=10, help="Golden Set size")
    parser.add_argument("--output_dir", type=str, default="qa_reports", help="Output directory")
    args = parser.parse_args()
    
    # Setup
    db_path = "data/listings.db"
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
        
    storage = StorageService(db_url=f"sqlite:///{os.path.abspath(db_path)}")
    
    # 1. Generate Golden Set
    print(f"Generating Golden Set (n={args.size})...")
    gs_gen = GoldenSetGenerator(db_path)
    golden_set = gs_gen.generate(size=args.size)
    
    if not golden_set:
        print("Error: Empty Golden Set generated. Check database content.")
        sys.exit(1)
        
    # 2. Initialize Service & Tracer
    val_service = ValuationService(storage)
    tracer = QATracer()
    
    results = []
    
    print(f"Running pipeline on {len(golden_set)} listings...")
    
    for i, listing in enumerate(golden_set):
        print(f"Processing {i+1}/{len(golden_set)}: {listing.id}...", end="\r")
        try:
            # Run Pipeline with Tracing
            val_service.evaluate_deal(listing, tracer=tracer)
            
            # Retrieve Trace
            traces = tracer.get_traces()
            if not traces or traces[-1].listing_id != listing.id:
                raise RuntimeError("Trace mismatch or missing")
                
            latest_trace = traces[-1]
            
            # Check Assertions
            assertions = QAAssertions.check_all(latest_trace)
            
            results.append({
                "id": listing.id,
                "assertions": assertions,
                "trace_summary": list(latest_trace.steps.keys())
            })
            
        except Exception as e:
            logger.error("qa_run_failed", id=listing.id, error=str(e))
            results.append({"id": listing.id, "error": str(e)})
            
    print("\nRun complete.")
    
    # 3. Generate Report
    json_path, html_path = ReportGenerator.generate(results, args.output_dir)
    print(f"Reports generated:\nJSON: {json_path}\nHTML: {html_path}")
    
    # Check failure status
    failures = sum(1 for r in results if "error" in r or any(not a.passed for a in r.get("assertions", [])))
    
    if failures > 0:
        print(f"\n{failures} listings had failures or errors.")
        sys.exit(1)
    else:
        print("\nAll checks PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    main()
