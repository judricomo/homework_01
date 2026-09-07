from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ChoreQueueViewSet,
    ChoreViewSet,
    MembershipDetailView,
    MembershipListCreateView,
)

router = DefaultRouter()
router.register("chores", ChoreViewSet, basename="chore")
router.register("my-chores", ChoreQueueViewSet, basename="my-chore")

urlpatterns = [
    path("", include(router.urls)),
    path("members/", MembershipListCreateView.as_view(), name="membership-list"),
    path(
        "members/<int:pk>/",
        MembershipDetailView.as_view(),
        name="membership-detail",
    ),
]
