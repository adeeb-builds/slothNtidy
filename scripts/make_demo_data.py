"""Builds the demo inbox: four WhatsApp class groups exactly like the pitch deck story.

    python scripts/make_demo_data.py

Creates tests/demo_data/demo_inbox/<Group>/ with a WhatsApp chat export (.txt) and the
media files it mentions, plus tests/demo_data/live_demo_extra/ with a Paging note to drop
in during the live demo (turns the red Unit 3 green).

What is inside (13 files):
  * typed notes from teachers and friends (OS + DBMS)
  * 3 circulars / notices                   -> removed
  * 1 exact re-share, 1 shorter re-typed copy -> removed as duplicates (fuller kept)
  * 2 phone photos of the SAME handwritten page -> one removed as near-duplicate
  * 1 meme                                   -> not in syllabus
  * 1 note that fits OS and DBMS equally     -> needs review
  * nothing on Paging & Virtual Memory      -> the red MISSING row
The handwriting is simulated with a handwriting font (Kalam) so the demo is repeatable;
try your own phone photos too.
"""
import os
import random
import shutil
import sys

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "demo_data", "demo_inbox")
EXTRA = os.path.join(ROOT, "tests", "demo_data", "live_demo_extra")
HAND_FONT = os.path.join(ROOT, "assets", "fonts", "kalam-latin-400-normal.woff")
LRM = "‎"  # the invisible mark real WhatsApp exports put before attachment names

# ---------------------------------------------------------------- note texts
OS_SCHEDULING = [
    ("OPERATING SYSTEMS - UNIT 1: CPU SCHEDULING", """Prof. R. Sharma | Lecture notes, B.Tech CSE Semester 5

1. Why CPU scheduling?
When several processes are in the ready queue, the short-term scheduler (CPU scheduler) picks the next process to run. Goals: maximise CPU utilisation and throughput, minimise turnaround time, waiting time and response time.

Key terms
- Arrival time (AT): when the process enters the ready queue.
- Burst time (BT): CPU time the process needs.
- Completion time (CT), Turnaround time TAT = CT - AT, Waiting time WT = TAT - BT.

2. First Come First Serve (FCFS)
- Non-preemptive. Processes run in order of arrival, like a queue at a ticket counter.
- Simple to implement with a FIFO queue.
- Problem: the convoy effect - one long process makes all short processes behind it wait.

Example: P1 (BT 24), P2 (BT 3), P3 (BT 3) arriving at time 0 in that order.
Gantt chart: P1 0-24, P2 24-27, P3 27-30. Waiting times: 0, 24, 27. Average WT = 17 ms.
If the order were P2, P3, P1 the average WT drops to 3 ms - order matters in FCFS."""),
    ("UNIT 1: CPU SCHEDULING (contd.)", """3. Shortest Job First (SJF)
- Picks the process with the smallest next CPU burst.
- Provably optimal: gives the minimum average waiting time for a given set of processes.
- Non-preemptive SJF runs the chosen job to completion.
- Preemptive version = Shortest Remaining Time First (SRTF): a newly arrived process with a shorter remaining time preempts the running one.
- Difficulty: the length of the next CPU burst is not known in advance. It is predicted with exponential averaging: tau(n+1) = alpha * t(n) + (1 - alpha) * tau(n).
- Problem: starvation of long processes. Solution: ageing.

Example (non-preemptive SJF): P1 (AT 0, BT 7), P2 (AT 2, BT 4), P3 (AT 4, BT 1), P4 (AT 5, BT 4).
Order: P1 0-7, P3 7-8, P2 8-12, P4 12-16. Average WT = (0 + 6 + 3 + 7) / 4 = 4 ms."""),
    ("UNIT 1: CPU SCHEDULING (contd.)", """4. Round Robin (RR)
- Designed for time-sharing systems. Every process gets a fixed time quantum (time slice), e.g. 4 ms.
- If a process does not finish within its time quantum it is preempted and put at the back of the ready queue.
- Performance depends heavily on the size of the time quantum:
  very large quantum -> behaves like FCFS; very small quantum -> too many context switches.
- Rule of thumb: about 80% of CPU bursts should be shorter than the time quantum.

Example: P1 (BT 24), P2 (BT 3), P3 (BT 3), time quantum = 4.
Gantt chart: P1 0-4, P2 4-7, P3 7-10, P1 10-14, 14-18, 18-22, 22-26, 26-30.
Average WT = (6 + 4 + 7) / 3 = 5.66 ms.

Comparison
FCFS - simple, convoy effect. SJF - optimal average waiting time, needs burst prediction, may starve.
Round Robin - fair, good response time, depends on the time quantum.

Important for internals: Gantt chart numericals on all three algorithms."""),
]

