"""Shot Card aggregation services.

Exports the three core service classes for convenient import:
- TopologyCollapser: Maps DAG node types to Shot Card bundle fields
- ProgressiveFillEngine: Incrementally fills JSONB columns with deep merge
- ShotCardAggregator: Orchestrates the full aggregation pipeline
"""

from app.services.progressive_fill import ProgressiveFillEngine
from app.services.topology_collapser import TopologyCollapser

__all__ = [
    "ProgressiveFillEngine",
    "TopologyCollapser",
]

# ShotCardAggregator added in Task 2 (aggregator.py creation)
