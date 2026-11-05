"""
The database version this code expects. Update it with every new migration. When the database is behind
(the code was updated but `alembic upgrade head` wasn't run), the API says so plainly instead of failing
with a long database error.
"""

SCHEMA_VERSION = "0008"
UPDATE_MESSAGE = (
    "The database needs updating for this version of the portal. "
    "In apps/api run: .venv\\Scripts\\alembic upgrade head, then restart the API."
)
