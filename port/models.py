from django.db import models
from django.utils import timezone


class Flight(models.Model):
    STATUS_CHOICES = [
        ('landing',  'Landing'),
        ('takeoff',  'Takeoff'),
        ('StandBy',  'Stand By'),
        ('Landed',   'Landed'),
        ('Departed', 'Departed'),
        ('Cancelled','Cancelled'),
    ]

    flight_id    = models.IntegerField(unique=True, verbose_name="Flight ID")
    airline      = models.CharField(max_length=100, default="Unknown")
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='StandBy')
    emergency    = models.BooleanField(default=False)
    time         = models.IntegerField(
        default=0,
        help_text="Scheduled time in minutes past midnight (0–1439)"
    )
    # NEW: Day of year (1–365).
    date_day     = models.IntegerField(
        default=1,
        verbose_name="Day of Year",
        help_text="Day of the current year (1–365). Cannot be earlier than today."
    )
    runway_id    = models.IntegerField(
        default=1,
        verbose_name="Runway ID",
        help_text="Runway number (1–5)"
    )
    created_at   = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['date_day', 'time', '-emergency']

    def __str__(self):
        return f"Flight {self.flight_id} | {self.airline} | {self.status}"

    @property
    def formatted_time(self):
        h = self.time // 60
        m = self.time % 60
        return f"{h:02d}:{m:02d}"

    @property
    def formatted_date(self):
        """Return day-of-year as a readable date string for the current year."""
        import datetime
        year = timezone.now().year
        try:
            dt = datetime.date(year, 1, 1) + datetime.timedelta(days=self.date_day - 1)
            return dt.strftime("%b %d, %Y")
        except Exception:
            return f"Day {self.date_day}"

    @property
    def is_pending(self):
        return self.status in ('landing', 'takeoff', 'StandBy')

    @property
    def status_color(self):
        colors = {
            'landing':  'warning',
            'takeoff':  'info',
            'StandBy':  'secondary',
            'Landed':   'success',
            'Departed': 'primary',
            'Cancelled':'danger',
        }
        return colors.get(self.status, 'secondary')


class FlightLog(models.Model):
    """Audit log: records every status change for a flight."""
    flight     = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='logs')
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    message    = models.TextField(blank=True)
    timestamp  = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return (
            f"[{self.timestamp:%Y-%m-%d %H:%M}] "
            f"Flight {self.flight.flight_id}: {self.old_status} → {self.new_status}"
        )


class Runway(models.Model):
    STATUS_CHOICES = [
        ('free', 'Free'),
        ('busy', 'Busy'),
    ]

    runway_id   = models.IntegerField(unique=True, verbose_name="Runway ID")
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='free')
    assigned_to = models.OneToOneField(
        Flight, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_runway'
    )

    def __str__(self):
        return f"Runway {self.runway_id} — {self.status}"