DEADLOCK_NOTES = [
    ("Deadlocks - Unit 2 (Rohan's notes)", """Deadlock: a set of processes each waiting for a resource held by another process in the set.

Four necessary conditions (Coffman):
1. Mutual exclusion   2. Hold and wait   3. No preemption   4. Circular wait
All four must hold at the same time for a deadlock to happen.

Resource allocation graph: a cycle means a possible deadlock; with single-instance resources a cycle means a deadlock for sure.

DEADLOCK PREVENTION - make sure at least one condition can never hold:
- Mutual exclusion: use sharable resources where possible (read-only files).
- Hold and wait: a process must request all resources at once before it starts.
- No preemption: if a request cannot be granted, release everything held.
- Circular wait: number all resource types, request only in increasing order."""),
    ("Deadlocks - Unit 2 (contd.)", """DEADLOCK AVOIDANCE - the OS checks every request and grants it only if the system stays in a safe state.
Safe state: there is at least one order (safe sequence) in which every process can finish.
Unsafe state does not always mean deadlock, but it may lead to one.

BANKER'S ALGORITHM (multiple instances of each resource type)
Data structures: Available, Max, Allocation, Need = Max - Allocation.
Safety algorithm: find a process whose Need <= Work, pretend it finishes, add its Allocation to Work, repeat.
Resource-request algorithm: if Request <= Need and Request <= Available, pretend to allocate and run the safety algorithm; grant only if the new state is safe.

Example: 5 processes P0-P4, resources A B C with Available = (3, 3, 2).
Safe sequence found: P1, P3, P4, P0, P2 -> the system is in a safe state.

(see the lecture slides for the rest)"""),
]

AMBIGUOUS_NOTE = [
    ("Locking and deadlocks - quick revision", """Two-phase locking: a transaction first acquires all its locks in the growing phase and releases them in the shrinking phase. Strict two-phase locking holds exclusive locks until commit.

Two-phase locking can itself lead to deadlocks between transactions. Common deadlock prevention schemes based on timestamps:
- wait-die: an older transaction may wait for a younger one; a younger one requesting a lock held by an older one is rolled back.
- wound-wait: an older transaction wounds (rolls back) the younger one; a younger one waits.

Doubt: do we need this for both the OS paper and the DBMS paper? Check with sir."""),
]

DBMS_NORMALIZATION = [
    ("DBMS - UNIT 5: NORMALIZATION", """Prof. A. Mehta | Database Management Systems

Why normalise? To remove redundancy and the insertion, update and deletion anomalies that come with it.

Functional dependency (FD): X -> Y means the value of X determines the value of Y.
Example: RollNo -> Name. Closure of attributes X+ gives everything X determines; used to find candidate keys.
Armstrong's axioms: reflexivity, augmentation, transitivity.

First normal form (1NF): every attribute holds atomic values, no repeating groups.
Second normal form (2NF): 1NF + no partial dependency of a non-prime attribute on part of a candidate key.
Third normal form (3NF): 2NF + no transitive dependency of a non-prime attribute on a key.
For every FD X -> A: X is a superkey, or A is a prime attribute."""),
    ("UNIT 5: NORMALIZATION (contd.)", """Boyce-Codd normal form (BCNF): for every non-trivial FD X -> Y, X must be a superkey.
BCNF is stricter than 3NF. Every BCNF relation is in 3NF but not the other way round.

Decomposition properties
- Lossless join: joining the decomposed tables gives back exactly the original table. Test: the common attributes must be a key of at least one of the two tables.
- Dependency preservation: every FD can be checked inside a single table.
3NF decomposition always achieves both. BCNF decomposition is always lossless but may not preserve dependencies.

Worked example: R(A, B, C) with A -> B, B -> C. Key = A. B -> C is transitive, so R is not in 3NF.
Decompose into R1(A, B) and R2(B, C): both in BCNF, lossless join, dependencies preserved.

Denormalisation: deliberately adding redundancy back for faster reads in reporting systems."""),
]

