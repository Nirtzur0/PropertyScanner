import json
import os
from typing import List, Dict, Any
from datetime import datetime
from src.qa.tracer import PipelineTrace

class ReportGenerator:
    """
    Generates JSON and HTML reports for QA runs.
    """
    
    @staticmethod
    def generate(
        results: List[Dict[str, Any]], 
        output_dir: str
    ):
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. JSON Report
        json_path = os.path.join(output_dir, f"qa_report_{timestamp}.json")
        
        # Convert objects to dicts if needed
        serialized_results = []
        stats = {"total": 0, "passed": 0, "failed": 0, "errors": 0}
        
        for r in results:
            stats["total"] += 1
            if "error" in r:
                stats["errors"] += 1
                serialized_results.append(r)
                continue
                
            assertions = r.get("assertions", [])
            # Serialize assertion objects
            serialized_assertions = []
            failures = 0
            for a in assertions:
                if not a.passed:
                    failures += 1
                serialized_assertions.append({
                    "check_id": a.check_id,
                    "description": a.description,
                    "passed": a.passed,
                    "details": a.details
                })
            
            if failures > 0:
                stats["failed"] += 1
            else:
                stats["passed"] += 1
                
            serialized_results.append({
                "id": r["id"],
                "assertions": serialized_assertions
            })
            
        report_data = {
            "meta": {
                "timestamp": timestamp,
                "stats": stats
            },
            "results": serialized_results
        }
        
        with open(json_path, "w") as f:
            json.dump(report_data, f, indent=2)
            
        # 2. HTML Summary (Minimal)
        html_path = os.path.join(output_dir, f"qa_report_{timestamp}.html")
        html_content = f"""
        <html>
        <head>
            <title>QA Run Report {timestamp}</title>
            <style>
                body {{ font-family: sans-serif; padding: 20px; }}
                .summary {{ padding: 10px; background: #f0f0f0; margin-bottom: 20px; }}
                .fail {{ color: red; }}
                .pass {{ color: green; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            </style>
        </head>
        <body>
            <h1>QA Run Report</h1>
            <div class="summary">
                <p>Total: {stats['total']}</p>
                <p class="pass">Passed: {stats['passed']}</p>
                <p class="fail">Failed: {stats['failed']}</p>
                <p class="fail">Errors: {stats['errors']}</p>
            </div>
            
            <h2>Failures & Errors</h2>
            <table>
                <tr>
                    <th>Listing ID</th>
                    <th>Issue</th>
                </tr>
        """
        
        for r in serialized_results:
            if "error" in r:
                html_content += f"<tr><td>{r['id']}</td><td class='fail'>ERROR: {r['error']}</td></tr>"
            else:
                failures = [a for a in r["assertions"] if not a["passed"]]
                if failures:
                    issues = "<br>".join([f"{f['check_id']}: {f['description']}" for f in failures])
                    html_content += f"<tr><td>{r['id']}</td><td class='fail'>{issues}</td></tr>"
        
        html_content += """
            </table>
        </body>
        </html>
        """
        
        with open(html_path, "w") as f:
            f.write(html_content)
            
        return json_path, html_path
