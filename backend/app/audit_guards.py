"""Database enforcement; administrators can still disable database triggers."""
from sqlalchemy import DDL, event

SQLITE_GUARDS = [
    f"CREATE TRIGGER IF NOT EXISTS audit_no_{action.lower()} BEFORE {action} ON activity_logs "
    "BEGIN SELECT RAISE(ABORT, 'Activity logs are append-only'); END"
    for action in ("UPDATE", "DELETE")
]
POSTGRES_GUARDS = [
    """CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    RAISE EXCEPTION 'Activity logs are append-only'; END; $$""",
    "CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON activity_logs FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_mutation()",
]


def install_guards(connection):
    for sql in POSTGRES_GUARDS if connection.dialect.name == "postgresql" else SQLITE_GUARDS:
        connection.exec_driver_sql(sql)


def register_guards(table):
    for sql in SQLITE_GUARDS:
        event.listen(table, "after_create", DDL(sql).execute_if(dialect="sqlite"))
    for sql in POSTGRES_GUARDS:
        event.listen(table, "after_create", DDL(sql).execute_if(dialect="postgresql"))
