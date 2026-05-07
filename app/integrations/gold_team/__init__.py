"""Gold-team integration module.

Exports ReviewPlatformClient for gold-team to submit GPU task reviews.
"""

from app.integrations.gold_team.client import (
    ReviewClientError,
    ReviewPlatformClient,
    ReviewQueryResult,
    ReviewSubmitResult,
)

__all__ = [
    "ReviewClientError",
    "ReviewPlatformClient",
    "ReviewQueryResult",
    "ReviewSubmitResult",
]
