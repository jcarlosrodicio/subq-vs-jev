"""Synthetic event logs for Kettle & Co., a fictional online store, with known answers.

Every log is built from a seed, so the same (length, log) pair always yields the same
text, questions and ground truth.
"""
import random
import re
from datetime import datetime, timedelta

WAREHOUSES = ["Bilbao", "Gdansk", "Leeds", "Lyon", "Porto"]
LEVELS = ["None", "One", "Two or three", "Four or more"]
HEADER = "Kettle & Co. online store - event log. One event per line, in chronological order.\n"
LENGTHS = [2_000, 8_000, 16_000, 30_000, 64_000, 128_000, 256_000, 360_000]
LOGS_PER_LENGTH = 20
ROBUSTNESS_LENGTH = 8_000
CHARS_PER_TOKEN = 1.70  # measured in the pilot: ~1.72 chars per token on both APIs, rounded down for headroom
SPAN_MIN = 365 * 24 * 60
START = datetime(2026, 1, 1)
DAY = 24 * 60

NOUL_TEMPLATES = {
    "L1": [
        "Was order #{o} returned?",
        "Does the log show that order #{o} came back as a return?",
        "Did the customer send order #{o} back, with a RETURNED event for it?",
    ],
    "X1": [
        "Did customer {c} place an order after their account was closed?",
        "Is there an ORDER_PLACED event for customer {c} that happens after their ACCOUNT_CLOSED event?",
        "After closing their account, did customer {c} still buy something?",
    ],
    "X2": [
        "Was order #{o} refunded an amount different from its order total?",
        "Does the refund for order #{o} differ from what the customer paid?",
        "Is the REFUND amount for order #{o} unequal to the order's total?",
    ],
}
NEGATIONS = {
    "L1": "Was order #{o} NOT returned?",
    "X1": "Did customer {c} place NO orders after their account was closed?",
    "X2": "Was order #{o} refunded exactly its order total?",
}


class Log:
    def __init__(self, rng):
        self.rng = rng
        self.events = []  # (minute, text)
        self.used_orders = set()
        self.used_customers = set()
        self.chars = len(HEADER)

    def order_id(self, near=None):
        while True:
            if near is None:
                o = self.rng.randint(10000, 99999)
            else:
                o = near - near % 10 + self.rng.randint(0, 9)
            if o not in self.used_orders:
                self.used_orders.add(o)
                return o

    def customer(self):
        while True:
            c = f"C-{self.rng.randint(1, 9999):04d}"
            if c not in self.used_customers:
                self.used_customers.add(c)
                return c

    def add(self, t, kind, fields):
        self.events.append((min(max(t, 0), SPAN_MIN - 1), f"{kind:<15}{fields}"))
        self.chars += 18 + 15 + len(fields) + 1

    def order(self, t, customer, warehouse, returned=False, refund_ratio=1.0, oid=None):
        """Full lifecycle of one order starting at minute t. Returns (order id, total)."""
        r = self.rng
        oid = oid or self.order_id()
        total = round(r.uniform(9, 240), 2)
        self.add(t, "ORDER_PLACED", f"order=#{oid} customer={customer} warehouse={warehouse} total=€{total:.2f}")
        t += r.uniform(0.3, 2) * DAY
        self.add(t, "SHIPPED", f"order=#{oid} warehouse={warehouse}")
        t += r.uniform(1, 4) * DAY
        self.add(t, "DELIVERED", f"order=#{oid}")
        if returned:
            t += r.uniform(2, 12) * DAY
            self.add(t, "RETURNED", f"order=#{oid} reason={r.choice(['damaged', 'wrong-size', 'not-needed', 'late'])}")
            t += r.uniform(1, 5) * DAY
            self.add(t, "REFUND", f"order=#{oid} amount=€{round(total * refund_ratio, 2):.2f}")
        return oid, total

    def ticket(self, t, customer, severity):
        topic = self.rng.choice(["billing", "delivery", "product", "account"])
        self.add(t, "TICKET", f"customer={customer} severity={severity} topic={topic}")

    def text(self):
        lines = []
        for t, body in sorted(self.events, key=lambda e: e[0]):
            stamp = (START + timedelta(minutes=t)).strftime("%Y-%m-%d %H:%M")
            lines.append(f"{stamp}  {body}")
        return HEADER + "\n".join(lines) + "\n"


