from django.urls import path
from . import views

urlpatterns = [
    path('',                    views.dashboard,       name='dashboard'),
    path('flights/',            views.flight_list,     name='flight_list'),
    path('flights/add/',        views.add_flight,      name='add_flight'),
    path('flights/<int:pk>/',   views.flight_detail,   name='flight_detail'),
    path('flights/<int:pk>/cancel/', views.cancel_flight, name='cancel_flight'),
    path('flights/search/',     views.search_flight,   name='search_flight'),
    path('queues/',             views.pending_queues,  name='queues'),
    path('process/landing/',    views.process_landing, name='process_landing'),
    path('process/takeoff/',    views.process_takeoff, name='process_takeoff'),
    path('standby/',                 views.standby_manage, name='standby_manage'),
    path('standby/update/<int:pk>/', views.standby_update, name='standby_update'),
]
