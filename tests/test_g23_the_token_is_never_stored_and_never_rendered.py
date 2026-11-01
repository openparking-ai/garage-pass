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
from garage_pass.enrolment import digest, register_hash_of
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
    (``show-pass``) and the garage's register read (``show-garage-register``)
    render neither a token nor its digest."""
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
                  "--starts-on", "2026-06-01", "--days-valid", "3", "--plate", "CAR-1",
                  "--by", "owner", "--at", "2026-06-01T12:00:00-06:00"])
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
                       "--token-in-argv",
                           "--token", token, "--vehicle", "CAR-1", "--lane", "L1", "--direction",
                       "entry", "--at", "2026-06-01T12:00:00-06:00"])
    assert '"REFUSAL_CREDENTIAL_UNKNOWN"' in unknown_cli["printed"]
    # bound to its plate from issue: recognised at either end (its first use moves
    # the draft pass to active), and a far-off plate is wrong car
    redeemed = run(["redeem-enrolment", *T, "--token-in-argv",
                    "--token", token, "--vehicle", "CAR-1", "--lane",
                    "L1", "--direction", "entry", "--at", "2026-06-01T12:00:00-06:00"])
    assert redeemed["status"] == 0 and '"recognised": true' in redeemed["printed"]
    other_end = run(["redeem-enrolment", *T, "--token-in-argv",
                     "--token", token, "--vehicle", "CAR-1", "--lane",
                     "L1", "--direction", "exit", "--at", "2026-06-01T12:00:00-06:00"])
    assert '"recognised": true' in other_end["printed"]
    used = run(["redeem-enrolment", *T, "--token-in-argv",
                "--token", token, "--vehicle", "VAN-99", "--lane", "L1",
                "--direction", "entry", "--at", "2026-06-02T12:00:00-06:00"])
    assert '"match_required": true' in used["printed"]
    used = run(["confirm-match", *T, "--enrolment-id", "qr-cli", "--matched", "no",
                "--vehicle", "VAN-99", "--decided-by", "api", "--lane", "L1", "--direction",
                "entry", "--at", "2026-06-02T12:00:00-06:00"])
    assert '"REFUSAL_CREDENTIAL_WRONG_CAR"' in used["printed"]
    from_link = run(["redeem-holder-link", *T, "--token-in-argv",
                     "--token", link_token, "--name", "A Holder",
                     "--phone", "+1 555 0100", "--enrolment-id", "qr-from-link", "--plate",
                     "HOLDER-1", "--starts-on",
                     "2026-06-01", "--days-valid", "3", "--at", "2026-06-01T12:00:00-06:00"])
    assert from_link["status"] == 0
    second_token = json.loads(from_link["printed"])["enrolment"]["token"]
    used_link = run(["redeem-holder-link", *T, "--token-in-argv",
                     "--token", link_token, "--name", "A", "--phone",
                     "1", "--enrolment-id", "qr-2", "--plate", "HOLDER-2", "--starts-on",
                     "2026-06-01", "--days-valid",
                     "3", "--at", "2026-06-01T12:00:00-06:00"])
    assert '"REFUSAL_CREDENTIAL_ALREADY_USED"' in used_link["printed"]
    # the two writes on one QR (0005): replace-car ISSUES and returns the new QR's
    # token -- the one return -- and renders neither the old one's nor its digest;
    # cancel-code renders no token at all
    replaced = run(["replace-car", *T, "--enrolment-id", "qr-cli", "--new-enrolment-id",
                    "qr-replacement", "--starts-on", "2026-06-02", "--days-valid", "3",
                    "--plate", "NEW-9", "--by",
                    "desk", "--reason", "rental swapped", "--at", "2026-06-02T08:00:00-06:00"])
    assert replaced["status"] == 0, replaced["printed"]
    replacement_token = json.loads(replaced["printed"])["new"]["token"]
    assert digest(token) not in replaced["printed"]
    cancelled_one = run(["cancel-code", *T, "--enrolment-id", "qr-replacement", "--by", "desk",
                         "--reason", "never received", "--at", "2026-06-02T08:05:00-06:00"])
    assert cancelled_one["status"] == 0, cancelled_one["printed"]
    # the one READ of a pass (G26) is a door too: it renders neither the
    # plaintext (the loop below reads its output with every other command's)
    # nor the digest -- nothing from the credential tables travels
    read = run(["show-pass", *T, "--pass-id", pass_.id])
    assert read["status"] == 0 and '"registrations"' in read["printed"]
    for name, needle in (("enrolment", digest(token)), ("link", digest(link_token))):
        assert needle not in read["printed"], f"the read rendered the {name} digest"
    # and the one READ of a garage's register (G27), the same way
    register = run(["show-garage-register", *T])
    assert register["status"] == 0 and '"registrations"' in register["printed"]
    for name, needle in (("enrolment", digest(token)), ("link", digest(link_token)),
                         ("replacement", digest(replacement_token))):
        assert needle not in register["printed"], f"the register read rendered the {name} digest"
    # its positive control: the register DOES carry each QR, by its register hash (the
    # hash of the digest), which is what a lane matches -- so the scan above reads the
    # very output the QRs are in
    for needle in (register_hash_of(token), register_hash_of(replacement_token)):
        assert needle in register["printed"], "the register lost a QR's register hash"
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
    tokens = {"enrolment token": token, "link token": link_token, "second token": second_token,
              "replacement token": replacement_token}
    for name, needle in tokens.items():
        where = [command for command, text in printed if needle in text]
        expected = {"enrolment token": ["issue-enrolment"], "link token": ["issue-holder-link"],
                    "second token": ["redeem-holder-link"],
                    "replacement token": ["replace-car"]}[name]
        assert where == expected, f"the {name} was printed by {where}"
        rendered = [d for d, _stack in rendered_so_far()[started:] if needle in d]
        assert rendered == [], f"the {name} reached a rendered detail: {rendered}"
    assert len(rendered_so_far()) - started >= 6, "the collector saw the answers and refusals"
    # and the refusal that names a credential names its ID, never its token
    assert "'qr-cli'" in used["printed"] and token not in used["printed"]


@pytest.mark.guarantee("G23")
def test_the_command_line_reads_a_token_from_stdin_and_refuses_one_in_argv_unless_told(
    app, tenant_id, capsys, monkeypatch
):
    """A TOKEN IS NOT AN ARGUMENT: arguments are visible in ``ps`` to every
    user on the machine. ``redeem-enrolment`` and ``redeem-holder-link`` read
    the token from standard input; ``--token`` is refused by name
    (REFUSAL_TOKEN_ON_THE_COMMAND_LINE, exit 3, nothing written) unless the
    caller also says ``--token-in-argv`` -- the old form, kept behind a flag
    for an integrator that has not moved yet -- and the refusal never echoes
    the token. Measured before this: the token was a required argument."""
    import io

    from garage_pass.cli import main

    _dsn_for_the_app(monkeypatch)
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    qr = issue_plate_for(app, tenant_id, pass_)
    link = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    T = ["--tenant", str(tenant_id), "--garage", TRANSIENT_ENTRY.id]
    MOVE = ["--vehicle", "CAR-1", "--lane", "L1", "--direction", "entry",
            "--at", "2026-06-01T12:00:00-06:00"]
    HOLDER = ["--name", "A Holder", "--phone", "+1 555 0100", "--enrolment-id", "qr-l",
              "--plate", "HOLDER-1", "--starts-on", "2026-06-01", "--days-valid", "3",
              "--at", "2026-06-01T12:00:00-06:00"]

    def run(argv: list[str], stdin: str = "") -> tuple[int, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        status = main(argv)
        out = capsys.readouterr()
        return status, out.out + out.err

    for command, rest, token in (("redeem-enrolment", MOVE, qr),
                                 ("redeem-holder-link", HOLDER, link)):
        status, printed = run([command, *T, "--token", token, *rest])
        assert status == 3 and '"REFUSAL_TOKEN_ON_THE_COMMAND_LINE"' in printed, printed
        assert '"field": "token"' in printed and token not in printed
    assert credential(app, tenant_id, "link-1", HOLDER_LINK).state.value == "issued"
    status, printed = run(["redeem-enrolment", *T, *MOVE], stdin=f"{qr}\n")
    assert status == 0 and '"recognised": true' in printed and qr not in printed
    status, printed = run(["redeem-holder-link", *T, *HOLDER], stdin=f"  {link}\n")
    assert status == 0 and link not in printed, printed
    assert credential(app, tenant_id, "link-1", HOLDER_LINK).state.value == "redeemed"
    status, printed = run(["redeem-enrolment", *T, *MOVE], stdin="")
    assert '"REFUSAL_FIELD_BLANK"' in printed and '"field": "token"' in printed, (
        "nothing on stdin is a blank token, refused as a blank --token always was")
    # the old form, behind its flag
    status, printed = run(["redeem-enrolment", *T, "--token-in-argv", "--token", qr, *MOVE])
    assert status == 0 and '"recognised": true' in printed


def issue_plate_for(app, tenant_id, pass_) -> str:
    from enrolment_harness import issue_plate

    return issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "CAR-1")["token"]
