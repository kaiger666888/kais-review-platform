"""Verification tests for audit log protection authorizer (DEBT-03).

The audit_protect_authorizer was implemented in v1.0 and registered
in database.py:28 via set_authorizer(). These tests verify it works
correctly: UPDATE and DELETE on audit_entries are blocked while all
other operations are allowed.
"""

import sqlite3

from app.core.audit import audit_protect_authorizer


class TestAuditAuthorizerUnit:
    """Unit tests for audit_protect_authorizer function."""

    def test_update_on_audit_entries_denied(self):
        """UPDATE on audit_entries returns SQLITE_DENY."""
        result = audit_protect_authorizer(
            sqlite3.SQLITE_UPDATE, "audit_entries", None, None, None
        )
        assert result == sqlite3.SQLITE_DENY

    def test_delete_on_audit_entries_denied(self):
        """DELETE on audit_entries returns SQLITE_DENY."""
        result = audit_protect_authorizer(
            sqlite3.SQLITE_DELETE, "audit_entries", None, None, None
        )
        assert result == sqlite3.SQLITE_DENY

    def test_select_on_audit_entries_allowed(self):
        """SELECT on audit_entries returns SQLITE_OK."""
        result = audit_protect_authorizer(
            sqlite3.SQLITE_SELECT, "audit_entries", None, None, None
        )
        assert result == sqlite3.SQLITE_OK

    def test_insert_on_audit_entries_allowed(self):
        """INSERT on audit_entries returns SQLITE_OK."""
        result = audit_protect_authorizer(
            sqlite3.SQLITE_INSERT, "audit_entries", None, None, None
        )
        assert result == sqlite3.SQLITE_OK

    def test_update_on_reviews_allowed(self):
        """UPDATE on reviews (non-audit table) returns SQLITE_OK."""
        result = audit_protect_authorizer(
            sqlite3.SQLITE_UPDATE, "reviews", None, None, None
        )
        assert result == sqlite3.SQLITE_OK

    def test_delete_on_reviews_allowed(self):
        """DELETE on reviews (non-audit table) returns SQLITE_OK."""
        result = audit_protect_authorizer(
            sqlite3.SQLITE_DELETE, "reviews", None, None, None
        )
        assert result == sqlite3.SQLITE_OK

    def test_select_on_reviews_allowed(self):
        """SELECT on reviews returns SQLITE_OK."""
        result = audit_protect_authorizer(
            sqlite3.SQLITE_SELECT, "reviews", None, None, None
        )
        assert result == sqlite3.SQLITE_OK

    def test_update_on_policy_versions_allowed(self):
        """UPDATE on policy_versions (non-audit table) returns SQLITE_OK."""
        result = audit_protect_authorizer(
            sqlite3.SQLITE_UPDATE, "policy_versions", None, None, None
        )
        assert result == sqlite3.SQLITE_OK


class TestAuditAuthorizerIntegration:
    """Integration tests: verify authorizer works with real SQLite connection."""

    def test_update_audit_entries_raises_not_authorized(self):
        """Attempting UPDATE on audit_entries raises OperationalError."""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE audit_entries (id INTEGER PRIMARY KEY, action TEXT)"
        )
        conn.execute(
            "CREATE TABLE reviews (id INTEGER PRIMARY KEY, state TEXT)"
        )
        conn.execute("INSERT INTO audit_entries (action) VALUES ('test')")
        conn.execute("INSERT INTO reviews (state) VALUES ('PENDING')")

        # Register the authorizer
        conn.set_authorizer(audit_protect_authorizer)

        # SELECT should work
        conn.execute("SELECT * FROM audit_entries")

        # INSERT should work
        conn.execute("INSERT INTO audit_entries (action) VALUES ('test2')")

        # UPDATE on audit_entries should fail
        try:
            conn.execute("UPDATE audit_entries SET action = 'modified' WHERE id = 1")
            assert False, "UPDATE should have raised DatabaseError"
        except sqlite3.DatabaseError as e:
            assert "not authorized" in str(e).lower()

        # DELETE on audit_entries should fail
        try:
            conn.execute("DELETE FROM audit_entries WHERE id = 1")
            assert False, "DELETE should have raised DatabaseError"
        except sqlite3.DatabaseError as e:
            assert "not authorized" in str(e).lower()

        # UPDATE on reviews should succeed (authorizer only protects audit_entries)
        conn.execute("UPDATE reviews SET state = 'COMPLETE' WHERE id = 1")

        # DELETE on reviews should succeed
        conn.execute("DELETE FROM reviews WHERE id = 1")

        conn.close()

    def test_read_audit_entries_succeeds(self):
        """SELECT on audit_entries works after authorizer is registered."""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE audit_entries (id INTEGER PRIMARY KEY, action TEXT)"
        )
        conn.execute("INSERT INTO audit_entries (action) VALUES ('read_test')")
        conn.set_authorizer(audit_protect_authorizer)

        # SELECT should work
        cursor = conn.execute("SELECT * FROM audit_entries")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "read_test"

        conn.close()