DBMS_TRANSACTIONS = [
    ("DBMS Unit 4 - Transactions (Neha)", """Transaction: a unit of work that must execute completely or not at all.

ACID properties
- Atomicity: all or nothing - handled by the recovery manager using the log (undo).
- Consistency: a transaction takes the database from one consistent state to another.
- Isolation: concurrent transactions do not see each other's intermediate results.
- Durability: once committed, changes survive crashes (redo from the log).

Transaction states: active -> partially committed -> committed; or failed -> aborted.

Concurrency problems: lost update, dirty read, unrepeatable read, phantom read.

Two-phase locking (2PL)
- Growing phase: the transaction may obtain locks but not release any.
- Shrinking phase: it may release locks but not obtain new ones.
- Strict 2PL keeps exclusive locks till commit, which avoids cascading rollbacks.
Shared (S) and exclusive (X) lock compatibility: S-S compatible, everything else conflicts."""),
]

PAGING_NOTES = [
    ("OS Unit 3 - Paging & Virtual Memory", """Paging: physical memory is divided into fixed-size frames and logical memory into pages of the same size. The page table maps each page number to a frame number, so a process need not be stored contiguously. No external fragmentation; small internal fragmentation in the last page.
Address translation: logical address = (page number p, offset d). TLB caches recent page-table entries.

Virtual memory and demand paging: pages are loaded only when needed. A reference to a page not in memory causes a page fault.

Page replacement algorithms
- FIFO: replace the oldest page. Can show Belady's anomaly (more frames, more faults).
- Optimal page replacement: replace the page that will not be used for the longest time. Lowest fault rate, but needs the future - used as a benchmark.
- LRU (least recently used): replace the page that has not been used for the longest time. Good approximation of optimal; implemented with counters or a stack.

Thrashing: the process spends more time paging than executing because it does not have enough frames. Cause: degree of multiprogramming too high. Fix: working-set model, page-fault frequency control."""),
]

FEE_CIRCULAR = [("CIRCULAR No. ACC/2026/114", """Date: 15 October 2026

Dear Students,

All students are informed that the last date for payment of the semester fee for the odd semester 2026-27 is 31 October 2026. A late fine of Rs 100 per day will be charged after the last date.

Fees can be paid online through the student portal or at the accounts counter between 10:00 am and 3:00 pm on working days.

By order,
Registrar""")]

ASSIGNMENT_NOTICE = [("NOTICE - Department of CSE", """Date: 20 October 2026

All students of B.Tech CSE Semester 5 are hereby informed that the submission deadline for Assignment 3 (Operating Systems) is 28 October 2026.

Assignments must be submitted in hard copy to the HOD office. Late submissions will not be accepted.

HOD, CSE""")]

HOSTEL_NOTICE = [("HOSTEL NOTICE", """Dear students,

This is to inform all residents of Boys Hostel Block B that the water supply will remain suspended on 27 October 2026 from 9 am to 2 pm due to tank cleaning.

Residents are requested to store water in advance.

Chief Warden""")]

HANDWRITTEN_PAGE = [
    "Unit 4 - Disk Scheduling + RAID",
    "SCAN (elevator algo): head moves in one",
    "direction servicing requests, then reverses.",
    "C-SCAN: circular SCAN, jumps back to start",
    "without servicing on return -> uniform wait.",
    "",
    "RAID 0 = striping, no redundancy",
    "RAID 1 = mirroring (2x disks)",
    "RAID 5 = block striping + distributed parity",
    "     survives 1 disk failure",
]

MEME_LINES = ["ME AT 2 AM BEFORE INTERNALS", "opening DOC-2026-WA0041.pdf",
              "for the 6th time hoping it is", "the right subject this time"]


# ---------------------------------------------------------------- builders

def typed_pdf(path, pages, fontsize=10.5):
    doc = fitz.open()
    for title, body in pages:
        page = doc.new_page(width=595, height=842)
        page.insert_text((56, 70), title, fontsize=14, fontname="hebo")
        page.draw_line((56, 80), (539, 80), color=(0.6, 0.6, 0.6), width=0.6)
        page.insert_textbox(fitz.Rect(56, 96, 539, 800), body, fontsize=fontsize, fontname="helv",
                            lineheight=1.35)
    doc.set_metadata({"producer": "slothNtidy demo data"})
    doc.save(path, garbage=3, deflate=True)
    doc.close()


