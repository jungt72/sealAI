<%!
    import datetime
%>
"""${message if message else "empty migration"}
Revision ID: ${up_revision if up_revision else "???"}
Revises: ${repr(down_revision)}
Create Date: ${create_date if create_date else datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}
"""

revision = '${up_revision if up_revision else ""}'
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels) if branch_labels is not None else None}
depends_on = ${repr(depends_on) if depends_on is not None else None}

def upgrade():
    ${upgrades if upgrades is not None else "pass"}

def downgrade():
    ${downgrades if downgrades is not None else "pass"}
