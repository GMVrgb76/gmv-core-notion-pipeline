import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
import gmv_mail_flag_export as fe

LISTING = (
    "iCloud\t3\t101\t<a@x>\n"
    "Proton\t5\t7\ta@x\n"
    "Proton\t2\t8\t<b@x>\n"
    "Proton\t2\t9\t\n"
)


class FakeMail:
    def __init__(self, listing=LISTING, fail_ids=()):
        self.listing, self.fail_ids, self.exports = listing, set(fail_ids), []

    def __call__(self, script, args):
        if script is fe.LIST_SCRIPT:
            self.list_args = args
            return self.listing
        acct, box, mid, out = args
        if int(mid) in self.fail_ids:
            raise RuntimeError("boom")
        self.exports.append((acct, int(box), int(mid)))
        Path(out).write_bytes(b"From: x\n\nbody")
        return ""


def test_same_message_id_across_accounts_and_brackets_deduped():
    cands = fe.parse_candidates(LISTING)
    assert len(cands) == 3
    assert {c.key for c in cands} == {"a@x", "b@x", "Proton|2|9"}


def test_exports_new_messages_and_names_are_deterministic(tmp_path):
    fake = FakeMail()
    stats = fe.run(tmp_path, 4, "Proton", "EXPORT", runner=fake)
    assert stats == {"candidates": 3, "exported": 3, "already_exported": 0, "errors": 0}
    assert fake.list_args == ["4", "Proton", "EXPORT"]
    assert sorted(p.name for p in tmp_path.glob("*.eml")) == sorted(c.filename for c in fe.parse_candidates(LISTING))
    assert not list(tmp_path.glob("*.part"))


def test_rerun_skips_already_exported(tmp_path):
    fe.run(tmp_path, 4, "", "EXPORT", runner=FakeMail())
    fake = FakeMail()
    stats = fe.run(tmp_path, 4, "", "EXPORT", runner=fake)
    assert stats["exported"] == 0 and stats["already_exported"] == 3
    assert fake.exports == []


def test_dry_run_writes_nothing(tmp_path):
    fake = FakeMail()
    stats = fe.run(tmp_path, 4, "", "EXPORT", dry_run=True, runner=fake)
    assert stats["exported"] == 3 and fake.exports == [] and list(tmp_path.glob("*.eml")) == []


def test_one_failing_export_is_counted_and_others_continue(tmp_path):
    stats = fe.run(tmp_path, 4, "", "EXPORT", runner=FakeMail(fail_ids={101}))
    assert stats["errors"] == 1 and stats["exported"] == 2
    assert not list(tmp_path.glob("*.part"))


def test_empty_export_file_is_error_not_success(tmp_path):
    def empty_runner(script, args):
        if script is fe.LIST_SCRIPT:
            return "iCloud\t1\t5\t<z@x>\n"
        Path(args[3]).write_bytes(b"")
        return ""

    stats = fe.run(tmp_path, 4, "", "EXPORT", runner=empty_runner)
    assert stats["errors"] == 1 and list(tmp_path.glob("*.eml")) == []


def test_no_flagged_messages_is_not_an_error(tmp_path):
    stats = fe.run(tmp_path, 4, "", "EXPORT", runner=FakeMail(listing=""))
    assert stats == {"candidates": 0, "exported": 0, "already_exported": 0, "errors": 0}
