from flask import (
    Flask, render_template, request, url_for, redirect,
    flash, get_flashed_messages
)
from flask_mysqldb import MySQL
from datetime import datetime, date

app = Flask(__name__)

app.config['MYSQL_HOST'] = "localhost"
app.config['MYSQL_USER'] = "root"
app.config['MYSQL_PASSWORD'] = "Tars@2511"
app.config['MYSQL_DB'] = "event_system"
app.config['MYSQL_CURSORCLASS'] = "DictCursor"

mysql = MySQL(app)
app.secret_key = "abc123"

def get_cursor():
    return mysql.connection.cursor()

def resource_conflicts(rid, start, end, ignore_event_id=None):
    cur = get_cursor()
    if ignore_event_id:
        sql = """
            SELECT 1
            FROM event_resource_allocations a
            JOIN events e ON a.event_id = e.id
            WHERE a.resource_id = %s
              AND a.event_id != %s
              AND (e.start_time < %s AND e.end_time > %s)
            LIMIT 1
        """
        cur.execute(sql, (rid, ignore_event_id, end, start))
    else:
        sql = """
            SELECT 1
            FROM event_resource_allocations a
            JOIN events e ON a.event_id = e.id
            WHERE a.resource_id = %s
              AND (e.start_time < %s AND e.end_time > %s)
            LIMIT 1
        """
        cur.execute(sql, (rid, end, start))

    conflict = cur.fetchone()
    cur.close()
    return bool(conflict)


def parse_iso_datetime(s):
    try:
        return datetime.fromisoformat(s)
    except:
        return None

@app.route('/')
def home():
    cur = get_cursor()

    cur.execute("SELECT COUNT(*) AS c FROM events")
    total_events = cur.fetchone()['c']

    cur.execute("SELECT COUNT(*) AS c FROM resources")
    total_resources = cur.fetchone()['c']

    cur.execute("""
      SELECT DISTINCT
      e.id, e.title, e.start_time, e.end_time
      FROM events e
      INNER JOIN event_resource_allocations a
      ON e.id = a.event_id
      WHERE e.start_time > NOW()
      ORDER BY e.start_time ASC
      LIMIT 4;
    """)
    upcoming = cur.fetchall()
    cur.close()

    return render_template(
        "dashboard.html",
        total_events=total_events,
        total_resources=total_resources,
        upcoming=upcoming
    )

@app.route('/events')
def events():
    cur = get_cursor()
    cur.execute("""
        SELECT * FROM events
    """)
    rows = cur.fetchall()
    cur.close()
    return render_template("events.html", datas=rows)

@app.route('/add_event', methods=['GET', 'POST'])
def add_event():
    if request.method == "GET":
        get_flashed_messages()
        return render_template("add_event.html",
                               title="", description="",
                               start_time="", end_time="")

    title = request.form.get("title", "").strip()
    desc = request.form.get("description", "").strip()
    start = request.form.get("start_time", "").strip()
    end = request.form.get("end_time", "").strip()

    context = {
        "title": title,
        "description": desc,
        "start_time": start,
        "end_time": end,
    }

    if not title:
        flash("Please enter event title.", "danger")
        return render_template("add_event.html", **context)

    s_dt = parse_iso_datetime(start)
    e_dt = parse_iso_datetime(end)

    if not s_dt or not e_dt:
        flash("Invalid datetime format.", "danger")
        return render_template("add_event.html", **context)

    if s_dt < datetime.now():
        flash("Cannot create past events.", "danger")
        return render_template("add_event.html", **context)

    if s_dt > e_dt:
        flash("Start time must be before end time.", "danger")
        return render_template("add_event.html", **context)
    
    if s_dt == e_dt:
        flash("Start and End Time cannot be same", "danger")
        return render_template("add_event.html", **context)

    cur = get_cursor()
    cur.execute("""
            INSERT INTO events (title, description, start_time, end_time)
            VALUES (%s, %s, %s, %s)
        """, (title, desc, start, end))
    mysql.connection.commit()
    flash("Event added successfully!", "success")
    cur.close()
    return redirect(url_for('events'))