def depth_time(rng, depth):
    return depth * SPAN_MIN + rng.uniform(-3, 3) * DAY


def build_log(length, log_idx, attempt):
    rng = random.Random(f"{length}-{log_idx}-{attempt}")
    log = Log(rng)
    depths = [[0.1, 0.5, 0.9][(log_idx + i) % 3] for i in range(8)]
    truth, questions = {}, {}

    def noul(name, family, text, answer, depth, **ctx):
        questions[name] = {"type": "noul", "instructions": text}
        truth[name] = {"family": family, "answer": answer, "depth": depth, "ctx": ctx}

    def yes_first():
        return rng.random() < 0.5

    # L1: was order X returned? A near-identical order id gets the opposite fate as a distractor.
    first = yes_first()
    for i, answer in enumerate([first, not first]):
        d = depths[i]
        c = log.customer()
        oid, _ = log.order(depth_time(rng, d), c, rng.choice(WAREHOUSES), returned=answer)
        log.order(rng.uniform(0, 0.95) * SPAN_MIN, log.customer(), rng.choice(WAREHOUSES),
                  returned=not answer, oid=log.order_id(near=oid))
        noul(f"l1_{'ab'[i]}", "L1", NOUL_TEMPLATES["L1"][0].format(o=oid), answer, d, o=oid)

    # L2: which warehouse shipped order X?
    for i in range(2):
        d = depths[2 + i]
        w = rng.choice(WAREHOUSES)
        oid, _ = log.order(depth_time(rng, d), log.customer(), w)
        name = f"l2_{'ab'[i]}"
        questions[name] = {"type": "choice", "instructions": f"Which warehouse shipped order #{oid}?",
                           "criteria": {x: None for x in WAREHOUSES}}
        truth[name] = {"family": "L2", "answer": w, "depth": d, "ctx": {"o": oid}}

    # X1: did customer C order after closing their account? Closure sits at the depth.
    first = yes_first()
    for i, answer in enumerate([first, not first]):
        d = depths[4 + i]
        c = log.customer()
        t_close = depth_time(rng, d)
        for _ in range(2):
            log.order(t_close - rng.uniform(15, 40) * DAY, c, rng.choice(WAREHOUSES))
        log.add(t_close, "ACCOUNT_CLOSED", f"customer={c}")
        if answer:
            log.order(t_close + rng.uniform(4, 25) * DAY, c, rng.choice(WAREHOUSES))
        noul(f"x1_{'ab'[i]}", "X1", NOUL_TEMPLATES["X1"][0].format(c=c), answer, d, c=c)

    # X2: was order X refunded a different amount than its total?
    first = yes_first()
    for i, answer in enumerate([first, not first]):
        d = depths[6 + i]
        ratio = rng.choice([0.5, 0.6, 0.75, 0.8, 0.9]) if answer else 1.0
        oid, _ = log.order(depth_time(rng, d), log.customer(), rng.choice(WAREHOUSES), returned=True, refund_ratio=ratio)
        noul(f"x2_{'ab'[i]}", "X2", NOUL_TEMPLATES["X2"][0].format(o=oid), answer, d, o=oid)

    # A2: how many critical tickets did customer C open? Two customers, two different levels.
    levels = [(log_idx + k) % 4 for k in (0, 2)]
    for i, level in enumerate(levels):
        c = log.customer()
        n = [0, 1, rng.choice([2, 3]), rng.choice([4, 5])][level]
        log.order(rng.uniform(0, 0.9) * SPAN_MIN, c, rng.choice(WAREHOUSES))
        for _ in range(rng.randint(1, 2)):
            log.ticket(rng.uniform(0, 1) * SPAN_MIN, c, rng.choice(["low", "medium"]))
        for _ in range(n):
            log.ticket(rng.uniform(0, 1) * SPAN_MIN, c, "critical")
        name = f"a2_{'ab'[i]}"
        questions[name] = {"type": "score", "instructions": f"How many tickets with severity=critical did customer {c} open?",
                           "criteria": LEVELS}
        truth[name] = {"family": "A2", "answer": level, "depth": None, "ctx": {"c": c, "n": n}}

    # Background traffic. Two warehouses are favoured so the aggregate questions have a clear winner.
    ship_winner, ret_winner = rng.sample(WAREHOUSES, 2)
    budget = length * CHARS_PER_TOKEN
    while log.chars < budget:
        roll = rng.random()
        if roll < 0.75:
            w = rng.choices(WAREHOUSES, weights=[2.2 if x == ship_winner else 1 for x in WAREHOUSES])[0]
            p_ret = 0.4 if w == ret_winner else 0.08
            log.order(rng.uniform(0, 0.97) * SPAN_MIN, log.customer(), w, returned=rng.random() < p_ret,
                      refund_ratio=1.0 if rng.random() < 0.9 else 0.5)
        elif roll < 0.95:
            log.ticket(rng.uniform(0, 1) * SPAN_MIN, log.customer(), rng.choices(["low", "medium", "critical"], [5, 3.5, 1.5])[0])
        else:
            log.add(rng.uniform(0, 1) * SPAN_MIN, "ACCOUNT_CLOSED", f"customer={log.customer()}")

    # A1: which warehouse shipped / returned the most? Counted on the final log, must have a clear margin.
    text = log.text()
    shipped = {w: 0 for w in WAREHOUSES}
    order_wh, returned_ids = {}, set()
    for m in re.finditer(r"SHIPPED +order=(#\d+) warehouse=(\w+)", text):
        shipped[m[2]] += 1
        order_wh[m[1]] = m[2]
    for m in re.finditer(r"RETURNED +order=(#\d+)", text):
        returned_ids.add(m[1])
    returns = {w: 0 for w in WAREHOUSES}
    for o in returned_ids:
        returns[order_wh[o]] += 1
    for name, counts, label in [("a1_ship", shipped, "shipped the most orders"),
                                ("a1_ret", returns, "had the most returned orders")]:
        top, second = sorted(counts.values(), reverse=True)[:2]
        if top < 2 or top < 1.5 * second:
            return None
        winner = max(counts, key=counts.get)
        questions[name] = {"type": "choice", "instructions": f"Across the whole log, which warehouse {label}?",
                           "criteria": {x: None for x in WAREHOUSES}}
        truth[name] = {"family": "A1", "answer": winner, "depth": None, "ctx": {"counts": counts}}

    order = ["l1_a", "l1_b", "l2_a", "l2_b", "x1_a", "x1_b", "x2_a", "x2_b", "a1_ship", "a1_ret", "a2_a", "a2_b"]
    return {"id": f"{length // 1000:03d}K-{log_idx:02d}", "length": length, "log": log_idx, "seed_attempt": attempt,
            "state": text, "questions": {k: questions[k] for k in order}, "truth": {k: truth[k] for k in order}}