def handwritten_photo(path, lines, seed=7, rotate=1.1, brightness=1.0, blur=0.6, quality=82):
    rnd = random.Random(seed)
    w, h = 1240, 1700
    img = Image.new("RGB", (w, h), (247, 243, 229))
    d = ImageDraw.Draw(img)
    for y in range(150, h, 64):
        d.line([(60, y), (w - 60, y)], fill=(170, 192, 220), width=2)
    d.line([(132, 0), (132, h)], fill=(222, 150, 150), width=2)
    font = ImageFont.truetype(HAND_FONT, 46)
    y = 100
    for ln in lines:
        if ln:
            d.text((152 + rnd.randint(-6, 6), y + rnd.randint(-3, 3)), ln, font=font, fill=(28, 38, 112))
        y += 64
    img = img.rotate(rotate, resample=Image.BICUBIC, fillcolor=(58, 52, 48))
    img = ImageEnhance.Brightness(img).enhance(brightness)
    img = img.filter(ImageFilter.GaussianBlur(blur))
    img.save(path, quality=quality)


def meme(path):
    img = Image.new("RGB", (900, 900), (24, 24, 28))
    d = ImageDraw.Draw(img)
    d.ellipse((330, 330, 570, 570), fill=(246, 196, 88))           # a very tired emoji face
    d.ellipse((385, 410, 425, 450), fill=(24, 24, 28))
    d.ellipse((475, 410, 515, 450), fill=(24, 24, 28))
    d.arc((400, 470, 500, 540), 200, 340, fill=(24, 24, 28), width=8)
    font = ImageFont.truetype(HAND_FONT, 52)
    for i, ln in enumerate(MEME_LINES[:1]):
        d.text((60, 70 + i * 70), ln, font=font, fill=(255, 255, 255))
    for i, ln in enumerate(MEME_LINES[1:]):
        d.text((60, 640 + i * 70), ln, font=font, fill=(255, 255, 255))
    img.save(path, quality=85)


