from __future__ import annotations

import csv
import logging
import math
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..database.database import SessionLocal
from ..models import Agent, AgentSession, Borrower, Call, CallAttempt, Campaign, Vendor

logger = logging.getLogger(__name__)

MODEL_MAP = {
    "vendor_telephony.csv": Vendor,
    "campaigns.csv": Campaign,
    "borrowers.csv": Borrower,
    "agents.csv": Agent,
    "calls.csv": Call,
    "call_attempts.csv": CallAttempt,
    "agent_sessions.csv": AgentSession,
}
IMPORT_ORDER = tuple(MODEL_MAP)
BATCH_SIZE = 1000
MISSING_TEXT = {"", "nan", "nat", "null", "none"}
EXCEL_EPOCH = datetime(1899, 12, 30)


class ImportValidationError(ValueError):
    """The input CSV does not satisfy the importer contract."""


class ImportConflictError(ImportValidationError):
    """The resolved input conflicts with rows already stored in the database."""


class ImportDatabaseError(RuntimeError):
    """A database operation failed for reasons other than invalid CSV data."""


def _database_error_context(exc: SQLAlchemyError) -> str:
    """Return safe diagnostic context without exposing SQL or imported values."""
    original = getattr(exc, "orig", None)
    args = getattr(original, "args", ())
    driver_code = args[0] if args and isinstance(args[0], (int, str)) else None
    driver_message = args[1] if len(args) > 1 and isinstance(args[1], str) else ""
    code_text = f", database code {driver_code}" if driver_code is not None else ""

    explanations = {
        1048: "the database rejected a NULL value for a required column",
        1054: "the database table has a column that does not match the application model",
        1146: "the database table is missing; restart the API to create its tables",
        1364: "the database table requires a column that the application model does not provide",
        1406: "a database column is narrower than the imported value; check the existing table schema",
        1452: "the database rejected a foreign-key reference",
    }
    explanation = explanations.get(driver_code)
    if driver_code == 1364:
        # MySQL identifies the required column but does not include row data in
        # this error. Returning only that identifier is safe and actionable.
        missing_default = re.search(
            r"Field ['`]([^'`]+)['`] doesn't have a default value",
            driver_message,
            flags=re.IGNORECASE,
        )
        column = missing_default.group(1) if missing_default else None
        if column:
            context = (
                f" (database code 1364: existing table requires column '{column}' "
                "with no default, but the importer does not provide it; "
                "the database schema does not match the application model)"
            )
        else:
            context = f" (database code 1364: {explanation})"
    elif explanation:
        context = f" (database code {driver_code}: {explanation})"
    elif driver_code is not None:
        context = f" (database code {driver_code})"
    else:
        context = ""

    logger.error(
        "CSV database operation failed: exception_type=%s%s%s",
        type(exc).__name__, code_text, context,
    )
    return context


