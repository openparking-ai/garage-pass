"""G23 -- the token is never stored and never rendered.

**THE SCAN, AND ITS CONTROLS.** Tokens are issued -- enrolments and holder
links, through the API and through the command line -- and every column of
every table in the catalogue is read as text and searched for each plaintext:
zero hits, or the guarantee is broken. The POSITIVE CONTROL runs in the same
test: the same scan, for the token's SHA-256, finds exactly the row that holds
it, so a zero is a measurement of the columns and not blindness. Then every
detail the module rendered in this process since the test began (the suite's
own collector: every ``Answer`` built, every ``Refused`` the command line
printed), and every line the command line printed, is searched for each
plaintext: it appears in the two issue outputs -- the one return, and the scan
must find it there, which is the rendered half's positive control -- and
nowhere else: not in a read, not in a refusal, not in an answer.

Controls: the plaintext planted into a stored column; the presented token
planted into the unknown-credential refusal's detail.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from enrolment_harness import (
    ENROLMENT,
    HOLDER_LINK,
    TRANSIENT_ENTRY,
    credential,
    issue,
    issue_link,
    redeem,
    redeem_link,
    seeded,
)
from fixtures import at
from garage_pass import findings as f
from garage_pass.enrolment import digest
from garage_pass.passes import State
from garage_pass.store.postgres import all_tables, tenant
from garage_pass.store.records import change_state
from store_harness import needs_postgres, new_tenant

pytestmark = needs_postgres


def columns_holding(owner, needle: str) -> list[str]:
    """Every ``table.column`` in the catalogue whose text contains ``needle``,
    read as the owner (which sees every tenant's rows)."""
    hits = []
    with owner.cursor() as cursor:
        for table in all_tables(owner):
            cursor.execute(
                "SELECT attname FROM pg_attribute WHERE attrelid = %s::regclass AND attnum > 0 "
                "AND NOT attisdropped", (table,),
            )
            for (column,) in cursor.fetchall():
                cursor.execute(
                    f'SELECT count(*) FROM "{table}" WHERE "{column}"::text LIKE %s',
                    (f"%{needle}%",),
                )
                if cursor.fetchone()[0]:
                    hits.append(f"{table}.{column}")
    return hits


def _dsn_for_the_app(monkeypatch):
    from psycopg import conninfo

    from garage_pass.store.postgres import APP_ROLE
    from store_harness import APP_PASSWORD, DSN

    params = conninfo.conninfo_to_dict(DSN)
    monkeypatch.setenv("GARAGE_PASS_DSN", conninfo.make_conninfo(
        **{**params, "user": APP_ROLE, "password": APP_PASSWORD}))


@pytest.mark.guarantee("G23")
def test_the_plaintext_is_in_no_column_of_any_table_and_the_digest_is_the_control(
    app, owner, tenant_id
):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    tokens = {
        ENROLMENT: issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-1",
                         vehicle_description="silver Toyota")["token"],
        HOLDER_LINK: issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_, "link-1")["token"],
    }
    # redeem both, so the redemption columns are populated and scanned too
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, tokens[ENROLMENT], "CAR-1").redeemed
    redeem_link(app, tenant_id, TRANSIENT_ENTRY, tokens[HOLDER_LINK])
    tables = all_tables(owner)
    assert {"enrolments", "holder_links", "passes"} <= set(tables) and len(tables) >= 11
    for kind, token in tokens.items():
        assert columns_holding(owner, token) == [], f"the {kind} token is stored in plaintext"
        # THE CONTROL: the same scan finds the digest, in the one column that holds it
        table = "enrolments" if kind == ENROLMENT else "holder_links"
        assert columns_holding(owner, digest(token)) == [f"{table}.token_sha256"], kind
        # and a fragment of the token is not there either (a prefix stored "for lookup")
        assert columns_holding(owner, token[:12]) == [], kind


