"""Re-derive every answer from the log text alone and check it matches the generator's truth."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
import generate as g  # noqa: E402

LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d)  (\w+) +(.*)$")


def parse(text):
    events = []
    for line in text.splitlines()[1:]:
        stamp, kind, fields = LINE.match(line).groups()
        events.append((stamp, kind, dict(p.split("=", 1) for p in fields.split())))
    return events


def answer(events, q):
    text = q["instructions"]
    if m := re.search(r"order #(\d+)", text):
        o = "#" + m[1]
        if "warehouse" in text:
            return next(f["warehouse"] for _, k, f in events if k == "SHIPPED" and f["order"] == o)
        if "returned" in text:
            return any(k == "RETURNED" and f["order"] == o for _, k, f in events)
        total = next(f["total"] for _, k, f in events if k == "ORDER_PLACED" and f["order"] == o)
        refund = next(f["amount"] for _, k, f in events if k == "REFUND" and f["order"] == o)
        return total != refund
    if m := re.search(r"customer (C-\d+)", text):
        c = m[1]
        if "critical" in text:
            n = sum(1 for _, k, f in events if k == "TICKET" and f["customer"] == c and f["severity"] == "critical")
            return 0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3
        closed = next(s for s, k, f in events if k == "ACCOUNT_CLOSED" and f["customer"] == c)
        return any(k == "ORDER_PLACED" and f["customer"] == c and s > closed for s, k, f in events)
    counts = {w: 0 for w in g.WAREHOUSES}
    if "shipped the most" in text:
        for _, k, f in events:
            if k == "SHIPPED":
                counts[f["warehouse"]] += 1
    else:
        wh = {f["order"]: f["warehouse"] for _, k, f in events if k == "SHIPPED"}
        for o in {f["order"] for _, k, f in events if k == "RETURNED"}:
            counts[wh[o]] += 1
    top = sorted(counts.values(), reverse=True)
    assert top[0] >= 1.5 * top[1], counts
    return max(counts, key=counts.get)


class TruthTest(unittest.TestCase):
    def check(self, case):
        events = parse(case["state"])
        for name, q in case["questions"].items():
            with self.subTest(case=case["id"], q=name):
                self.assertEqual(answer(events, q), case["truth"][name]["answer"])

    def test_all_lengths(self):
        for length in g.LENGTHS:
            for i in range(3):
                self.check(g.build_case(length, i))

    def test_deterministic(self):
        self.assertEqual(g.build_case(8_000, 4)["state"], g.build_case(8_000, 4)["state"])

    def test_yes_no_balanced(self):
        case = g.build_case(16_000, 2)
        for fam in ["L1", "X1", "X2"]:
            answers = [t["answer"] for t in case["truth"].values() if t["family"] == fam]
            self.assertEqual(sorted(answers), [False, True])

    def test_negations_are_inverted(self):
        case = g.build_case(g.ROBUSTNESS_LENGTH, 0)
        _, truth = g.robustness(case)
        for name, t in truth.items():
            if t["test"] == "C3":
                self.assertEqual(t["answer"], not case["truth"][t["base"]]["answer"])


if __name__ == "__main__":
    unittest.main()
