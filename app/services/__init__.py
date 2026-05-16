"""Shot Card aggregation services.

Exports the core service classes for convenient import:
- TopologyCollapser: Maps DAG node types to Shot Card bundle fields
- ProgressiveFillEngine: Incrementally fills JSONB columns with deep merge
- ShotCardAggregator: Orchestrates the full aggregation pipeline
- GitPolicyProvider: Provides policies from Git repo with SHA-based caching
- get_git_policy_provider: Singleton factory for GitPolicyProvider
"""

from app.services.aggregator import ShotCardAggregator
from app.services.git_policy_provider import GitPolicyProvider, get_git_policy_provider
from app.services.progressive_fill import ProgressiveFillEngine
from app.services.topology_collapser import TopologyCollapser

__all__ = [
    "ShotCardAggregator",
    "ProgressiveFillEngine",
    "TopologyCollapser",
    "GitPolicyProvider",
    "get_git_policy_provider",
]