@app.route('/edit_event/<int:id>', methods=['GET', 'POST'])
def edit_event(id):
    cur = get_cursor()
    cur.execute("SELECT * FROM events WHERE id=%s", [id])
    event = cur.fetchone()

    if request.method == "POST":
        title = request.form.get('title', '').strip()
        desc = request.form.get('description', '').strip()
        start = request.form.get('start_time', '').strip()
        end = request.form.get('end_time', '').strip()

        if not title:
            flash("Please enter title.", "danger")
            return redirect(url_for('edit_event', id=id))

        s_dt = parse_iso_datetime(start)
        e_dt = parse_iso_datetime(end)

        if not s_dt or not e_dt:
            flash("Invalid datetime.", "danger")
            return redirect(url_for('edit_event', id=id))

        if s_dt >= e_dt:
            flash("Start must be before end.", "danger")
            return redirect(url_for('edit_event', id=id))
        cur.execute("""
                UPDATE events
                SET title=%s, description=%s, start_time=%s, end_time=%s
                WHERE id=%s
            """, (title, desc, start, end, id))
        mysql.connection.commit()
        flash("Event updated.", "success")
        cur.close()
        return redirect(url_for('events'))
        
    return render_template("edit_event.html", event=event)


@app.route('/delete_event/<int:id>')
def delete_event(id):
    cur = get_cursor()
    cur.execute("DELETE FROM event_resource_allocations WHERE event_id=%s", [id])
    cur.execute("DELETE FROM events WHERE id=%s", [id])
    mysql.connection.commit()
    flash("Event deleted.", "success")
    cur.close()
    return redirect(url_for('events'))



@app.route('/resources')
def resources():
    cur = get_cursor()
    cur.execute("SELECT * FROM resources ORDER BY name ASC")
    rows = cur.fetchall()
    cur.close()
    return render_template("resources.html", datas=rows)


@app.route('/add_resource', methods=['GET', 'POST'])
def add_resource():
    if request.method == "POST":
        name = request.form.get('name', '').strip()
        rtype = request.form.get('type', '').strip()
        details = request.form.get('details', '').strip()

        if not name:
            flash("Please provide resource name.", "danger")
            return redirect(url_for('add_resource'))
        
        if name in resources():
            flash("Resource already exist", "danger")
            return redirect(url_for('add_resource'))
        
        cur = get_cursor()
        cur.execute("SELECT * FROM resources WHERE name=%s AND resource_type = %s",(name, rtype))
        existing_resource = cur.fetchone()
        if existing_resource:
            flash("Resource already exists.", "danger")
            cur.close()
            return redirect(url_for('add_resource'))
        
        cur = get_cursor()
        cur.execute(
                "INSERT INTO resources (name, resource_type, details) VALUES (%s, %s, %s)",
                (name, rtype, details)
            )
        mysql.connection.commit()
        flash("Resource added.", "success")
        cur.close()
        return redirect(url_for('resources'))

    return render_template("add_resource.html")


@app.route('/edit_resource/<int:id>', methods=['GET', 'POST'])
def edit_resource(id):
    cur = get_cursor()
    cur.execute("SELECT * FROM resources WHERE id=%s", [id])
    resource = cur.fetchone()

    if request.method == "POST":
        name = request.form.get('name', '').strip()
        rtype = request.form.get('type', '').strip()
        details = request.form.get('details', '').strip()

        if not name:
            flash("Please provide resource name.", "danger")
            return redirect(url_for('edit_resource', id=id))
            
        cur.execute("""
                UPDATE resources
                SET name=%s, resource_type=%s, details=%s
                WHERE id=%s
            """, (name, rtype, details, id))
        mysql.connection.commit()
        flash("Resource updated.", "success")
        cur.close()
        return redirect(url_for('resources'))
    return render_template("edit_resource.html", resource=resource)


