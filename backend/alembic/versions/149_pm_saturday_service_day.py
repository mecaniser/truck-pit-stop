"""Move existing PM due dates onto the shop's Saturday service day.

The shop performs PM work on Saturdays. Dates stored before that rule sit on
arbitrary weekdays, so the fleet board shows PMs on days nobody services a
truck, and a manager reading the board cannot gather a week's work onto one
visit.

Each date moves forward to the Saturday that closes its week: Monday through
Friday land on the Saturday of that same week, Sunday on the following one, and
a date already on Saturday is untouched. Forward rather than back, so no truck
is pulled in earlier than its odometer supports.

Read-only over scheduling intent: only `pm_due_date` changes, and only for rows
that hold one. The mileage trigger (`next_pm_miles`) is deliberately left
alone - it is the other half of the PM condition and is unaffected by which day
the shop works.

Idempotent: a Saturday shifts by zero days, so re-running changes nothing.
"""
from alembic import op

revision = "149_pm_saturday_service_day"
down_revision = "148_elis_outcome_source"
branch_labels = None
depends_on = None


# ISODOW is Monday=1 .. Sunday=7; Saturday is 6. The modulo leaves a Saturday
# untouched and carries a Sunday to the next one.
_FORWARD_TO_SATURDAY = """
    UPDATE vehicles
       SET pm_due_date = pm_due_date
                       + make_interval(days => ((6 - EXTRACT(ISODOW FROM pm_due_date)::int) % 7))
     WHERE pm_due_date IS NOT NULL
       AND EXTRACT(ISODOW FROM pm_due_date)::int <> 6
"""


def upgrade():
    op.execute(_FORWARD_TO_SATURDAY)


def downgrade():
    # Not reversible: the original weekday is not recoverable from a rounded
    # date - several weekdays collapse onto the same Saturday. Downgrading
    # leaves the dates where they are, which remains a valid schedule.
    pass
