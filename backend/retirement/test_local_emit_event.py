import os, sys
# Force src to be importable
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from producers.retirement_bridge import emit_retirement_facts

fake_retirement_report = """
Your retirement success probability looks low.
There is a projected income shortfall.
You may also be underinsured.
"""

emit_retirement_facts(
    user_id="test_user_001",
    job_id="319cbc56-f165-408e-8c45-87baa93fd87d",
    retirement_report=fake_retirement_report
)

print("✅ Retirement test completed")