@app.route('/delete_resource/<int:id>')
def delete_resource(id):
    cur = get_cursor()
    cur.execute("DELETE FROM resources WHERE id=%s", [id])
    mysql.connection.commit()
    flash("Resource deleted.", "success")
    cur.close()
    return redirect(url_for('resources'))


@app.route('/allocations')
def allocations():
    cur = get_cursor()
    cur.execute("""
        SELECT e.id, e.title, e.start_time, e.end_time,
               COUNT(a.resource_id) AS total_resources
        FROM events e
        JOIN event_resource_allocations a ON e.id = a.event_id
        GROUP BY e.id
        ORDER BY e.start_time ASC
    """)
    rows = cur.fetchall()
    cur.close()
    return render_template("allocations.html", datas=rows)


@app.route('/allocation_details/<int:event_id>')
def allocation_details(event_id):
    cur = get_cursor()
    cur.execute("SELECT * FROM events WHERE id=%s", [event_id])
    event = cur.fetchone()

    cur.execute("""
        SELECT a.id AS alloc_id, r.id AS resource_id, r.name, r.resource_type, r.details
        FROM event_resource_allocations a
        JOIN resources r ON a.resource_id = r.id
        WHERE a.event_id=%s
    """, [event_id])
    resources = cur.fetchall()
    cur.close()

    return render_template(
        "allocation_details.html",
        event=event,
        resources=resources
    )

@app.route('/add_allocation', methods=['GET', 'POST'])
def add_allocation():

    def load_form():
        cur = get_cursor()
        cur.execute("SELECT id, title, start_time, end_time FROM events ORDER BY start_time ASC")
        events = cur.fetchall()
        cur.execute("SELECT id, name, resource_type FROM resources ORDER BY name ASC")
        resources = cur.fetchall()
        cur.close()
        return events, resources

    if request.method == "GET":
        get_flashed_messages()
        events, resources = load_form()
        return render_template("add_allocation.html", events=events, resources=resources)

    event_id = request.form.get("event_id")
    resource_ids = request.form.getlist("resource_ids")

    events, resources = load_form()

    cur = get_cursor()
    cur.execute("SELECT start_time, end_time FROM events WHERE id=%s", [event_id])
    event = cur.fetchone()

    if not event:
        cur.close()
        flash("Event not found.", "danger")
        return render_template("add_allocation.html", events=events, resources=resources)

    start = event['start_time']
    end = event['end_time']

    for rid in resource_ids:
        if resource_conflicts(rid, start, end):
            cur.execute("SELECT name FROM resources WHERE id=%s", [rid])
            res = cur.fetchone()
            cur.close()
            flash(f"'{res['name']}' is already booked in this time slot.", "danger")
            return render_template("add_allocation.html", events=events, resources=resources)

    try:
        for rid in resource_ids:
            cur.execute(
                "INSERT INTO event_resource_allocations (event_id, resource_id) VALUES (%s, %s)",
                (event_id, rid)
            )
        mysql.connection.commit()
        flash("Allocation successful!", "success")
    except:
        mysql.connection.rollback()
        flash(" Error creating allocation.", "danger")
    finally:
        cur.close()

    events, resources = load_form()
    return render_template("add_allocation.html", events=events, resources=resources)