@pytest.mark.guarantee("G23")
def test_the_plaintext_is_rendered_by_the_issue_calls_and_by_nothing_else(
    app, owner, tenant_id, tmp_path, capsys, monkeypatch
):
    """Everything rendered since this test began -- every Answer, every printed
    refusal (the suite's collector) and every line the command line printed --
    holds the tokens only in the two issue outputs -- and the pass read
    (``show-pass``) renders neither a token nor its digest."""
    from _rendered_sentences import rendered_so_far
    from garage_pass.cli import main

    _dsn_for_the_app(monkeypatch)
    started = len(rendered_so_far())
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    T = ["--tenant", str(tenant_id), "--garage", TRANSIENT_ENTRY.id]
    printed: list[tuple[str, str]] = []

    def run(argv: list[str]) -> dict:
        status = main(argv)
        out = capsys.readouterr()
        printed.append((argv[0], out.out + out.err))
        return {"status": status, "printed": out.out}

    issued = run(["issue-enrolment", *T, "--pass-id", pass_.id, "--enrolment-id", "qr-cli",
                  "--starts-on", "2026-06-01", "--days-valid", "3", "--by", "owner",
                  "--at", "2026-06-01T12:00:00-06:00"])
    assert issued["status"] == 0
    token = json.loads(issued["printed"])["token"]
    link = run(["issue-holder-link", *T, "--pass-id", pass_.id, "--link-id", "link-cli",
                "--starts-on", "2026-06-01", "--days-valid", "3", "--by", "owner",
                "--at", "2026-06-01T12:00:00-06:00"])
    link_token = json.loads(link["printed"])["token"]
    # every door that could render it: the redemptions (refused and not), a read,
    # the link's redemption (which issues and RETURNS a new token -- the one return
    # -- and must not render the LINK's), the refusals that name a credential
    other = new_tenant(owner)
    seeded(app, other, TRANSIENT_ENTRY)
    unknown_here = redeem(app, other, TRANSIENT_ENTRY, token, "CAR-1")  # another tenant
    assert unknown_here.refusal.code == f.REFUSAL_CREDENTIAL_UNKNOWN
    assert token not in unknown_here.refusal.detail, "the refusal echoed the token presented"
    unknown_cli = run(["redeem-enrolment", "--tenant", str(other), "--garage", TRANSIENT_ENTRY.id,
                       "--token", token, "--vehicle", "CAR-1", "--lane", "L1", "--direction",
                       "entry", "--at", "2026-06-01T12:00:00-06:00"])
    assert '"REFUSAL_CREDENTIAL_UNKNOWN"' in unknown_cli["printed"]
    wrong_end = run(["redeem-enrolment", *T, "--token", token, "--vehicle", "CAR-1", "--lane",
                     "L1", "--direction", "exit", "--at", "2026-06-01T12:00:00-06:00"])
    assert '"REFUSAL_ENROLMENT_AT_WRONG_END"' in wrong_end["printed"]
    redeemed = run(["redeem-enrolment", *T, "--token", token, "--vehicle", "CAR-1", "--lane",
                    "L1", "--direction", "entry", "--at", "2026-06-01T12:00:00-06:00"])
    assert redeemed["status"] == 0 and '"redeemed": true' in redeemed["printed"]
    used = run(["redeem-enrolment", *T, "--token", token, "--vehicle", "CAR-2", "--lane", "L1",
                "--direction", "entry", "--at", "2026-06-02T12:00:00-06:00"])
    assert '"REFUSAL_CREDENTIAL_ALREADY_USED"' in used["printed"]
    from_link = run(["redeem-holder-link", *T, "--token", link_token, "--name", "A Holder",
                     "--phone", "+1 555 0100", "--enrolment-id", "qr-from-link", "--starts-on",
                     "2026-06-01", "--days-valid", "3", "--at", "2026-06-01T12:00:00-06:00"])
    assert from_link["status"] == 0
    second_token = json.loads(from_link["printed"])["enrolment"]["token"]
    used_link = run(["redeem-holder-link", *T, "--token", link_token, "--name", "A", "--phone",
                     "1", "--enrolment-id", "qr-2", "--starts-on", "2026-06-01", "--days-valid",
                     "3", "--at", "2026-06-01T12:00:00-06:00"])
    assert '"REFUSAL_CREDENTIAL_ALREADY_USED"' in used_link["printed"]
    # the one READ of a pass (G26) is a door too: it renders neither the
    # plaintext (the loop below reads its output with every other command's)
    # nor the digest -- nothing from the credential tables travels
    read = run(["show-pass", *T, "--pass-id", pass_.id])
    assert read["status"] == 0 and '"registrations"' in read["printed"]
    for name, needle in (("enrolment", digest(token)), ("link", digest(link_token))):
        assert needle not in read["printed"], f"the read rendered the {name} digest"
    with tenant(app, tenant_id) as cursor:
        change_state(cursor, tenant_id, TRANSIENT_ENTRY.id, pass_.id, State.REVOKED, by="o",
                     at=at(date(2026, 6, 2), 9), reason="divorced")
    app.commit()
    cancelled = redeem(app, tenant_id, TRANSIENT_ENTRY, second_token, "CAR-3",
                       at=at(date(2026, 6, 2), 10))
    assert cancelled.refusal.code == f.REFUSAL_CREDENTIAL_CANCELLED
    for kind, external_id in ((ENROLMENT, "qr-cli"), (HOLDER_LINK, "link-cli")):
        read = credential(app, tenant_id, external_id, kind)
        assert not any(isinstance(v, str) and (token in v or link_token in v)
                       for v in vars(read).values()), f"a read of the {kind} carried a token"
    # THE RENDERED SCAN, and its positive control: the scan sees the token where it IS returned
    tokens = {"enrolment token": token, "link token": link_token, "second token": second_token}
    for name, needle in tokens.items():
        where = [command for command, text in printed if needle in text]
        expected = {"enrolment token": ["issue-enrolment"], "link token": ["issue-holder-link"],
                    "second token": ["redeem-holder-link"]}[name]
        assert where == expected, f"the {name} was printed by {where}"
        rendered = [d for d, _stack in rendered_so_far()[started:] if needle in d]
        assert rendered == [], f"the {name} reached a rendered detail: {rendered}"
    assert len(rendered_so_far()) - started >= 6, "the collector saw the answers and refusals"
    # and the refusal that names a credential names its ID, never its token
    assert "'qr-cli'" in used["printed"] and token not in used["printed"]
