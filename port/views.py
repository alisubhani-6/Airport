from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q

from .models import Flight, FlightLog, Runway
from .forms import FlightForm, FlightSearchForm
from .data_structures import RecordBST, MinHeapQueue


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_structures():
    bst = RecordBST()
    landing_q = MinHeapQueue()
    takeoff_q = MinHeapQueue()
    standby_q = MinHeapQueue()

    for f in Flight.objects.filter(status__in=['landing', 'takeoff', 'StandBy']):
        d = {
            'flight_id': f.flight_id,
            'airline':   f.airline,
            'status':    f.status,
            'time':      f.time,
            'date_day':  f.date_day,
            'emergency': f.emergency,
            'runway_id': f.runway_id,
        }
        bst.insert(f.flight_id, d)
        if f.status == 'landing':
            landing_q.enqueue(d)
        elif f.status == 'takeoff':
            takeoff_q.enqueue(d)
        else:
            standby_q.enqueue(d)

    return bst, landing_q, takeoff_q, standby_q


def _log(flight, old_status, new_status, msg=""):
    FlightLog.objects.create(
        flight=flight,
        old_status=old_status,
        new_status=new_status,
        message=msg,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

def dashboard(request):
    """Main dashboard with live stats."""
    _, landing_q, takeoff_q, standby_q = _build_structures()

    stats = {
        'total':     Flight.objects.count(),
        'pending':   Flight.objects.filter(status__in=['landing', 'takeoff', 'StandBy']).count(),
        'landed':    Flight.objects.filter(status='Landed').count(),
        'departed':  Flight.objects.filter(status='Departed').count(),
        'emergency': Flight.objects.filter(emergency=True, status__in=['landing', 'takeoff', 'StandBy']).count(),
        'cancelled': Flight.objects.filter(status='Cancelled').count(),
    }

    next_landing = landing_q.peek()
    next_takeoff = takeoff_q.peek()
    recent_logs  = FlightLog.objects.select_related('flight').order_by('-timestamp')[:8]
    recent_flights = Flight.objects.order_by('-created_at')[:5]

    context = {
        'stats':          stats,
        'next_landing':   next_landing,
        'next_takeoff':   next_takeoff,
        'landing_count':  landing_q.size(),
        'takeoff_count':  takeoff_q.size(),
        'standby_count':  standby_q.size(),
        'recent_logs':    recent_logs,
        'recent_flights': recent_flights,
    }
    return render(request, 'port/dashboard.html', context)


def add_flight(request):
    """
    Add a new flight OR re-register / update an existing one.

    Rules:
    - If a flight_id already exists, the form updates its airline, status,
      time, date_day, runway_id, and emergency flag.
    - Status transitions: only 'landing', 'takeoff', 'StandBy' are allowed
      via this form; 'Landed', 'Departed', 'Cancelled' cannot be set manually.
    - Date: must be >= today's day-of-year.
    - Time: if date_day == today, must be >= current time.
    - Runway: 1–5 only.
    """
    if request.method == 'POST':
        form = FlightForm(request.POST)
        if form.is_valid():
            flight, created = form.save()
            action = "added" if created else "updated"
            _log(
                flight,
                'None' if created else flight.status,
                flight.status,
                f"Flight {flight.flight_id} {action} via registration form."
            )
            icon = "✅" if created else "🔄"
            messages.success(
                request,
                f"{icon} Flight {flight.flight_id} ({flight.airline}) {action} successfully! "
                f"Scheduled: Day {flight.date_day} at {flight.formatted_time}, Runway {flight.runway_id}."
            )
            return redirect('dashboard')
        else:
            messages.error(request, "❌ Please fix the errors below.")
    else:
        # Pre-populate from query param ?flight_id=XXX (used by "re-register" button)
        prefill_id = request.GET.get('flight_id')
        instance   = None
        if prefill_id:
            try:
                instance = Flight.objects.get(flight_id=int(prefill_id))
            except (Flight.DoesNotExist, ValueError):
                pass
        form = FlightForm(instance=instance)

    return render(request, 'port/flight_form.html', {'form': form, 'title': 'Add / Update Flight'})


def flight_list(request):
    """List all flights with filters — BST traversal."""
    status_filter  = request.GET.get('status', '')
    airline_filter = request.GET.get('airline', '')

    flights = Flight.objects.all()
    if status_filter:
        flights = flights.filter(status=status_filter)
    if airline_filter:
        flights = flights.filter(airline__icontains=airline_filter)

    bst, _, _, _ = _build_structures()
    inorder_ids  = bst.inorder()

    context = {
        'flights':        flights,
        'inorder_ids':    inorder_ids,
        'status_filter':  status_filter,
        'airline_filter': airline_filter,
        'status_choices': Flight.STATUS_CHOICES,
    }
    return render(request, 'port/flight_list.html', context)


def flight_detail(request, pk):
    """Detail view with log history."""
    flight = get_object_or_404(Flight, pk=pk)
    logs   = flight.logs.all()
    return render(request, 'port/flight_detail.html', {'flight': flight, 'logs': logs})


def process_landing(request):
    """Process next landing."""
    if request.method == 'POST':
        _, landing_q, _, _ = _build_structures()
        next_f = landing_q.peek()
        if next_f:
            try:
                flight = Flight.objects.get(flight_id=next_f['flight_id'])
                old    = flight.status
                flight.status       = 'Landed'
                flight.processed_at = timezone.now()
                flight.save()
                _log(flight, old, 'Landed',
                     f"Flight {flight.flight_id} landed on Runway {flight.runway_id}.")
                messages.success(
                    request,
                    f"🛬 Flight {flight.flight_id} ({flight.airline}) has landed on Runway {flight.runway_id}!"
                )
            except Flight.DoesNotExist:
                messages.error(request, "Flight record not found.")
        else:
            messages.warning(request, "⚠️ No pending landing flights.")
    return redirect('dashboard')


def process_takeoff(request):
    """Process next takeoff."""
    if request.method == 'POST':
        _, _, takeoff_q, _ = _build_structures()
        next_f = takeoff_q.peek()
        if next_f:
            try:
                flight = Flight.objects.get(flight_id=next_f['flight_id'])
                old    = flight.status
                flight.status       = 'Departed'
                flight.processed_at = timezone.now()
                flight.save()
                _log(flight, old, 'Departed',
                     f"Flight {flight.flight_id} departed from Runway {flight.runway_id}.")
                messages.success(
                    request,
                    f"🛫 Flight {flight.flight_id} ({flight.airline}) has departed from Runway {flight.runway_id}!"
                )
            except Flight.DoesNotExist:
                messages.error(request, "Flight record not found.")
        else:
            messages.warning(request, "⚠️ No pending takeoff flights.")
    return redirect('dashboard')


def cancel_flight(request, pk):
    """Cancel a pending flight."""
    flight = get_object_or_404(Flight, pk=pk)
    if request.method == 'POST':
        if not flight.is_pending:
            messages.error(request, "Only pending flights can be cancelled.")
        else:
            old = flight.status
            flight.status = 'Cancelled'
            flight.save()
            _log(flight, old, 'Cancelled', f"Flight {flight.flight_id} cancelled.")
            messages.success(request, f"❌ Flight {flight.flight_id} cancelled.")
        return redirect('flight_list')
    return render(request, 'port/confirm_cancel.html', {'flight': flight})


def search_flight(request):
    form   = FlightSearchForm(request.GET or None)
    result = None
    found  = None

    if form.is_valid():
        fid = form.cleaned_data['flight_id']
        try:
            result = Flight.objects.get(flight_id=fid)
            found  = True
        except Flight.DoesNotExist:
            found = False

    return render(request, 'port/search.html', {
        'form':   form,
        'result': result,
        'found':  found,
    })


def pending_queues(request):
    _, landing_q, takeoff_q, standby_q = _build_structures()

    def process(queue):
        flights = queue.to_list()
        for f in flights:
            f['hours']   = f['time'] // 60
            f['minutes'] = f['time'] % 60
        return flights

    context = {
        'landing_flights': process(landing_q),
        'takeoff_flights': process(takeoff_q),
        'standby_flights': process(standby_q),
    }
    return render(request, 'port/queues.html', context)


def standby_manage(request):
    """
    Display all StandBy flights with per-flight inline edit forms.
    Allows updating scheduled time and/or promoting to 'landing' or 'takeoff'.
    """
    standby_flights = Flight.objects.filter(status='StandBy').order_by('-emergency', 'date_day', 'time')
    emergency_count = standby_flights.filter(emergency=True).count()
 
    context = {
        'standby_flights': standby_flights,
        'emergency_count': emergency_count,
    }
    return render(request, 'port/standby_manage.html', context)
 
 
def standby_update(request, pk):
    """
    Handle inline edit form submission for a single StandBy flight.
 
    POST params:
        time   — new scheduled time in minutes (0–1439)
        status — 'StandBy' (keep), 'landing', or 'takeoff' (promote)
 
    Rules:
        - Only flights currently in StandBy can be updated via this view.
        - Status can only be set to 'landing' or 'takeoff' (promotion),
          or left as 'StandBy' (time-only update).
        - Time must be 0–1439.
    """
    flight = get_object_or_404(Flight, pk=pk)
 
    if request.method != 'POST':
        return redirect('standby_manage')
 
    if flight.status != 'StandBy':
        messages.error(request, f"Flight {flight.flight_id} is no longer on standby.")
        return redirect('standby_manage')
 
    # ── Validate & parse time ─────────────────────────────────────────────
    raw_time = request.POST.get('time', '').strip()
    try:
        new_time = int(raw_time)
        if not (0 <= new_time <= 1439):
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, f"❌ Invalid time value for FL{flight.flight_id}. Must be 0–1439.")
        return redirect('standby_manage')
 
    # ── Validate status ───────────────────────────────────────────────────
    new_status = request.POST.get('status', 'StandBy')
    allowed_statuses = ('StandBy', 'landing', 'takeoff')
    if new_status not in allowed_statuses:
        messages.error(request, f"❌ Invalid status '{new_status}' for FL{flight.flight_id}.")
        return redirect('standby_manage')
 
    # ── Apply changes ─────────────────────────────────────────────────────
    old_status  = flight.status
    old_time    = flight.time
    changed     = False
 
    if new_time != old_time:
        flight.time = new_time
        changed = True
 
    if new_status != 'StandBy':
        flight.status = new_status
        changed = True
 
    if changed:
        flight.save()
 
        # Build a descriptive log message
        parts = []
        if new_time != old_time:
            h_old, m_old = old_time // 60, old_time % 60
            h_new, m_new = new_time // 60, new_time % 60
            parts.append(f"time {h_old:02d}:{m_old:02d} → {h_new:02d}:{m_new:02d}")
        if new_status != old_status:
            parts.append(f"promoted from StandBy to {new_status}")
 
        log_msg = f"Flight {flight.flight_id} updated: " + "; ".join(parts) + "."
        _log(flight, old_status, flight.status, log_msg)
 
        # User-friendly success message
        if new_status == 'landing':
            messages.success(
                request,
                f"🛬 FL{flight.flight_id} ({flight.airline}) promoted to Landing queue."
            )
        elif new_status == 'takeoff':
            messages.success(
                request,
                f"🛫 FL{flight.flight_id} ({flight.airline}) promoted to Takeoff queue."
            )
        else:
            h, m = new_time // 60, new_time % 60
            messages.success(
                request,
                f"🕐 FL{flight.flight_id} ({flight.airline}) rescheduled to {h:02d}:{m:02d}."
            )
    else:
        messages.info(request, f"No changes made to FL{flight.flight_id}.")
 
    return redirect('standby_manage')