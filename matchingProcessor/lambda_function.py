import os
import json
import io
import csv
import logging
from datetime import datetime
from typing import List, Dict, Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ENV
RESPONSES_TABLE = os.environ.get("RESPONSES_TABLE", "Roomeya-FormResponses")
STUDENTS_TABLE = os.environ.get("STUDENTS_TABLE", "Roomeya-Students")
MATCHES_TABLE = os.environ.get("MATCHES_TABLE", "Roomeya-Results")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "roomeya-export")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
responses_table = dynamodb.Table(RESPONSES_TABLE)
students_table = dynamodb.Table(STUDENTS_TABLE)
matches_table = dynamodb.Table(MATCHES_TABLE)
s3 = boto3.client("s3", region_name=REGION)


def lambda_handler(event, context):
    logger.info(f"EVENT = {event}")

    form_id = event.get("formId")
    if not form_id:
        raise ValueError("formId is required")

    # 1. Form 응답 조회
    responses = fetch_responses_by_form_id(form_id)
    logger.info(f"Fetched {len(responses)} responses")

    if not responses:
        return {
            "formId": form_id,
            "totalStudents": 0,
            "totalRooms": 0,
            "matches": [],
        }

    # 2. 학생 테이블 정보 merge
    merged = merge_with_student_table(responses)

    # 3. 매칭 알고리즘
    matches = match_students(merged)

    # 4. DynamoDB 저장
    save_matches(form_id, matches)

    # 5. CSV 파일 S3 업로드
    s3_key = write_results_to_s3(form_id, matches)

    return {
        "formId": form_id,
        "totalStudents": len(merged),
        "totalRooms": len(matches),
        "matches": [
            {
                "roomId": m["roomId"],
                "members": [stu["studentId"] for stu in m["members"]]
            }
            for m in matches
        ],
        "s3Key": s3_key
    }


def fetch_responses_by_form_id(form_id):
    items = []
    last_key = None

    while True:
        params = {
            "KeyConditionExpression": "formId = :f",
            "ExpressionAttributeValues": {":f": form_id},
        }
        if last_key:
            params["ExclusiveStartKey"] = last_key

        res = responses_table.query(**params)
        items.extend(res.get("Items", []))

        last_key = res.get("LastEvaluatedKey")
        if not last_key:
            break

    return items


def merge_with_student_table(responses):
    merged = []
    for res in responses:
        sid = res["studentId"]

        stu = students_table.get_item(Key={"studentId": sid}).get("Item", {})

        merged.append({
            "studentId": sid,
            "name": res.get("name"),
            "answers": res.get("answers"),
            "gender": stu.get("gender", ""),
        })

    return merged


def calc_score(a, b):
    score = 0

    # 1) 성별 동일해야 함
    if a["gender"] and a["gender"] == b["gender"]:
        score += 30
    else:
        return 0  # 성별 다르면 바로 제외

    ans_a = a["answers"]
    ans_b = b["answers"]

    # 2) 흡연 여부
    if ans_a.get("smoking") == ans_b.get("smoking"):
        score += 10

    # 3) wakeup 동일
    if ans_a.get("wakeup") == ans_b.get("wakeup"):
        score += 8

    # 4) bedtime similarity
    score += bedtime_similarity(ans_a.get("bedtime"), ans_b.get("bedtime"))

    # 5) MBTI 첫 글자 동일
    if ans_a.get("mbti", "")[:1] == ans_b.get("mbti", "")[:1]:
        score += 3

    return score


def bedtime_similarity(a, b):
    order = {"before10": 1, "10to12": 2, "after12": 3}
    if a not in order or b not in order:
        return 0
    diff = abs(order[a] - order[b])
    return max(5 - diff * 2, 0)


def match_students(students):
    used = set()
    matches = []
    room_num = 1

    for i in range(len(students)):
        if i in used:
            continue

        best_j = None
        best_score = -1

        # 가장 점수 높은 짝 찾기
        for j in range(i + 1, len(students)):
            if j in used:
                continue

            s = calc_score(students[i], students[j])
            if s > best_score:
                best_score = s
                best_j = j

        if best_j is not None and best_score > 0:
            matches.append({
                "roomId": f"room-{room_num:04d}",
                "members": [students[i], students[best_j]],
                "score": best_score
            })
            used.add(i)
            used.add(best_j)

        else:
            # 단독 배정 (score 없음)
            matches.append({
                "roomId": f"room-{room_num:04d}",
                "members": [students[i]],
                "score": 0
            })
            used.add(i)

        room_num += 1

    return matches



def save_matches(form_id, matches):
    for match in matches:
        item = {
            "formId": form_id,
            "roomId": match["roomId"],
            "members": [m["studentId"] for m in match["members"]],
            "score": match.get("score", 0),
            "createdAt": datetime.utcnow().isoformat(),
        }
        matches_table.put_item(Item=item)



def write_results_to_s3(form_id, matches):
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["formId", "roomId", "studentId", "score"])

    for match in matches:
        for m in match["members"]:
            writer.writerow([
                form_id,
                match["roomId"],
                m["studentId"],
                match.get("score", 0)
            ])

    key = f"matching-results/{form_id}.csv"

    s3.put_object(
        Bucket=RESULTS_BUCKET,
        Key=key,
        Body=buffer.getvalue().encode("utf-8"),
        ContentType="text/csv"
    )

    return key

def calculate_score(a, b):
    score = 0

    # 성별
    if a.get("answers", {}).get("gender") == b.get("answers", {}).get("gender"):
        score += 30

    # 흡연 여부
    if a.get("answers", {}).get("smoking") == b.get("answers", {}).get("smoking"):
        score += 20

    # wakeup
    if a.get("answers", {}).get("wakeup") == b.get("answers", {}).get("wakeup"):
        score += 15

    # bedtime (before10, 10to12, after12 비슷한지 체크)
    bedtime_a = a.get("answers", {}).get("bedtime")
    bedtime_b = b.get("answers", {}).get("bedtime")
    if bedtime_a and bedtime_b:
        if bedtime_a == bedtime_b:
            score += 15
        # 예: before10 ~ 10to12 는 비슷한 시간대
        elif (bedtime_a == "before10" and bedtime_b == "10to12") or (bedtime_b == "before10" and bedtime_a == "10to12"):
            score += 8

    # MBTI 첫 글자
    mbti_a = a.get("answers", {}).get("mbti", "")
    mbti_b = b.get("answers", {}).get("mbti", "")
    if len(mbti_a) > 0 and len(mbti_b) > 0 and mbti_a[0] == mbti_b[0]:
        score += 20

    return min(score, 100)