@app.route('/edit_allocation/<int:event_id>', methods=['GET', 'POST'])
def edit_allocation(event_id):

    if request.method == "GET":
        get_flashed_messages()

    cur = get_cursor()
    cur.execute("SELECT * FROM events WHERE id=%s", [event_id])
    event = cur.fetchone()

    if not event:
        cur.close()
        flash("Event not found.", "danger")
        return redirect(url_for('allocations'))

    cur.execute("SELECT id, name, resource_type FROM resources ORDER BY name ASC")
    all_resources = cur.fetchall()

    cur.execute("SELECT resource_id FROM event_resource_allocations WHERE event_id=%s", [event_id])
    current_allocs = cur.fetchall()
    cur.close()

    current_ids = {str(r['resource_id']) for r in current_allocs}

    if request.method == "POST":
        selected = request.form.getlist("resource_ids")

        if not selected:
            flash(" Please select at least one resource!", "danger")
            return redirect(url_for('edit_allocation', event_id=event_id))

        for rid in selected:
            if resource_conflicts(rid, event['start_time'], event['end_time'], ignore_event_id=event_id):
                cur = get_cursor()
                cur.execute("SELECT name FROM resources WHERE id=%s", [rid])
                name = cur.fetchone()['name']
                cur.close()
                flash(f" '{name}' is already booked.", "danger")
                return redirect(url_for('edit_allocation', event_id=event_id))

        cur = get_cursor()
        try:
            cur.execute("DELETE FROM event_resource_allocations WHERE event_id=%s", [event_id])
            for rid in selected:
                cur.execute(
                    "INSERT INTO event_resource_allocations (event_id, resource_id) VALUES (%s, %s)",
                    (event_id, rid)
                )
            mysql.connection.commit()
            flash("Allocation updated.", "success")
        except:
            mysql.connection.rollback()
            flash("Error updating allocation.", "danger")
        finally:
            cur.close()

        return redirect(url_for('allocation_details', event_id=event_id))

    return render_template(
        "edit_allocation.html",
        event=event,
        all_resources=all_resources,
        allocated_ids=current_ids
    )


@app.route('/delete_event_allocations/<int:event_id>')
def delete_event_allocations(event_id):
    cur = get_cursor()
    try:
        cur.execute("DELETE FROM event_resource_allocations WHERE event_id=%s", [event_id])
        mysql.connection.commit()
        flash("All allocations for this event were deleted.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash("Error deleting allocations.", "danger")
        print("delete_event_allocations error:", e)
    finally:
        cur.close()
    return redirect(url_for('allocations'))


@app.route('/report', methods=['GET', 'POST'])
def report():

    if request.method == "GET":
        return render_template(
            "report.html",
            rows=[],
            start_date="",
            end_date=""
        )

    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")

    if not start_date or not end_date:
        flash("Please select both start and end dates.", "danger")
        return render_template("report.html", rows=[], start_date="", end_date="")

    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.strptime(end_date, "%Y-%m-%d").date()
    except:
        flash("Invalid date format.", "danger")
        return render_template("report.html", rows=[], start_date="", end_date="")

    if sd > ed:
        sd, ed = ed, sd
        flash("Dates swapped because start > end.", "warning")

    cur = get_cursor()
    cur.execute("""
    SELECT
        r.id AS resource_id,r.resource_type ,
        r.name AS resource_name,
        SUM(
            CASE
                WHEN DATE(e.start_time) BETWEEN %s AND %s
                THEN TIMESTAMPDIFF(MINUTE, e.start_time, e.end_time)
                ELSE 0
            END
        ) AS total_minutes,
        SUM(
            CASE
                WHEN DATE(e.start_time) > %s
                THEN 1
                ELSE 0
            END
        ) AS upcoming_count
    FROM resources r
    LEFT JOIN event_resource_allocations a ON r.id = a.resource_id
    LEFT JOIN events e ON a.event_id = e.id
    GROUP BY r.id, r.name, r.resource_type
    ORDER BY r.name ASC
""", (sd, ed, date.today()))

    rows = cur.fetchall()
    cur.close()

    data = []
    for r in rows:
        minutes = int(r['total_minutes'])
        hrs = minutes // 60
        rem = minutes % 60
        hours_used = "0 hr" if minutes == 0 else (f"{hrs} hr" if rem == 0 else f"{hrs} hr {rem} min")

        data.append({
            "resource_name": r['resource_name'],
            "range_hours": hours_used,
            "upcoming_bookings": r['upcoming_count'],
            "resource_type": r['resource_type']
        })

    return render_template(
        "report.html",
        rows=data,
        start_date=sd.isoformat(),
        end_date=ed.isoformat()
    )

if __name__ == "__main__":
    app.run(debug=True)