def write_chat(folder, name, lines):
    with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    if os.path.isdir(EXTRA):
        shutil.rmtree(EXTRA)

    # Group 1 - the official group (Android export)
    g1 = os.path.join(OUT, "Official_CSE_Group")
    os.makedirs(g1)
    typed_pdf(os.path.join(g1, "DOC-20261012-WA0003.pdf"), DBMS_NORMALIZATION)
    typed_pdf(os.path.join(g1, "Fee_Circular_Oct.pdf"), FEE_CIRCULAR)
    typed_pdf(os.path.join(g1, "OS_Unit1_CPU_Scheduling.pdf"), OS_SCHEDULING)
    typed_pdf(os.path.join(g1, "Assignment_3_Notice.pdf"), ASSIGNMENT_NOTICE)
    write_chat(g1, "WhatsApp Chat with Official_CSE_Group.txt", [
        "12/10/26, 10:02 am - Messages and calls are end-to-end encrypted. No one outside of this chat can read or listen to them.",
        f"12/10/26, 10:02 am - Prof. Mehta: {LRM}DOC-20261012-WA0003.pdf (file attached)",
        "DBMS normalization notes for Unit 5. Read before Thursday's class.",
        f"15/10/26, 4:31 pm - CR Office: {LRM}Fee_Circular_Oct.pdf (file attached)",
        "15/10/26, 4:32 pm - CR Office: Fee last date 31st, please pay on time",
        f"16/10/26, 11:20 am - Prof. Sharma: {LRM}OS_Unit1_CPU_Scheduling.pdf (file attached)",
        "Unit 1 complete notes - FCFS, SJF, Round Robin. Numericals will come in internals.",
        f"20/10/26, 6:45 pm - CR Office: {LRM}Assignment_3_Notice.pdf (file attached)",
    ])

    # Group 2 - the unofficial class group (iPhone export: [date, time] + <attached: ...>)
    g2 = os.path.join(OUT, "Unofficial_Class")
    os.makedirs(g2)
    shutil.copyfile(os.path.join(g1, "OS_Unit1_CPU_Scheduling.pdf"),
                    os.path.join(g2, "00000011-DOC-20261018-WA0011.pdf"))       # exact re-share
    typed_pdf(os.path.join(g2, "00000019-DOC-20261021-WA0019.pdf"), DEADLOCK_NOTES)
    meme(os.path.join(g2, "00000031-IMG-20261022-WA0031.jpg"))
    typed_pdf(os.path.join(g2, "00000044-DOC-20261023-WA0044.pdf"), AMBIGUOUS_NOTE)
    write_chat(g2, "_chat.txt", [
        f"{LRM}[18/10/26, 9:40:11 PM] Aman: {LRM}<attached: 00000011-DOC-20261018-WA0011.pdf>",
        "[18/10/26, 9:40:30 PM] Aman: sir wale scheduling notes",
        f"{LRM}[21/10/26, 9:14:03 PM] Rohan: {LRM}<attached: 00000019-DOC-20261021-WA0019.pdf>",
        "[21/10/26, 9:15:20 PM] Rohan: Deadlock notes, recovery skipped",
        "[21/10/26, 9:16:02 PM] Aman: thanks bhai",
        f"{LRM}[22/10/26, 11:58:40 PM] Kabir: {LRM}<attached: 00000031-IMG-20261022-WA0031.jpg>",
        "[22/10/26, 11:59:02 PM] Kabir: literally us",
        f"{LRM}[23/10/26, 8:12:44 AM] Isha: {LRM}<attached: 00000044-DOC-20261023-WA0044.pdf>",
    ])

    # Group 3 - lab section (Android export)
    g3 = os.path.join(OUT, "OS_Lab_Section")
    os.makedirs(g3)
    short = [OS_SCHEDULING[0], OS_SCHEDULING[1]]                                 # same notes, one page less
    typed_pdf(os.path.join(g3, "CPU_scheduling_short.pdf"), short, fontsize=11)
    handwritten_photo(os.path.join(g3, "IMG-20261024-WA0007.jpg"), HANDWRITTEN_PAGE)
    typed_pdf(os.path.join(g3, "DOC-20261025-WA0052.pdf"), DBMS_TRANSACTIONS)
    write_chat(g3, "WhatsApp Chat with OS_Lab_Section.txt", [
        f"19/10/26, 7:02 pm - Priya: {LRM}CPU_scheduling_short.pdf (file attached)",
        "my notes from the lecture, shorter version",
        f"24/10/26, 6:05 pm - Neha: {LRM}IMG-20261024-WA0007.jpg (file attached)",
        "disk scheduling + RAID handwritten notes",
        f"25/10/26, 9:30 pm - Neha: {LRM}DOC-20261025-WA0052.pdf (file attached)",
        "25/10/26, 9:31 pm - Neha: dbms transactions, made these myself",
    ])

    # Group 4 - hostel wing (Android export)
    g4 = os.path.join(OUT, "Hostel_Wing")
    os.makedirs(g4)
    handwritten_photo(os.path.join(g4, "IMG-20261024-WA0012.jpg"), HANDWRITTEN_PAGE,
                      seed=7, rotate=1.1, brightness=0.9, blur=0.9, quality=60)   # same page, re-photographed
    typed_pdf(os.path.join(g4, "Hostel_Notice_Water_Supply.pdf"), HOSTEL_NOTICE)
    write_chat(g4, "WhatsApp Chat with Hostel_Wing.txt", [
        f"24/10/26, 10:41 pm - Arjun: {LRM}IMG-20261024-WA0012.jpg (file attached)",
        "photo of Neha's storage notes",
        f"26/10/26, 8:05 am - Warden Office: {LRM}Hostel_Notice_Water_Supply.pdf (file attached)",
    ])

    # Extra file for the live demo: drop it in and watch Unit 3 turn green
    os.makedirs(EXTRA)
    typed_pdf(os.path.join(EXTRA, "DOC-20261029-WA0063.pdf"), PAGING_NOTES)
    write_chat(EXTRA, "WhatsApp Chat with Unofficial_Class.txt", [
        f"29/10/26, 11:02 pm - Rohan: {LRM}DOC-20261029-WA0063.pdf (file attached)",
        "found Unit 3 paging notes from a senior",
    ])

    count = sum(len([f for f in fs if not f.endswith(".txt")]) for _, _, fs in os.walk(OUT))
    print(f"Demo inbox ready: {OUT} ({count} files in 4 groups)")
    print(f"Live-demo extra:  {EXTRA}")


if __name__ == "__main__":
    sys.exit(main())
