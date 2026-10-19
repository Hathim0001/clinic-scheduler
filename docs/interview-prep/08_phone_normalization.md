# Backend File Guide: `backend/app/domain/phone.py`

> **File Path:** [`backend/app/domain/phone.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/phone.py)  
> **Topic:** Phone Number Normalization, Validation, Uniqueness & Privacy  
> **Key Function:** `normalise_phone(raw: str) -> str`

---

## 1. File Role & High-Level Purpose

In India, a patient's mobile number serves as their primary unique identifier in outpatient clinics. 

This file handles:
1. Normalizing raw user input (with spaces, hyphens, prefixes, or trunk zeros) into a canonical E.164 format: `+91XXXXXXXXXX`.
2. Validating that the phone is a legitimate 10-digit Indian mobile number starting with digits 6, 7, 8, or 9.
3. Rejecting non-ASCII numbers (guarding against homoglyph attacks and strange Unicode digit scripts).
4. Guarding patient privacy during uniqueness conflicts (`PHONE_TAKEN`).

---

## 2. Key Functions & Code Breakdown

### `normalise_phone(raw: str) -> str` (Lines 21–36)
```python
_FORMS = (
    re.compile(r"\+?91([6-9][0-9]{9})"),
    re.compile(r"0([6-9][0-9]{9})"),
    re.compile(r"([6-9][0-9]{9})"),
)

def normalise_phone(raw: str) -> str:
    if len(raw) > MAX_RAW_LENGTH or not raw.isascii():
        raise ValueError(MESSAGE)
    squeezed = _SEPARATORS.sub("", raw.strip())
    for form in _FORMS:
        match = form.fullmatch(squeezed)
        if match:
            return "+91" + match.group(1)
    raise ValueError(MESSAGE)
```

#### Detailed Logic:
1. **Punctuation Stripping:** Removes common separators: spaces, hyphens, parentheses, and dots (`_SEPARATORS = re.compile(r"[ \-().]")`).
2. **Flexible Prefix Handling:** Matches any standard way Indian users write numbers:
   - International prefix: `+91 98765 43210` $\rightarrow$ `+919876543210`
   - Numeric prefix: `919876543210` $\rightarrow$ `+919876543210`
   - Trunk zero: `09876543210` $\rightarrow$ `+919876543210`
   - Bare 10 digits: `9876543210` $\rightarrow$ `+919876543210`
3. **Valid Range:** The 10-digit number must start with `6`, `7`, `8`, or `9` (official Telecom Regulatory Authority of India mobile allocation).
4. **Security / ASCII Check:** Rejects non-ASCII input. `[0-9]` is explicitly used instead of `\d`, because Python's `\d` matches Unicode digits from Arabic, Devanagari, and other scripts.

---

## 3. Privacy & Uniqueness Architecture

* **Database Constraint:** In [`0001_initial.sql`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/migrations/versions/0001_initial.sql#L52), `CONSTRAINT patients_phone_key UNIQUE (phone)`.
* **Privacy on Conflict (`A-15`):** If someone tries to register an existing number, the API returns:
  ```json
  {
    "error": {
      "code": "PHONE_TAKEN",
      "message": "This phone number is already registered.",
      "details": { "existing_patient_id": 42 }
    }
  }
  ```
  **Notice what is missing:** It does **not** return the patient's name, email, or date of birth. This prevents malicious actors from brute-forcing phone numbers to harvest patient identities.

---

## 4. Interview Pitch (60-Second Explanation)

> *"In `phone.py`, we normalize patient phone numbers into canonical `+91XXXXXXXXXX` format. We accept common human variations—such as spaces, dashes, country code prefixes (+91 or 91), or domestic trunk zeros (0)—and validate that the 10-digit number begins with 6 through 9. To ensure security, we reject non-ASCII inputs to prevent Unicode digit spoofing. Phone numbers are strictly unique in our PostgreSQL schema. To protect patient privacy, when an existing phone conflict occurs, our API returns only the existing patient ID, never disclosing names or medical details."*

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Why is phone number uniqueness enforced in both the service and the database?**  
  * **A:** The service check performs a query first so it can return a clean, descriptive `409 PHONE_TAKEN` error. However, if two receptionists register the same phone number at the exact same millisecond, both service checks would pass. The database `UNIQUE (phone)` constraint is the ultimate concurrency guard that stops the race condition.
