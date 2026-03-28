from django import forms
from django.utils import timezone
import datetime

from .models import Flight


def _today_day_of_year():
    """Return today's day-of-year (1–365/366)."""
    today = timezone.now().date()
    return today.timetuple().tm_yday


def _current_minutes():
    """Return current local time as minutes-past-midnight."""
    now = timezone.now()
    return now.hour * 60 + now.minute


def _current_year():
    return timezone.now().year


def _used_runways():
    """
    Return a set of runway IDs (1–5) that are currently busy
    (i.e. have a pending flight assigned to them).
    Used to pre-populate the runway dropdown label.
    """
    busy = set(
        Flight.objects.filter(
            status__in=['landing', 'takeoff', 'StandBy'],
            runway_id__in=range(1, 6)
        ).values_list('runway_id', flat=True)
    )
    return busy


# ---------------------------------------------------------------------------
# Main flight form  (create  OR  re-register an existing flight)
# ---------------------------------------------------------------------------

class FlightForm(forms.Form):
    """
    Standalone Form (not ModelForm) so we can handle both create and update
    for an existing flight_id without a unique-constraint collision.
    """

    flight_id = forms.IntegerField(
        label="Flight ID",
        widget=forms.NumberInput(attrs={
            'class': 'atc-input',
            'placeholder': 'e.g. 101',
            'min': '1',
        }),
    )

    airline = forms.CharField(
        max_length=100,
        label="Airline",
        widget=forms.TextInput(attrs={
            'class': 'atc-input',
            'placeholder': 'e.g. Emirates',
        }),
    )

    status = forms.ChoiceField(
        choices=[
            ('landing', 'Landing'),
            ('takeoff', 'Takeoff'),
            ('StandBy', 'Stand By'),
        ],
        label="Status",
        widget=forms.Select(attrs={'class': 'atc-select'}),
    )

    emergency = forms.BooleanField(
        required=False,
        label="Mark as Emergency",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input-atc'}),
    )

    # Day of year — minimum is today, max 365
    date_day = forms.IntegerField(
        label="Day of Year",
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(attrs={
            'class': 'atc-input',
            'id': 'id_date_day',
        }),
    )

    time = forms.IntegerField(
        label="Scheduled Time (minutes past midnight, 0–1439)",
        min_value=0,
        max_value=1439,
        widget=forms.NumberInput(attrs={
            'class': 'atc-input',
            'min': '0',
            'max': '1439',
            'placeholder': 'e.g. 480 = 08:00',
            'id': 'id_time',
        }),
    )

    runway_id = forms.IntegerField(
        label="Runway ID",
        min_value=1,
        max_value=5,
        widget=forms.NumberInput(attrs={
            'class': 'atc-input',
            'min': '1',
            'max': '5',
            'placeholder': '1–5',
        }),
    )

    # ------------------------------------------------------------------ #
    # Initialise with helpful defaults                                     #
    # ------------------------------------------------------------------ #

    def __init__(self, *args, **kwargs):
        # Allow passing an existing Flight instance for pre-population
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

        today_day = _today_day_of_year()
        self.fields['date_day'].widget.attrs['min'] = today_day
        self.fields['date_day'].min_value = today_day

        # Store today's values so the template JS can read them
        self.today_day = today_day
        self.current_year = _current_year()
        self.today_minutes = _current_minutes()

        # Pre-populate from existing instance
        if self.instance and not self.data:
            self.fields['flight_id'].initial = self.instance.flight_id
            self.fields['airline'].initial   = self.instance.airline
            self.fields['status'].initial    = self.instance.status
            self.fields['emergency'].initial  = self.instance.emergency
            self.fields['date_day'].initial  = max(self.instance.date_day, today_day)
            self.fields['time'].initial      = self.instance.time
            self.fields['runway_id'].initial = self.instance.runway_id

        # Build runway choices with busy/free labels
        busy = _used_runways()
        runway_choices = []
        for r in range(1, 6):
            label = f"Runway {r}"
            if r in busy:
                # Check if this runway belongs to current instance (editing same flight)
                if self.instance and self.instance.runway_id == r:
                    label += " (current)"
                else:
                    label += " — in use"
            else:
                label += " — free"
            runway_choices.append((r, label))

        self.runway_choices = runway_choices  # expose to template if needed
        self.fields['runway_id'].widget = forms.Select(
            choices=runway_choices,
            attrs={'class': 'atc-select'},
        )

    # ------------------------------------------------------------------ #
    # Field-level validation                                               #
    # ------------------------------------------------------------------ #

    def clean_flight_id(self):
        fid = self.cleaned_data.get('flight_id')
        if fid is not None and fid <= 0:
            raise forms.ValidationError("Flight ID must be a positive integer.")
        return fid

    def clean_runway_id(self):
        rid = self.cleaned_data.get('runway_id')
        if rid is not None and not (1 <= rid <= 5):
            raise forms.ValidationError("Runway must be between 1 and 5.")
        return rid

    def clean_date_day(self):
        day = self.cleaned_data.get('date_day')
        today = _today_day_of_year()
        if day is not None and day < today:
            raise forms.ValidationError(
                f"Day cannot be in the past. Today is day {today} of {_current_year()}."
            )
        if day is not None and day > 365:
            raise forms.ValidationError("Day cannot exceed 365.")
        return day

    def clean_time(self):
        t = self.cleaned_data.get('time')
        if t is not None and not (0 <= t <= 1439):
            raise forms.ValidationError("Time must be between 0 (00:00) and 1439 (23:59).")
        return t

    def clean(self):
        cleaned = super().clean()
        day  = cleaned.get('date_day')
        time = cleaned.get('time')

        if day is not None and time is not None:
            today = _today_day_of_year()
            now_minutes = _current_minutes()
            if day == today and time < now_minutes:
                h, m = divmod(now_minutes, 60)
                raise forms.ValidationError(
                    f"For today (day {today}), the scheduled time cannot be earlier "
                    f"than the current time ({h:02d}:{m:02d})."
                )
        return cleaned

    # ------------------------------------------------------------------ #
    # Save helper — create or update                                       #
    # ------------------------------------------------------------------ #

    def save(self):
        """
        Create a new Flight or update an existing one.
        Returns (flight, created) tuple.
        """
        data = self.cleaned_data
        fid  = data['flight_id']

        try:
            flight   = Flight.objects.get(flight_id=fid)
            created  = False
        except Flight.DoesNotExist:
            flight   = Flight(flight_id=fid)
            created  = True

        flight.airline   = data['airline']
        flight.status    = data['status']
        flight.emergency = data['emergency']
        flight.date_day  = data['date_day']
        flight.time      = data['time']
        flight.runway_id = data['runway_id']
        flight.save()
        return flight, created


# ---------------------------------------------------------------------------
# Search form (unchanged)
# ---------------------------------------------------------------------------

class FlightSearchForm(forms.Form):
    flight_id = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'atc-input',
            'placeholder': 'Enter Flight ID...',
        }),
        label='Search Flight ID',
    )