@dataclass(frozen=True)
class ImportReport:
    file: str
    table: str
    source_rows: int
    imported: int
    exact_duplicates: int
    conflicts_resolved: int
    skipped: int
    orphan_rows_skipped: int = 0
    orphan_examples: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        return (
            f"{self.table.replace('_', ' ').title()} imported successfully. "
            f"Imported: {self.imported}; exact duplicates: {self.exact_duplicates}; "
            f"conflicts resolved: {self.conflicts_resolved}; skipped: {self.skipped}; "
            f"orphan rows skipped: {self.orphan_rows_skipped}."
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["message"] = self.message
        return result


@dataclass(frozen=True)
class ParsedRow:
    row_number: int
    values: dict[str, Any]
    updated_at: datetime | None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if value.__class__.__name__ in {"NAType", "NaTType"}:
        return True
    return isinstance(value, str) and value.strip().casefold() in MISSING_TEXT


def _excel_number_to_text(value: str) -> str:
    """Expand Excel/scientific numeric text without converting identifiers to float."""
    if "e" not in value.casefold() and "." not in value:
        return value
    try:
        number = Decimal(value)
    except InvalidOperation:
        return value
    if not number.is_finite():
        return value
    if number == number.to_integral_value():
        return str(int(number))
    return format(number, "f")


def _parse_datetime(value: str, filename: str, row_number: int, column_name: str) -> datetime:
    text_value = value.strip()
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
        for pattern in (
            "%Y/%m/%d %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
        ):
            try:
                parsed = datetime.strptime(text_value, pattern)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                serial = Decimal(text_value)
                if not serial.is_finite():
                    raise InvalidOperation
                parsed = EXCEL_EPOCH + timedelta(days=float(serial))
            except (InvalidOperation, OverflowError, ValueError) as exc:
                raise ImportValidationError(
                    f"{filename}: row {row_number}: invalid timestamp in '{column_name}': {value!r}."
                ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _normalize_value(value: Any, column: Any, filename: str, row_number: int) -> Any:
    if _is_missing(value):
        if column.nullable:
            return None
        raise ImportValidationError(
            f"{filename}: row {row_number}: required field '{column.name}' is empty."
        )

    text_value = str(value).strip()
    try:
        python_type = column.type.python_type
        if python_type is datetime:
            return _parse_datetime(text_value, filename, row_number, column.name)
        if python_type is int:
            number = Decimal(text_value)
            if not number.is_finite() or number != number.to_integral_value():
                raise ValueError("expected a whole number")
            return int(number)
        if python_type is float:
            number = Decimal(text_value)
            if not number.is_finite():
                raise ValueError("expected a finite number")
            return float(number)
        if python_type is str:
            normalized = _excel_number_to_text(text_value)
            max_length = getattr(column.type, "length", None)
            if max_length and len(normalized) > max_length:
                raise ValueError(f"exceeds maximum length {max_length}")
            return normalized
        return text_value
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ImportValidationError(
            f"{filename}: row {row_number}: invalid value for '{column.name}': {text_value!r}."
        ) from exc


def _read_records(path: Path, model: type) -> tuple[list[ParsedRow], int, int, bool]:
    filename = path.name
    columns = {column.name: column for column in model.__table__.columns}
    expected = set(columns)
    rows: list[ParsedRow] = []
    source_rows = 0
    skipped = 0

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            try:
                raw_headers = next(reader)
            except StopIteration as exc:
                raise ImportValidationError(f"{filename}: CSV file has no header row.") from exc

            headers = [header.replace("\ufeff", "").strip() for header in raw_headers]
            ignored_positions = {
                index for index, header in enumerate(headers)
                if not header or re.match(r"(?i)^unnamed(?::|$)", header)
            }
            kept_headers = [header for index, header in enumerate(headers) if index not in ignored_positions]
            if len(kept_headers) != len(set(kept_headers)):
                raise ImportValidationError(f"{filename}: duplicate column names after trimming whitespace.")

            auxiliary_updated_at = "updated_at" not in expected and "updated_at" in kept_headers
            allowed = expected | ({"updated_at"} if auxiliary_updated_at else set())
            unknown = sorted(set(kept_headers) - allowed)
            missing = sorted(expected - set(kept_headers))
            if unknown:
                raise ImportValidationError(f"{filename}: unsupported column(s): {', '.join(unknown)}.")
            if missing:
                raise ImportValidationError(f"{filename}: missing column(s): {', '.join(missing)}.")

            for row_number, values in enumerate(reader, start=2):
                if not values or all(not value.strip() for value in values):
                    continue
                source_rows += 1
                if len(values) != len(raw_headers):
                    raise ImportValidationError(
                        f"{filename}: row {row_number}: expected {len(raw_headers)} values, got {len(values)}."
                    )
                if any(values[index].strip() for index in ignored_positions):
                    raise ImportValidationError(
                        f"{filename}: row {row_number}: unnamed columns contain data."
                    )

                raw = {
                    header: values[index]
                    for index, header in enumerate(headers)
                    if index not in ignored_positions
                }
                record = {
                    name: _normalize_value(raw[name], column, filename, row_number)
                    for name, column in columns.items()
                }
                key_column = next(column for column in columns.values() if column.primary_key)
                if record[key_column.name] is None:
                    raise ImportValidationError(
                        f"{filename}: row {row_number}: primary key '{key_column.name}' is empty."
                    )

                if "updated_at" in columns:
                    updated_at = record["updated_at"]
                elif auxiliary_updated_at:
                    raw_update = raw["updated_at"]
                    updated_at = (
                        None if _is_missing(raw_update)
                        else _parse_datetime(str(raw_update), filename, row_number, "updated_at")
                    )
                else:
                    updated_at = None
                rows.append(ParsedRow(row_number, record, updated_at))
    except UnicodeDecodeError as exc:
        raise ImportValidationError(f"{filename}: CSV must use UTF-8 encoding.") from exc
    except OSError as exc:
        raise ImportValidationError(f"{filename}: CSV could not be read.") from exc

    return rows, source_rows, skipped, "updated_at" in columns or auxiliary_updated_at


def _signature(row: ParsedRow) -> tuple[Any, ...]:
    # Keep source updated_at in the comparison even when the model treats it as metadata.
    return tuple(row.values.items()), row.updated_at


def _resolve_duplicates(
    filename: str,
    model: type,
    rows: list[ParsedRow],
    has_updated_at: bool,
) -> tuple[list[ParsedRow], int, int]:
    primary_key = next(column.name for column in model.__table__.columns if column.primary_key)
    grouped: OrderedDict[Any, list[ParsedRow]] = OrderedDict()
    for row in rows:
        grouped.setdefault(row.values[primary_key], []).append(row)

    resolved: list[ParsedRow] = []
    exact_duplicates = 0
    conflicts_resolved = 0
    for key, candidates in grouped.items():
        distinct: list[ParsedRow] = []
        signatures: set[tuple[Any, ...]] = set()
        for candidate in candidates:
            signature = _signature(candidate)
            if signature in signatures:
                exact_duplicates += 1
                logger.debug(
                    "%s: discarded exact duplicate row %s for %s=%r",
                    filename, candidate.row_number, primary_key, key,
                )
            else:
                signatures.add(signature)
                distinct.append(candidate)

        if len(distinct) == 1:
            winner = distinct[0]
        elif has_updated_at:
            winner = max(
                distinct,
                key=lambda item: (
                    item.updated_at or datetime.min,
                    -item.row_number,
                ),
            )
        else:
            winner = distinct[0]

        for candidate in distinct:
            if candidate is winner:
                continue
            conflicts_resolved += 1
            logger.debug(
                "%s: discarded conflicting row %s for %s=%r; kept row %s",
                filename, candidate.row_number, primary_key, key, winner.row_number,
            )
        resolved.append(winner)

    return resolved, exact_duplicates, conflicts_resolved


def _check_existing_primary_keys(
    filename: str,
    model: type,
    rows: list[ParsedRow],
    db: Session,
) -> None:
    primary_key = next(column for column in model.__table__.columns if column.primary_key)
    keys = [row.values[primary_key.name] for row in rows]
    existing: set[Any] = set()
    for start in range(0, len(keys), BATCH_SIZE):
        existing.update(
            db.scalars(select(primary_key).where(primary_key.in_(keys[start : start + BATCH_SIZE]))).all()
        )
    if existing:
        ordered_existing = [key for key in keys if key in existing]
        examples = ", ".join(repr(value) for value in ordered_existing[:5])
        raise ImportConflictError(
            f"{filename}: resolved primary key(s) already exist in the database: {examples}. "
            "Reset the database before re-importing this dataset."
        )


def _validate_foreign_keys(
    filename: str,
    model: type,
    rows: list[ParsedRow],
    db: Session,
) -> tuple[list[ParsedRow], int, tuple[str, ...]]:
    orphan_rows: dict[int, list[str]] = {}
    for column in model.__table__.columns:
        if not column.foreign_keys:
            continue
        foreign_key = next(iter(column.foreign_keys))
        target = foreign_key.column
        references: dict[Any, list[int]] = {}
        for row in rows:
            value = row.values[column.name]
            if value is not None:
                references.setdefault(value, []).append(row.row_number)
        if not references:
            continue

        existing: set[Any] = set()
        values = list(references)
        for start in range(0, len(values), BATCH_SIZE):
            existing.update(
                db.scalars(select(target).where(target.in_(values[start : start + BATCH_SIZE]))).all()
            )
        missing = [value for value in references if value not in existing]
        for value in missing:
            for row_number in references[value]:
                orphan_rows.setdefault(row_number, []).append(
                    f"{column.name}={value!r} has no {target.table.name}.{target.name} parent"
                )

    examples = tuple(
        f"row {row_number}: {'; '.join(reasons)}"
        for row_number, reasons in list(orphan_rows.items())[:5]
    )
    valid_rows = [row for row in rows if row.row_number not in orphan_rows]
    return valid_rows, len(orphan_rows), examples


def _validate_unique_constraints(filename: str, model: type, rows: list[ParsedRow], db: Session) -> None:
    for constraint in model.__table__.constraints:
        if not getattr(constraint, "unique", False) or len(constraint.columns) != 1:
            continue
        column = next(iter(constraint.columns))
        values = [row.values[column.name] for row in rows if row.values[column.name] is not None]
        seen: set[Any] = set()
        repeated = None
        for value in values:
            if value in seen:
                repeated = value
                break
            seen.add(value)
        if repeated is not None:
            raise ImportValidationError(
                f"{filename}: resolved rows still duplicate unique column '{column.name}': {repeated!r}."
            )
        for start in range(0, len(values), BATCH_SIZE):
            existing = db.scalar(
                select(column).where(column.in_(values[start : start + BATCH_SIZE])).limit(1)
            )
            if existing is not None:
                raise ImportConflictError(
                    f"{filename}: unique value for '{column.name}' already exists in the database."
                )


def import_csv(file_path: str | Path) -> ImportReport:
    path = Path(file_path)
    model = MODEL_MAP.get(path.name)
    if model is None:
        raise ImportValidationError(f"Unsupported dataset file: {path.name}.")

    rows, source_rows, skipped, has_updated_at = _read_records(path, model)
    resolved, exact_duplicates, conflicts_resolved = _resolve_duplicates(
        path.name, model, rows, has_updated_at,
    )
    db = SessionLocal()
    orphan_rows_skipped = 0
    orphan_examples: tuple[str, ...] = ()
    try:
        resolved, orphan_rows_skipped, orphan_examples = _validate_foreign_keys(
            path.name, model, resolved, db,
        )
        _check_existing_primary_keys(path.name, model, resolved, db)
        _validate_unique_constraints(path.name, model, resolved, db)

        mappings = [row.values for row in resolved]
        for start in range(0, len(mappings), BATCH_SIZE):
            db.execute(insert(model), mappings[start : start + BATCH_SIZE])
        db.commit()
    except ImportValidationError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise ImportValidationError(
            f"{path.name}: database constraint rejected the resolved rows. "
            "Check required values and foreign-key references."
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        context = _database_error_context(exc)
        raise ImportDatabaseError(
            f"{path.name}: database operation failed{context}. "
            "The server log contains the exception type and database code; "
            "SQL statements and imported personal data are intentionally omitted."
        ) from exc
    finally:
        db.close()

    logger.info(
        "%s imported %s row(s), resolved %s conflict(s), skipped %s orphan row(s)",
        path.name, len(resolved), conflicts_resolved, orphan_rows_skipped,
    )

    return ImportReport(
        file=path.name,
        table=model.__tablename__,
        source_rows=source_rows,
        imported=len(resolved),
        exact_duplicates=exact_duplicates,
        conflicts_resolved=conflicts_resolved,
        skipped=skipped + orphan_rows_skipped,
        orphan_rows_skipped=orphan_rows_skipped,
        orphan_examples=orphan_examples,
    )
