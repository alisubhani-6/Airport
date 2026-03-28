from django.contrib import admin
from .models import Flight, FlightLog, Runway


@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display  = ['flight_id', 'airline', 'status', 'emergency', 'formatted_time', 'runway_id', 'created_at']
    list_filter   = ['status', 'emergency', 'airline']
    search_fields = ['flight_id', 'airline']
    ordering      = ['time']


@admin.register(FlightLog)
class FlightLogAdmin(admin.ModelAdmin):
    list_display  = ['flight', 'old_status', 'new_status', 'timestamp']
    list_filter   = ['new_status']
    ordering      = ['-timestamp']


@admin.register(Runway)
class RunwayAdmin(admin.ModelAdmin):
    list_display = ['runway_id', 'status', 'assigned_to']
