# 🦥 Sloth Smart Document Index

### 📄 [2026-10-23_dbms_indexing_optimization.pdf](./Notes/2026-10-23_dbms_indexing_optimization.pdf)
**Original File:** `dbms_pdf1.pdf` | **Stats:** `2 page(s), 3860 chars`

**📌 Key Points:**
* Explains the concept and importance of indexing in DBMS, including types of indexes and their characteristics.
* Describes B+ tree and hash index structures and their use cases.
* Discusses cost-based and heuristic optimization techniques in query processing.
* Outlines join algorithms and provides practical tips for optimizing database performance.

---

### 📄 [2026-10-23_dbms_transactions_concurrency.pdf](./Notes/2026-10-23_dbms_transactions_concurrency.pdf)
**Original File:** `dbms_pdf3.pdf` | **Stats:** `3 page(s), 5841 chars`

**📌 Key Points:**
* Explains the concept of transactions and their states (Active, Partially committed, Committed, Failed, Aborted)
* Discusses problems of uncontrolled concurrency including Dirty read, Lost update, Unrepeatable read, and Phantom read
* Describes the ACID properties: Atomicity, Consistency, Isolation, Durability
* Introduces serializability, conflict serializability, and view serializability with the precedence graph test
* Details lock-based protocols like Two-Phase Locking (2PL) and its strict variant
* Outlines SQL isolation levels and their impact on transaction isolation
* Describes deadlock and its detection through the wait-for graph

**🗑️ User-Approved Duplicate Deletion:** `dbms_pdf4.pdf` (`2p, 3603 chars`)
* ➕ Includes detailed explanations on deadlock detection and prevention, such as wait-for graph, prevention methods, and timeout mechanisms.
* ➕ Expands on concurrency control with timestamp ordering, where each transaction has a unique timestamp, and operations violating timestamp order are rolled back.
* ➕ Provides comprehensive information on recovery from failure, including log records, write-ahead logging, undo, redo, and checkpoint mechanisms.
* ➕ Discusses deferred vs. immediate update techniques and introduces shadow paging as an alternative to logging.

---

### 📄 [2026-10-23_dbms_normalization.pdf](./Notes/2026-10-23_dbms_normalization.pdf)
**Original File:** `dbms_pdf5.pdf` | **Stats:** `3 page(s), 5245 chars`

**📌 Key Points:**
* Explains normalization to avoid data redundancy and update anomalies in database design
* Describes functional dependencies, Armstrong's axioms, and attribute closure
* Details the steps from 1NF to BCNF, including first, second, third normal forms, and Boyce-Codd normal form
* Discusses decomposition principles for lossless join and dependency preservation

**🗑️ User-Approved Duplicate Deletion:** `dbms_pdf2.pdf` (`2p, 3275 chars`)
* ➕ Includes detailed sections on decomposition, worked examples, beyond BCNF (multivalued dependencies, 4NF, 5NF), and when to denormalize.
* ➕ Provides specific examples and conditions for normalization and denormalization strategies.

---

