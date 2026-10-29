import pytest

from app import staff_account
from app.auth.staff import set_staff_password
from app.db import engine


def test_set_staff_password_creates_an_account_with_an_argon2_hash(run_sql):
    with engine.begin() as conn:
        user_id = set_staff_password(conn, "new.staff@example.test", "a long enough password")

    [row] = run_sql("SELECT user_id, password_hash, is_active FROM app.staff_users")
    assert row.user_id == user_id
    assert row.password_hash.startswith("$argon2")
    assert "a long enough password" not in row.password_hash
    assert row.is_active


def test_resetting_a_password_signs_out_existing_sessions(signed_in, staff):
    with engine.begin() as conn:
        same_user = set_staff_password(conn, staff["email"], "a brand new password")

    assert str(same_user) == staff["user_id"]
    assert signed_in.get("/api/v1/auth/session").status_code == 401
    old = signed_in.post("/api/v1/auth/login", json={"email": staff["email"], "password": staff["password"]})
    assert old.status_code == 401
    new = signed_in.post("/api/v1/auth/login", json={"email": staff["email"], "password": "a brand new password"})
    assert new.status_code == 200


def test_resetting_a_password_reactivates_the_account(staff, run_sql):
    run_sql("UPDATE app.staff_users SET is_active = false")

    with engine.begin() as conn:
        set_staff_password(conn, staff["email"], "a brand new password")

    [row] = run_sql("SELECT is_active FROM app.staff_users")
    assert row.is_active


def test_short_passwords_are_rejected(run_sql):
    with pytest.raises(ValueError, match="at least 12 characters"):
        with engine.begin() as conn:
            set_staff_password(conn, "new.staff@example.test", "too short")

    assert run_sql("SELECT 1 FROM app.staff_users") == []


def test_cli_prompts_twice_and_creates_the_account(monkeypatch, run_sql, capsys):
    answers = iter(["a long enough password", "a long enough password"])
    monkeypatch.setattr(staff_account.getpass, "getpass", lambda prompt="": next(answers))

    exit_code = staff_account.main(["new.staff@example.test"])

    assert exit_code == 0
    assert "new.staff@example.test" in capsys.readouterr().out
    assert len(run_sql("SELECT 1 FROM app.staff_users")) == 1


def test_cli_rejects_an_email_without_a_domain_cleanly(monkeypatch, run_sql, capsys):
    answers = iter(["a long enough password", "a long enough password"])
    monkeypatch.setattr(staff_account.getpass, "getpass", lambda prompt="": next(answers))

    exit_code = staff_account.main(["staff.one"])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "full address" in err and "nothing changed" in err
    assert "INSERT" not in err
    assert run_sql("SELECT 1 FROM app.staff_users") == []


def test_cli_refuses_mismatched_passwords(monkeypatch, run_sql, capsys):
    answers = iter(["a long enough password", "a different password"])
    monkeypatch.setattr(staff_account.getpass, "getpass", lambda prompt="": next(answers))

    exit_code = staff_account.main(["new.staff@example.test"])

    assert exit_code == 1
    assert "do not match" in capsys.readouterr().err
    assert run_sql("SELECT 1 FROM app.staff_users") == []
