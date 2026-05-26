# Backward-compatibility shim — real code lives in ai_ops.py
from franki.ai_ops import (  # noqa: F401
    run_report,
    run_payload,
    run_tools,
    run_explain,
    run_compact,
)
