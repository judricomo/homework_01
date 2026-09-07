from django.urls import path

from .views import MembershipDetailView, MembershipListCreateView

urlpatterns = [
    path("members/", MembershipListCreateView.as_view(), name="membership-list"),
    path(
        "members/<int:pk>/",
        MembershipDetailView.as_view(),
        name="membership-detail",
    ),
]
