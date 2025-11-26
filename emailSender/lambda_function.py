import os
import logging
from typing import Dict, Any, List

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
STUDENTS_TABLE = os.environ.get("STUDENTS_TABLE", "Roomeya-Students")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "no-reply@example.com") # SES에 인증된 이메일

dynamodb = boto3.resource("dynamodb", region_name=REGION)
students_table = dynamodb.Table(STUDENTS_TABLE)
ses = boto3.client("ses", region_name=REGION)

def lambda_handler(event, context):
    """
    event는 matchingProcessor의 결과를 받고:
    {
      "formId": "...",
      "matches": [
        {
          "roomId": "room-0001",
          "members": ["20250001", "20250002"],
          "roomType": "DOUBLE"
        },
        ...
      ]
    }
    """
    logger.info("Email sender event: %s", event)
    form_id = event.get("formId")
    matches = event.get("matches", [])
    
    if not form_id or not matches:
        logger.warning("formId or matches missing in event")
        return {"message": "No matches to notify", "notified": 0}

    # 1. studentNo -> (roomId, roomType) 매핑 만들기
    student_assignments = build_student_assignments(matches)

    # 2. studentNo 목록으로 학생 정보 조회 (이 예시는 단순 get_item 반복)
    student_nos = list(student_assignments.keys())
    students = fetch_students(student_nos)

    # 3. 각 학생에게 이메일 발송
    notified_count = 0
    for studentNo, student in students.items():
        assignment = student_assignments.get(studentNo)
        if not assignment:
            continue

        email = student.get("email")
        name = student.get("name", studentNo)
        room_id = assignment["roomId"]
        room_type = assignment["roomType"]

        if not email:
            logger.warning("No email for studentNo=%s", studentNo)
            continue

        try:
            send_room_assignment_email(
                to_email=email,
                name=name,
                form_id=form_id,
                room_id=room_id,
                room_type=room_type,
            )
            notified_count += 1
        except ClientError as e:
            logger.error("Failed to send email to %s: %s", email, e)

    logger.info("Notified %d students for formId=%s", notified_count, form_id)
    return {
        "formId": form_id,
        "notified": notified_count,
        "totalStudents": len(student_assignments),
    }


def build_student_assignments(matches: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    matches 배열을 studentNo 기준으로 펼쳐서:
    {
      "20250001": { "roomId": "room-0001", "roomType": "DOUBLE" },
      "20250002": { "roomId": "room-0001", "roomType": "DOUBLE" },
      ...
    }
    """
    result: Dict[str, Dict[str, Any]] = {}

    for match in matches:
        room_id = match.get("roomId")
        room_type = match.get("roomType")
        members = match.get("members", [])

        # members가 ["20250001", "20250002"] 형태인지
        # [{"studentNo": "20250001"}, ...] 형태인지에 따라 다름
        for m in members:
            if isinstance(m, dict):
                student_no = m.get("studentNo")
            else:
                student_no = m

            if not student_no:
                continue

            result[student_no] = {
                "roomId": room_id,
                "roomType": room_type,
            }

    return result


def fetch_students(student_nos: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    studentNo 리스트로 Roomeya-Students에서 학생 정보를 가져온다.
    (심플하게 get_item 반복. 학생 수 많으면 BatchGetItem으로 개선 가능)
    반환:
    {
      "20250001": { "studentNo": "20250001", "email": "a@...", ... },
      ...
    }
    """
    students: Dict[str, Dict[str, Any]] = {}

    for student_no in student_nos:
        try:
            res = students_table.get_item(
                Key={
                    "studentId": student_no,
                }
            )
        except ClientError as e:
            logger.error("Failed to get student %s: %s", student_no, e)
            continue

        item = res.get("Item")
        if item:
            students[student_no] = item
        else:
            logger.warning("No student found for studentNo=%s", student_no)

    return students


def send_room_assignment_email(
    to_email: str,
    name: str,
    form_id: str,
    room_id: str,
    room_type: str,
):
    """
    AWS SES로 방 배정 결과 이메일 발송
    """
    subject = "[Roomeya] 기숙사 방 배정 안내"
    body_text = f"""
{name}님 안녕하세요.

기숙사 방 배정 결과를 안내드립니다.

- 신청 폼 ID: {form_id}
- 배정된 방: {room_id}
- 방 유형: {room_type}

궁금한 점이 있으시면 관리자에게 문의해주세요.

감사합니다.
Roomeya 드림
""".strip()

    ses.send_email(
        Source=SENDER_EMAIL,
        Destination={
            "ToAddresses": [to_email],
        },
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": body_text, "Charset": "UTF-8"},
            },
        },
    )
    logger.info("Sent email to %s (room=%s)", to_email, room_id)