from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ChoreQueueViewSet,
    ChoreViewSet,
    CompletionViewSet,
    MembershipDetailView,
    MembershipListCreateView,
    LeaderboardView,
)

router = DefaultRouter()
router.register("chores", ChoreViewSet, basename="chore")
router.register("my-chores", ChoreQueueViewSet, basename="my-chore")
router.register("completions", CompletionViewSet, basename="completion")

urlpatterns = [
    path("", include(router.urls)),
    path("members/", MembershipListCreateView.as_view(), name="membership-list"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("leaderboard/all-time/", LeaderboardView.as_view(), name="leaderboard-all-time"),
    path(
        "leaderboard/current-period/",
        LeaderboardView.as_view(),
        {"period": "current_period"},
        name="leaderboard-current-period",
    ),
    path(
        "members/<int:pk>/",
        MembershipDetailView.as_view(),
        name="membership-detail",
    ),
]
