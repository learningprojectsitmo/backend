from __future__ import annotations

import json
from collections import defaultdict

from fastapi import HTTPException

from src.core.exceptions import BusinessLogicError

MAX_OUTPUT_CELLS = 1_000_000
MAX_AFFILIATION_BYTES = 50 * 1024 * 1024


def participation_rows(registrations, audience, preview, questions, answers, common, criterion_count):
    answer_map = defaultdict(dict)
    for answer in answers:
        answer_map[answer["submission_id"]][answer["question_id"]] = answer["score"]
    output_count = sum(
        len(audience[row["attempt_id"]]) if row["window_id"] else len(preview)
        for row in registrations
        if row["attempt_id"] is not None
    )
    if output_count * (3 * criterion_count + 24) > MAX_OUTPUT_CELLS:
        raise HTTPException(413, detail={"code": "csv_export_limit_exceeded", "message": "Too many output cells"})
    output = []
    affiliations = {}
    affiliation_bytes = 0
    for row in registrations:
        if row["attempt_id"] is None:
            continue
        historical = row["window_id"] is not None
        people = audience[row["attempt_id"]] if historical else preview
        criteria = questions[row["project_type_id"]]
        for person in people:
            # Preview people are reused across attempts. Cache once instead of copying a potentially
            # large affiliation string into each row before the HTTP byte budget gets a chance to run.
            person_key = id(person)
            if person_key not in affiliations:
                affiliations[person_key] = json.dumps(
                    sorted(set(person["own_project_ids"] or [])), separators=(",", ":")
                )
            encoded_ids = affiliations[person_key]
            affiliation_bytes += len(encoded_ids)  # JSON integer IDs are ASCII.
            if affiliation_bytes > MAX_AFFILIATION_BYTES:
                raise HTTPException(
                    413,
                    detail={
                        "code": "csv_export_limit_exceeded",
                        "message": "Affiliation expansion exceeds byte budget",
                    },
                )
            status = "not_requested"
            if historical:
                status = (
                    "excluded"
                    if not person["admitted"]
                    else ("submitted" if person["submission_id"] is not None else "not_submitted")
                )
            submitted = status == "submitted"
            scores = answer_map[person["submission_id"]] if submitted else {}
            if submitted and (set(scores) != {q["id"] for q in criteria} or sum(scores.values()) != person["total"]):
                raise BusinessLogicError({"code": "invalid_sheet_data", "message": "Inconsistent submitted sheet"})
            item = {
                "schema_version": "assessment-participation.v1",
                **common,
                **{
                    key: row[key]
                    for key in ("registration_id", "attempt_id", "project_id", "project_name", "project_type_id")
                },
                "assessor_id": person["user_id"],
                "assessor_name": person["assessor_name"],
                "role": person["role"],
                "own_project_ids": encoded_ids,
                "audience_source": "snapshot" if historical else "preview",
                "admitted": person["admitted"] if historical else None,
                "exclusion_reason": person["exclusion_reason"] if historical else None,
                "response_status": status,
                "submission_version": person["submission_version"] if submitted else None,
                "submitted_at": person["submitted_at"] if submitted else None,
                "total": person["total"] if submitted else None,
            }
            for i in range(criterion_count):
                question = criteria[i] if i < len(criteria) else None
                item[f"criterion_{i + 1}_question_id"] = question["id"] if question else None
                item[f"criterion_{i + 1}_text"] = question["text"] if question else None
                item[f"criterion_{i + 1}_score"] = scores.get(question["id"]) if question else None
            output.append(item)
    return output