def build_case(length, log_idx):
    for attempt in range(1000):
        case = build_log(length, log_idx, attempt)
        if case:
            return case
    raise RuntimeError(f"no valid log for {length}/{log_idx}")


def robustness(case):
    """Extra question sets on the same state: shuffled options, paraphrases and negations."""
    rng = random.Random(f"robust-{case['id']}")
    questions, truth = {}, {}
    for name in ["l2_a", "l2_b", "a1_ship", "a1_ret"]:
        q, t = case["questions"][name], case["truth"][name]
        perms = [WAREHOUSES[:]] + [rng.sample(WAREHOUSES, len(WAREHOUSES)) for _ in range(2)]
        for k, perm in enumerate(perms):
            questions[f"c1_{name}_p{k}"] = {**q, "criteria": {x: None for x in perm}}
            truth[f"c1_{name}_p{k}"] = {**t, "test": "C1", "base": name}
    for name in ["l1_a", "l1_b", "x1_a", "x1_b", "x2_a", "x2_b"]:
        t = case["truth"][name]
        for k, template in enumerate(NOUL_TEMPLATES[t["family"]]):
            questions[f"c2_{name}_v{k}"] = {"type": "noul", "instructions": template.format(**t["ctx"])}
            truth[f"c2_{name}_v{k}"] = {**t, "test": "C2", "base": name}
        questions[f"c3_{name}_neg"] = {"type": "noul", "instructions": NEGATIONS[t["family"]].format(**t["ctx"])}
        truth[f"c3_{name}_neg"] = {**t, "answer": not t["answer"], "test": "C3", "base": name}
    return questions, truth


def all_cases():
    for length in LENGTHS:
        for i in range(LOGS_PER_LENGTH):
            yield build_case(length, i)
